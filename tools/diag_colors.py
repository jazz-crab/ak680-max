#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диагностика цветов: заливает userpic, где КАЖДЫЙ ФИЗИЧЕСКИЙ РЯД — свой цвет.

Нужно, чтобы по внешнему виду клавиатуры понять, что именно ломается:
  * ряды остались рядами и цвета те же  -> RGB и порядок позиций верны;
  * цвета перепутаны (низ стал верхом)  -> индекс позиции трактуется иначе;
  * красный ряд светится зелёным        -> порядок каналов не RGB;
  * всё бледно-зелёное                  -> железо/прошивка гасит каналы.

Вернуть нормальную палитру: ak680 apply --yes
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ak680_max.config import Config
from ak680_max.device import Keyboard
from ak680_max.layout import LAYOUT_COLS, LAYOUT_ROWS, MATRIX_USAGE, PHYS_LAYOUT, USERPIC_BYTES

# Physical rows (usage -> row number). Everything else (right column, arrows)
# is row 5 so it is visible separately.
ROW_OF_USAGE = {}
for row_i, row in enumerate(PHYS_LAYOUT):
    for usage, _label, _w in row:
        if usage:
            ROW_OF_USAGE.setdefault(usage, row_i)

ROW_COLORS = [
    ("ряд 0 (Esc 1..0 = Bksp Home)", (255, 0, 0)),           # red
    ("ряд 1 (Tab Q..P [ ] \\ Del)", (0, 255, 0)),             # green
    ("ряд 2 (Caps A..L ; ' Enter)", (0, 0, 255)),             # blue
    ("ряд 3 (Shift Z..M , . / ↑)", (255, 255, 0)),            # yellow
    ("ряд 4 (Ctrl Win Alt Space Fn ← ↓ →)", (0, 255, 255)),   # cyan
    ("прочее (правый столбец)", (255, 0, 255)),               # magenta
]


def build():
    data = bytearray(USERPIC_BYTES)
    rows = {}
    for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
        usage = MATRIX_USAGE[pos]
        if not usage:
            continue
        row = ROW_OF_USAGE.get(usage, 5)
        r, g, b = ROW_COLORS[row][1]
        data[pos * 3:pos * 3 + 3] = bytes((r, g, b))
        rows.setdefault(row, []).append((pos, usage))
    return bytes(data), rows


def main():
    cfg = Config.load(REPO / "config" / "default.toml")
    data, rows = build()
    for row, keys in sorted(rows.items()):
        name, (r, g, b) = ROW_COLORS[row]
        print(f"{name}: #{r:02x}{g:02x}{b:02x}  позиции {[p for p, _ in keys]}")

    with Keyboard(cfg.vid, cfg.pid) as kb:
        profile = kb.active_profile()
        kb.set_userpic(cfg.lighting.slot, data)
        kb.set_led_userpic(cfg.lighting.slot, cfg.lighting.mode,
                           cfg.lighting.speed, cfg.lighting.brightness,
                           cfg.lighting.flash_rgb)
        got = kb.get_userpic(cfg.lighting.slot)
    print("залито:", "OK (побайтово)" if got == data else "НЕ СОВПАЛО")
    print(f"profile={profile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
