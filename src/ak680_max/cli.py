"""Command line interface: status / backup / apply / verify / restore / render."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import Config, ConfigError
from .device import DeviceNotFound, Keyboard
from .layout import KEY_COUNT
from .lighting import target_userpic, write_pngs
from .protocol import MAG_LIFT, MAG_PRESS
from .state import (
    describe_backup,
    entries,
    print_state,
    read_state,
    restore_state,
    save_backup,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "default.toml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ak680",
        description="AJAZZ AK680 MAX: конфигурация через HID (Windows, прошивка v306).",
    )
    parser.add_argument("--config", metavar="PATH",
                        help=f"путь к TOML-конфигу (по умолчанию {DEFAULT_CONFIG})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="прочитать устройство и напечатать состояние")

    p = sub.add_parser("backup", help="снять бэкап состояния в JSON")
    p.add_argument("--dir", default=str(REPO_ROOT / "backups"),
                   help="куда сохранять (по умолчанию backups/)")

    p = sub.add_parser("apply", help="привести устройство к конфигу")
    p.add_argument("--yes", action="store_true", help="реально писать (без флага — dry-run)")
    p.add_argument("--no-backup", action="store_true",
                   help="не делать автоматический бэкап перед записью")
    p.add_argument("--backup-dir", default=str(REPO_ROOT / "backups"),
                   help="куда сохранять автоматический бэкап")
    p.add_argument("--no-light", action="store_true", help="не трогать подсветку")
    p.add_argument("--image", default=None,
                   help="своя картинка 15x6 в порядке матрицы")

    p = sub.add_parser("verify", help="сверить устройство с конфигом")
    p.add_argument("--no-light", action="store_true", help="не проверять подсветку")
    p.add_argument("--image", default=None,
                   help="картинка, с которой сравнивать подсветку")

    p = sub.add_parser("restore", help="восстановить состояние из JSON-бэкапа")
    p.add_argument("file", help="путь к backup-*.json")
    p.add_argument("--yes", action="store_true", help="реально писать (без флага — dry-run)")

    p = sub.add_parser("render", help="нарисовать PNG-превью без устройства")
    p.add_argument("--out", default=str(REPO_ROOT / "preview"),
                   help="куда сохранять (по умолчанию preview/)")
    return parser


def load_config(args) -> Config:
    raw = args.config or os.environ.get("AK680_CONFIG")
    path = Path(raw).expanduser() if raw else DEFAULT_CONFIG
    return Config.load(path)


def resolve_profile(kb: Keyboard, cfg: Config) -> int:
    if cfg.profile == "active":
        return kb.active_profile()
    return int(cfg.profile)


def warn_firmware(kb: Keyboard, cfg: Config) -> None:
    info = kb.info()
    if cfg.firmware and info and info["version"] != cfg.firmware:
        print(f"ВНИМАНИЕ: на устройстве {info['version']}, конфиг проверен для "
              f"{cfg.firmware}. Сначала сделай backup и verify.", file=sys.stderr)


def print_plan(cfg: Config, want_pic: bytes | None,
               target_act: int, target_rel: int) -> None:
    print("\nПлан:")
    print("  base layer: " + ", ".join(
        f"{pos}→0x{code:02X}" for pos, code in sorted(cfg.base_remaps.items())))
    print("  Fn(Win):    " + ", ".join(
        f"{pos}→0x{code:02X}" for pos, code in sorted(cfg.fn_remaps.items())))
    print(f"  активация {cfg.actuation_mm:g} мм (raw {target_act}) / "
          f"отпускание {cfg.release_mm:g} мм (raw {target_rel}), {KEY_COUNT} позиций")
    if want_pic:
        total = sum(1 for i in range(0, len(want_pic), 3)
                    if want_pic[i:i + 3] != b"\x00\x00\x00")
        print(f"  подсветка → userpic слот {cfg.lighting.slot} "
              f"({total} клавиш) + режим LED {cfg.lighting.mode}")


def collect_checks(st: dict, cfg: Config, want_pic: bytes | None,
                   target_act: int, target_rel: int) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    layer0 = bytes.fromhex(st["keymatrix"].get("layer0", ""))
    base = entries(layer0, KEY_COUNT)
    for pos, code in sorted(cfg.base_remaps.items()):
        got = base[pos][2] if pos < len(base) else None
        checks.append((f"base[{pos}]", got == code,
                       f"0x{got:02X} (ожидалось 0x{code:02X})"
                       if got is not None else "нет данных"))

    fn_blob = bytes.fromhex(st.get("fn_win", ""))
    fn = entries(fn_blob, KEY_COUNT)
    for pos, code in sorted(cfg.fn_remaps.items()):
        got = fn[pos][2] if pos < len(fn) else None
        checks.append((f"Fn[{pos}]", got == code,
                       f"0x{got:02X} (ожидалось 0x{code:02X})"
                       if got is not None else "нет данных"))

    for name, values, target in (
        ("активация", st.get("actuation_raw"), target_act),
        ("отпускание", st.get("release_raw"), target_rel),
    ):
        good = bool(values) and all(v == target for v in values)
        details = sorted(set(values or []))
        checks.append((name, good, f"{details} (ожидалось [{target}])"))

    if want_pic is not None:
        got_pic = st.get("userpic_slot0")
        checks.append((f"userpic слот {cfg.lighting.slot}",
                       got_pic == want_pic.hex(),
                       "побайтово совпало" if got_pic == want_pic.hex() else "НЕ СОВПАЛО"))
        led_hex = st.get("led") or ""
        led = bytes.fromhex(led_hex) if led_hex else b""
        mode = led[1] if len(led) >= 2 else None
        checks.append((f"режим LED {cfg.lighting.mode}", mode == cfg.lighting.mode,
                       f"{mode}"))
        want_option = (cfg.lighting.slot << 4) & 0xF0
        option = led[4] if len(led) >= 5 else None
        checks.append((f"слот LED {cfg.lighting.slot}",
                       option == want_option,
                       f"0x{option:02X} (ожидалось 0x{want_option:02X})"
                       if option is not None else "нет данных"))
    return checks


def print_checks(checks: list[tuple[str, bool, str]]) -> None:
    for label, ok, detail in checks:
        print(f"  {label}: {'OK' if ok else 'НЕ СОВПАЛО'} ({detail})")


def cmd_status(kb: Keyboard, cfg: Config, args) -> int:
    profile = resolve_profile(kb, cfg)
    st = read_state(kb, profile, userpic_slot=cfg.lighting.slot)
    print_state(st, cfg.precision)
    return 0


def cmd_backup(kb: Keyboard, cfg: Config, args) -> int:
    profile = resolve_profile(kb, cfg)
    st = read_state(kb, profile, userpic_slot=cfg.lighting.slot, want_userpic=True)
    path = save_backup(st, args.dir)
    print_state(st, cfg.precision)
    print(f"\nБэкап: {path}")
    return 0


def cmd_apply(kb: Keyboard, cfg: Config, args) -> int:
    profile = resolve_profile(kb, cfg)
    st = read_state(kb, profile, userpic_slot=cfg.lighting.slot, want_userpic=True)
    print_state(st, cfg.precision)

    if not args.no_backup:
        path = save_backup(st, args.backup_dir)
        print(f"\nБэкап перед записью: {path}")

    wants_light = cfg.lighting.enabled and not args.no_light
    want_pic = (target_userpic(args.image, cfg.base_remaps, cfg.lighting)
                if wants_light else None)
    target_act = round(cfg.actuation_mm * cfg.precision)
    target_rel = round(cfg.release_mm * cfg.precision)
    print_plan(cfg, want_pic, target_act, target_rel)

    if not args.yes:
        print("\nDRY-RUN: ничего не записано. Добавь --yes, чтобы залить.")
        return 0

    failures: list[str] = []

    print("\n== 1/4. base-layer ремапы ==")
    for pos, code in sorted(cfg.base_remaps.items()):
        ok = kb.set_keymatrix_verified(profile, pos, code, layer=0)
        print(f"  {pos} -> 0x{code:02X}  {'OK' if ok else 'НЕ ПОДТВЕРДИЛОСЬ'}")
        if not ok:
            failures.append(f"base[{pos}]")

    print("== 2/4. Fn-слой (Win) ==")
    for pos, code in sorted(cfg.fn_remaps.items()):
        ok = kb.set_fn_verified(profile, pos, code, fn_sys=0)
        print(f"  Fn[{pos}] -> 0x{code:02X}  {'OK' if ok else 'НЕ ПОДТВЕРДИЛОСЬ'}")
        if not ok:
            failures.append(f"Fn[{pos}]")

    print("== 3/4. Hall Effect ==")
    kb.set_magnetism(MAG_PRESS, [target_act] * KEY_COUNT, KEY_COUNT)
    print(f"  активация {cfg.actuation_mm:g} мм (raw {target_act})")
    kb.set_magnetism(MAG_LIFT, [target_rel] * KEY_COUNT, KEY_COUNT)
    print(f"  отпускание {cfg.release_mm:g} мм (raw {target_rel})")

    if want_pic:
        print("== 4/4. Подсветка (userpic по клавишам + режим) ==")
        ok = kb.set_userpic(cfg.lighting.slot, want_pic)
        print(f"  userpic слот {cfg.lighting.slot}: "
              f"{'OK' if ok else 'НЕ ПОДТВЕРДИЛОСЬ'}")
        if not ok:
            failures.append("userpic")
        kb.set_led_userpic(cfg.lighting.slot, cfg.lighting.mode,
                           cfg.lighting.speed, cfg.lighting.brightness,
                           cfg.lighting.flash_rgb)
        print(f"  15x6, слот {cfg.lighting.slot}, режим {cfg.lighting.mode}")

    print("\n== Проверка (чтение с устройства) ==")
    st2 = read_state(kb, profile, userpic_slot=cfg.lighting.slot,
                     want_userpic=want_pic is not None)
    print_state(st2, cfg.precision)
    checks = collect_checks(st2, cfg, want_pic, target_act, target_rel)
    print_checks(checks)
    if any(not ok for _, ok, _ in checks):
        failures.extend(label for label, ok, _ in checks if not ok)

    print("\nГотово." if not failures else f"\nЕСТЬ ПРОБЛЕМЫ: {', '.join(failures)}")
    return 0 if not failures else 1


def cmd_verify(kb: Keyboard, cfg: Config, args) -> int:
    profile = resolve_profile(kb, cfg)
    wants_light = cfg.lighting.enabled and not args.no_light
    want_pic = (target_userpic(args.image, cfg.base_remaps, cfg.lighting)
                if wants_light else None)
    target_act = round(cfg.actuation_mm * cfg.precision)
    target_rel = round(cfg.release_mm * cfg.precision)
    st = read_state(kb, profile, userpic_slot=cfg.lighting.slot,
                    want_userpic=want_pic is not None)
    checks = collect_checks(st, cfg, want_pic, target_act, target_rel)
    print_checks(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


def cmd_restore(kb: Keyboard, cfg: Config, args) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"Ошибка: файл не найден: {path}", file=sys.stderr)
        return 1
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Ошибка чтения бэкапа: {exc}", file=sys.stderr)
        return 1

    print(f"Бэкап: {path}")
    for line in describe_backup(st, cfg.precision):
        print(f"  {line}")
    if not args.yes:
        print("\nDRY-RUN: ничего не записано. Добавь --yes, чтобы восстановить.")
        return 0

    print("\n== Восстановление ==")
    result = restore_state(kb, st, key_count=KEY_COUNT,
                           userpic_slot=cfg.lighting.slot)
    print(f"\nЗаписано полей: {result['written']}, ошибок: {result['failed']}")
    return 0 if result["failed"] == 0 else 1


def cmd_render(cfg: Config, args) -> int:
    userpic, preview = write_pngs(args.out, cfg.base_remaps, cfg.lighting)
    print(f"PNG записаны: {userpic}, {preview}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # A non-Russian Windows console (cp1252) must not crash on Cyrillic output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args)
    except ConfigError as exc:
        print(f"Ошибка конфига: {exc}", file=sys.stderr)
        return 2

    if args.command == "render":
        return cmd_render(cfg, args)

    try:
        kb = Keyboard(cfg.vid, cfg.pid)
    except DeviceNotFound as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # hidapi raises OSError on open/permission problems
        print(f"Ошибка HID: {exc}", file=sys.stderr)
        return 1

    try:
        warn_firmware(kb, cfg)
        handlers = {
            "status": cmd_status,
            "backup": cmd_backup,
            "apply": cmd_apply,
            "verify": cmd_verify,
            "restore": cmd_restore,
        }
        return handlers[args.command](kb, cfg, args)
    finally:
        kb.close()
