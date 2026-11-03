#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Калибровка каналов: две шкалы, чтобы измерить дисбаланс R/G/B на глаз.

Ряд 1 (Tab, Q..P, [ ] \\):  R=255 постоянный, G убывает слева направо.
                            Где цвет впервые выглядит ЖЁЛТЫМ (а не зелёным) —
                            там зелёный канал сравнялся с красным.
Ряд 3 (Shift, Z..M , . /):  R=255 постоянный, B убывает слева направо.
                            Где впервые выглядит МАДЖЕНТОЙ (а не красным).

Результат впиши в config/default.toml -> [lighting.channel_gain].
Вернуть нормальную палитру: ak680 apply --yes
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ak680_max.config import Config
from ak680_max.device import Keyboard
from ak680_max.layout import (
    LAYOUT_COLS,
    LAYOUT_ROWS,
    MATRIX_USAGE,
    PHYS_LAYOUT,
    USERPIC_BYTES,
)

NAV_USAGES = {0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F}   # right column, untouched
RAMP_START, RAMP_END = 255, 70                      # 1.0 .. 0.27


def usage_index():
    out = {}
    for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
        usage = MATRIX_USAGE[pos]
        if usage:
            out.setdefault(usage, pos)
    return out


def ramp(keys):
    n = len(keys)
    out = []
    for i, (label, _usage) in enumerate(keys):
        t = i / max(1, n - 1)
        out.append((label, round(RAMP_START + (RAMP_END - RAMP_START) * t)))
    return out


def main():
    cfg = Config.load(REPO / "config" / "default.toml")
    idx = usage_index()
    data = bytearray(USERPIC_BYTES)

    def keys_of(row_i):
        return [(label, usage) for usage, label, _w in PHYS_LAYOUT[row_i]
                if usage and usage not in NAV_USAGES]

    green = ramp(keys_of(1))
    blue = ramp(keys_of(3))

    print("РЯД 1 — красный постоянный, зелёный убывает (ищем, где станет ЖЁЛТЫМ):")
    for label, value in green:
        usage = dict((l, u) for u, l, _ in PHYS_LAYOUT[1])[label]
        pos = idx[usage]
        data[pos * 3:pos * 3 + 3] = bytes((255, value, 0))
        print(f"   {label:<7} G={value:3d}  ({value / 255:.0%} от красного)")

    print("\nРЯД 3 — красный постоянный, синий убывает (ищем, где станет МАДЖЕНТОЙ):")
    for label, value in blue:
        usage = dict((l, u) for u, l, _ in PHYS_LAYOUT[3])[label]
        pos = idx[usage]
        data[pos * 3:pos * 3 + 3] = bytes((255, 0, value))
        print(f"   {label:<7} B={value:3d}  ({value / 255:.0%} от красного)")

    with Keyboard(cfg.vid, cfg.pid) as kb:
        kb.set_userpic(cfg.lighting.slot, bytes(data))
        kb.set_led_userpic(cfg.lighting.slot, cfg.lighting.mode,
                           cfg.lighting.speed, cfg.lighting.brightness,
                           cfg.lighting.flash_rgb)
    print(f"\nзалито в слот {cfg.lighting.slot} + режим {cfg.lighting.mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
