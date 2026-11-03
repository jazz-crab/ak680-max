"""Per-key lighting: turn a zone palette into the firmware's userpic bytes.

The firmware maps userpic bytes to *electrical matrix* positions, not to
physical rows. Bytes [3*i : 3*i+3] are the colour of matrix position i; the
image is column-major (x = i // 6, y = i % 6). This is why the preview is
drawn from PHYS_LAYOUT while the payload is built from MATRIX_USAGE.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import LightingConfig
from .layout import (
    BG,
    FN_POS,
    FN_USAGE,
    LAYOUT_COLS,
    LAYOUT_ROWS,
    LEGEND,
    MATRIX_USAGE,
    PHYS_LAYOUT,
    USERPIC_BYTES,
)


def to_device(rgb, level: float, gain) -> tuple[int, int, int]:
    """Intended sRGB -> firmware bytes, compensating LED channel imbalance."""
    ch = [c / k for c, k in zip(rgb, gain)]
    peak = max(ch)
    if peak <= 0:
        return (0, 0, 0)
    scale = 255.0 * level / peak
    return tuple(max(0, min(255, round(c * scale))) for c in ch)


def zone_name(usage: int) -> str:
    """Zone of a key by its *action* (usage already includes base remaps)."""
    if 0x04 <= usage <= 0x1D:                    # A..Z
        return "blue"
    if 0x1E <= usage <= 0x27 or usage in (0x2D, 0x2E):   # 1..0, - =
        return "orange"
    if usage in (0x2F, 0x30, 0x31, 0x33, 0x34, 0x36, 0x37, 0x38, 0x35):
        return "blue"                            # [ ] \ ; ' , . / and `
    if usage in (0x28, 0x2A, 0x29):              # Enter, Backspace, Esc (on Caps)
        return "red"
    if usage in (0x4C, 0xE3):                    # Delete, Win
        return "red"
    if usage in (0x4A, 0x4D):                    # Home, End
        return "purple"
    if usage == 0x46:                            # PrintScreen
        return "red"
    if usage == 0x4B or usage in (0x4E, 0x4F, 0x50, 0x51, 0x52):   # PgUp/PgDn, arrows
        return "orange"
    if usage == 0x2C:                            # Space
        return "orange"
    return "purple"                              # Tab, modifiers, Fn


def zone_color(usage: int, lighting: LightingConfig) -> tuple[int, int, int]:
    return lighting.palette[zone_name(usage)]


def preview_color(usage: int, lighting: LightingConfig) -> tuple[int, int, int]:
    return lighting.preview_palette[zone_name(usage)]


def build_userpic(base_remaps: dict[int, int], lighting: LightingConfig) -> bytes:
    """15x6 payload in matrix order: each key gets exactly its own colour."""
    data = bytearray(USERPIC_BYTES)
    for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
        usage = base_remaps.get(pos, MATRIX_USAGE[pos])
        if not usage:
            if pos == FN_POS:
                data[pos * 3:pos * 3 + 3] = bytes(
                    to_device(zone_color(FN_USAGE, lighting),
                              lighting.levels.get(zone_name(FN_USAGE), 1.0),
                              lighting.gain)
                )
            continue                              # empty matrix position: stay dark
        data[pos * 3:pos * 3 + 3] = bytes(
            to_device(zone_color(usage, lighting),
                      lighting.levels.get(zone_name(usage), 1.0),
                      lighting.gain)
        )
    return bytes(data)


def target_userpic(image: str | os.PathLike | None, base_remaps: dict[int, int],
                   lighting: LightingConfig) -> bytes:
    """Payload for a custom image (15x6, matrix order) or the built-in scheme."""
    if not image:
        return build_userpic(base_remaps, lighting)
    img = Image.open(image).convert("RGB").resize((LAYOUT_COLS, LAYOUT_ROWS), Image.NEAREST)
    data = bytearray(USERPIC_BYTES)
    for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
        x, y = pos // LAYOUT_ROWS, pos % LAYOUT_ROWS    # column-major, 6 rows
        data[pos * 3:pos * 3 + 3] = bytes(img.getpixel((x, y)))
    return bytes(data)


# --------------------------------------------------------------------------- #
# preview rendering
# --------------------------------------------------------------------------- #
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_font(filename: str, size: int):
    """Font for the preview: repo assets, then system fonts."""
    candidates = [
        _repo_root() / "assets" / "fonts" / filename,
        Path.cwd() / "assets" / "fonts" / filename,
        Path.cwd() / filename,
        filename,
        "consola.ttf",
        "segoeui.ttf",
        "arial.ttf",
        "DejaVuSans.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(str(name), size)
        except Exception:
            continue
    return ImageFont.load_default()


def write_pngs(directory: str | os.PathLike, base_remaps: dict[int, int],
               lighting: LightingConfig) -> tuple[Path, Path]:
    """Write userpic-tokyonight.png (raw payload) and keyboard-tokyonight.png.

    The userpic file contains exactly the bytes sent to the firmware (vivid
    palette + channel compensation). The keyboard preview uses the pastel
    preview palette: it shows the intent, not the raw bytes.
    """
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    data = build_userpic(base_remaps, lighting)

    img = Image.new("RGB", (LAYOUT_COLS, LAYOUT_ROWS))
    for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
        img.putpixel((pos // LAYOUT_ROWS, pos % LAYOUT_ROWS),
                     tuple(data[pos * 3:pos * 3 + 3]))
    userpic_path = out / "userpic-tokyonight.png"
    img.save(userpic_path)

    u = 44                                       # px per 1u
    pad, gap = 14, 4
    cols = max(sum(w for _, _, w in row) for row in PHYS_LAYOUT)
    width = int(cols * u) + pad * 2 + 8
    board_h = len(PHYS_LAYOUT) * u
    title_h = 34
    legend_row_h = 26
    legend_cols = 2                             # JetBrains Mono is wide
    legend_h = legend_row_h * ((len(LEGEND) + legend_cols - 1) // legend_cols) + 8
    canvas = Image.new("RGB", (width, int(pad * 2 + board_h + title_h + legend_h)), BG)
    draw = ImageDraw.Draw(canvas)
    font = load_font("JetBrainsMono-Regular.ttf", 12)
    font_title = load_font("JetBrainsMono-Bold.ttf", 17)
    draw.text((pad, pad - 2), "AJAZZ AK680 MAX RGB",
              fill=(0xC0, 0xCA, 0xF5), font=font_title)
    top = pad + title_h
    for row_i, row in enumerate(PHYS_LAYOUT):
        x = 0.0
        for usage, label, w in row:
            x0 = pad + x * u
            y0 = top + row_i * u
            color = preview_color(usage or 0x28, lighting)   # Fn: red, like on hardware
            draw.rounded_rectangle([x0 + gap, y0 + gap,
                                    x0 + w * u - gap, y0 + u - gap],
                                   radius=6, fill=color)
            if label:
                tw = draw.textlength(label, font=font)
                draw.text((x0 + w * u / 2 - tw / 2, y0 + u / 2 - 7), label,
                          fill=BG, font=font)
            x += w
    lw = (width - pad * 2) // legend_cols
    ly = top + board_h + 8
    for i, (usages, text) in enumerate(LEGEND):
        cx = pad + (i % legend_cols) * lw
        cy = ly + (i // legend_cols) * legend_row_h
        draw.rounded_rectangle([cx, cy, cx + 16, cy + 16], radius=4,
                               fill=preview_color(usages[0], lighting))
        draw.text((cx + 22, cy + 1), text, fill=(0xC0, 0xCA, 0xF5), font=font)
    preview_path = out / "keyboard-tokyonight.png"
    canvas.save(preview_path)
    return userpic_path, preview_path
