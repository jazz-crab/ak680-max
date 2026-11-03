"""Load and validate the device configuration (config/default.toml).

The config describes *intent* (what keys do, how deep the switches trigger,
which colours the zones get), not raw protocol bytes. The protocol layer turns
that intent into firmware reports.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PALETTE = {
    "blue": (0x7A, 0xA2, 0xF7),
    "orange": (0xFF, 0x4C, 0x00),
    "red": (0xFF, 0x00, 0x12),
    "purple": (0xCC, 0x33, 0xE8),
}
DEFAULT_PREVIEW = {
    "blue": (0x7A, 0xA2, 0xF7),
    "orange": (0xFF, 0x9E, 0x64),
    "red": (0xF7, 0x76, 0x8E),
    "purple": (0xBB, 0x9A, 0xF7),
}
DEFAULT_LEVELS = {"orange": 0.58, "red": 0.88}
DEFAULT_GAIN = (0.384, 1.0, 0.469)
ZONES = ("blue", "orange", "red", "purple")


class ConfigError(ValueError):
    """Invalid or missing configuration."""


@dataclass(frozen=True)
class LightingConfig:
    enabled: bool = True
    slot: int = 0
    mode: int = 13
    speed: int = 4
    brightness: int = 4
    flash_rgb: tuple[int, int, int] = (0, 200, 200)
    palette: dict[str, tuple[int, int, int]] = field(
        default_factory=lambda: dict(DEFAULT_PALETTE)
    )
    preview_palette: dict[str, tuple[int, int, int]] = field(
        default_factory=lambda: dict(DEFAULT_PREVIEW)
    )
    levels: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_LEVELS))
    gain: tuple[float, float, float] = DEFAULT_GAIN


@dataclass(frozen=True)
class Config:
    path: Path
    vid: int = 0x3151
    pid: int = 0x502D
    firmware: str | None = "v306"
    profile: str | int = "active"
    base_remaps: dict[int, int] = field(default_factory=dict)
    fn_remaps: dict[int, int] = field(default_factory=dict)
    actuation_mm: float = 1.0
    release_mm: float = 1.5
    precision: int = 100
    lighting: LightingConfig = field(default_factory=LightingConfig)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.is_file():
            raise ConfigError(f"конфиг не найден: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"{path}: не удалось прочитать конфиг: {exc}") from exc
        try:
            raw = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: некорректный TOML: {exc}") from exc
        return cls.from_dict(raw, path)

    @classmethod
    def from_dict(cls, raw: dict, path: Path) -> "Config":
        dev = raw.get("device", {})
        layout = raw.get("layout", {})
        switches = raw.get("switches", {})
        light = raw.get("lighting", {})

        cfg = cls(
            path=path,
            vid=_as_int(dev.get("vid", 0x3151), "device.vid"),
            pid=_as_int(dev.get("pid", 0x502D), "device.pid"),
            firmware=_as_optional_str(dev.get("firmware")),
            profile=_as_profile(dev.get("profile", "active")),
            base_remaps=_as_remaps(layout.get("base_remaps", {}), "layout.base_remaps"),
            fn_remaps=_as_remaps(layout.get("fn_remaps", {}), "layout.fn_remaps"),
            actuation_mm=_as_float(switches.get("actuation_mm", 1.0), "switches.actuation_mm"),
            release_mm=_as_float(switches.get("release_mm", 1.5), "switches.release_mm"),
            precision=_as_int(switches.get("precision", 100), "switches.precision"),
            lighting=_lighting(light),
        )
        cfg._validate()
        return cfg

    def _validate(self) -> None:
        if not (0 <= self.vid <= 0xFFFF and 0 <= self.pid <= 0xFFFF):
            raise ConfigError("device.vid/pid должны быть в диапазоне 0..0xFFFF")
        if self.precision <= 0:
            raise ConfigError("switches.precision должен быть > 0")
        if self.actuation_mm <= 0 or self.release_mm <= 0:
            raise ConfigError("switches.actuation_mm / release_mm должны быть > 0")
        if self.release_mm < self.actuation_mm:
            raise ConfigError("switches.release_mm не может быть меньше actuation_mm")
        for name, remaps in (("layout.base_remaps", self.base_remaps),
                             ("layout.fn_remaps", self.fn_remaps)):
            for pos, usage in remaps.items():
                if not (0 <= pos < 90):
                    raise ConfigError(f"{name}: позиция {pos} вне матрицы 0..89")
                if not (0 <= usage <= 0xFFFF):
                    raise ConfigError(f"{name}[{pos}]: HID usage вне диапазона")
        light = self.lighting
        if not (0 <= light.slot <= 15):
            raise ConfigError("lighting.slot должен быть 0..15")
        for name in ("mode", "speed", "brightness"):
            if not (0 <= getattr(light, name) <= 0xFF):
                raise ConfigError(f"lighting.{name} должен быть 0..255")
        if any(not (0 <= c <= 0xFF) for c in light.flash_rgb):
            raise ConfigError("lighting.flash_rgb: компоненты должны быть 0..255")
        if any(v <= 0 for v in light.gain):
            raise ConfigError("lighting.channel_gain: коэффициенты должны быть > 0")
        for zone in ZONES:
            if zone not in light.palette:
                raise ConfigError(f"lighting.palette: отсутствует зона {zone!r}")
            if zone not in light.preview_palette:
                raise ConfigError(f"lighting.preview_palette: отсутствует зона {zone!r}")


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
def _as_int(value, where: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{where}: ожидалось целое число")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{where}: ожидалось целое число, получено {value!r}") from None


def _as_float(value, where: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{where}: ожидалось число, получено {value!r}") from None


def _as_optional_str(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_profile(value) -> str | int:
    if value == "active":
        return "active"
    number = _as_int(value, "device.profile")
    if not (0 <= number <= 3):
        raise ConfigError("device.profile должен быть 'active' или 0..3")
    return number


def _as_remaps(raw: dict, where: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for key, value in raw.items():
        try:
            pos = int(key, 0)
        except (TypeError, ValueError):
            raise ConfigError(f"{where}: ключ {key!r} не является позицией матрицы") from None
        out[pos] = _as_int(value, f"{where}[{key}]")
    return out


def _as_color(value, where: str) -> tuple[int, int, int]:
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) != 6:
            raise ConfigError(f"{where}: ожидался цвет #RRGGBB, получено {value!r}")
        try:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        except ValueError:
            raise ConfigError(f"{where}: ожидался цвет #RRGGBB, получено {value!r}") from None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        rgb = tuple(_as_int(c, where) for c in value)
        if all(0 <= c <= 0xFF for c in rgb):
            return rgb  # type: ignore[return-value]
    raise ConfigError(f"{where}: ожидался цвет #RRGGBB или [r, g, b]")


def _palette(raw: dict, defaults: dict, where: str) -> dict[str, tuple[int, int, int]]:
    out = dict(defaults)
    for zone, value in raw.items():
        if zone not in ZONES:
            raise ConfigError(f"{where}: неизвестная зона {zone!r} (есть: {', '.join(ZONES)})")
        out[zone] = _as_color(value, f"{where}.{zone}")
    return out


def _lighting(raw: dict) -> LightingConfig:
    gain_raw = raw.get("channel_gain", {})
    gain = (
        _as_float(gain_raw.get("red", DEFAULT_GAIN[0]), "lighting.channel_gain.red"),
        _as_float(gain_raw.get("green", DEFAULT_GAIN[1]), "lighting.channel_gain.green"),
        _as_float(gain_raw.get("blue", DEFAULT_GAIN[2]), "lighting.channel_gain.blue"),
    )
    levels = dict(DEFAULT_LEVELS)
    for zone, value in raw.get("levels", {}).items():
        if zone not in ZONES:
            raise ConfigError(f"lighting.levels: неизвестная зона {zone!r}")
        levels[zone] = _as_float(value, f"lighting.levels.{zone}")
        if not (0.0 <= levels[zone] <= 1.0):
            raise ConfigError(f"lighting.levels.{zone}: ожидалось 0.0..1.0")

    flash = raw.get("flash_rgb", [0, 200, 200])
    if not (isinstance(flash, (list, tuple)) and len(flash) == 3):
        raise ConfigError("lighting.flash_rgb: ожидался список [r, g, b]")

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError("lighting.enabled: ожидалось true/false")

    return LightingConfig(
        enabled=enabled,
        slot=_as_int(raw.get("slot", 0), "lighting.slot"),
        mode=_as_int(raw.get("mode", 13), "lighting.mode"),
        speed=_as_int(raw.get("speed", 4), "lighting.speed"),
        brightness=_as_int(raw.get("brightness", 4), "lighting.brightness"),
        flash_rgb=tuple(_as_int(c, "lighting.flash_rgb") for c in flash),  # type: ignore[arg-type]
        palette=_palette(raw.get("palette", {}), DEFAULT_PALETTE, "lighting.palette"),
        preview_palette=_palette(raw.get("preview_palette", {}), DEFAULT_PREVIEW,
                                 "lighting.preview_palette"),
        levels=levels,
        gain=gain,
    )
