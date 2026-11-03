"""Thin HID transport for the AK680 MAX configuration interface."""
from __future__ import annotations

import time

import hid

from .layout import USERPIC_BYTES
from .protocol import (
    CMD_GET_FN,
    CMD_GET_KEYMATRIX,
    CMD_GET_LEDPARAM,
    CMD_GET_MULTI_MAGNETISM,
    CMD_GET_PROFILE,
    CMD_GET_USB_VERSION,
    CMD_GET_USERPIC,
    CMD_SET_FN,
    CMD_SET_KEYMATRIX,
    CMD_SET_LEDPARAM,
    CMD_SET_MULTI_MAGNETISM,
    CMD_SET_USERPIC,
    INPUT_REPORT_SIZE,
    REPORT_SIZE,
    build,
)

CONFIG_USAGE_PAGE = 0xFFFF
CONFIG_USAGE = 0x02


class DeviceNotFound(RuntimeError):
    """The keyboard configuration interface is not present."""


class Keyboard:
    def __init__(self, vid: int, pid: int, verbose: bool = True):
        dev = None
        for candidate in hid.enumerate(vid, pid):
            if (candidate.get("usage_page") == CONFIG_USAGE_PAGE
                    and candidate.get("usage") == CONFIG_USAGE):
                dev = candidate
                break
        if dev is None:
            raise DeviceNotFound(
                f"не найден конфигурационный HID-интерфейс "
                f"(VID {vid:04X} / PID {pid:04X} / usage_page 0xFFFF / usage 0x02). "
                f"Проверь провод, порт и что клавиатура не в режиме другого профиля."
            )
        self.path = dev["path"]
        self.h = hid.device()
        self.h.open_path(self.path)
        self.verbose = verbose

    def __enter__(self) -> "Keyboard":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        try:
            self.h.close()
        except Exception:
            pass

    # --- low level -------------------------------------------------------- #
    def _send(self, cmd, data=b"", bit8=False):
        self.h.send_feature_report(build(cmd, data, bit8))

    def _read(self, tries=4, gap=0.05):
        last = None
        for _ in range(tries):
            try:
                last = bytes(self.h.get_feature_report(0, REPORT_SIZE))
                return last
            except Exception:
                time.sleep(gap)
        return last

    def send(self, cmd, data=b"", bit8=False, delay=0.03):
        self._send(cmd, data, bit8)
        time.sleep(delay)

    def query_echo(self, cmd, data=b"", tries=8, gap=0.06):
        """Command whose reply echoes the command byte."""
        for _ in range(tries):
            self._send(cmd, data)
            time.sleep(gap)
            r = self._read(tries=2, gap=gap)
            if r and r[1] == cmd:
                return r[1:]
        return None

    def query_page(self, cmd, data=b"", tries=8, gap=0.06):
        """Paged command: reply is a full 64-byte data page, no echo byte."""
        for _ in range(tries):
            self._send(cmd, data)
            time.sleep(gap)
            r = self._read(tries=2, gap=gap)
            if r is not None and len(r[1:]) == INPUT_REPORT_SIZE:
                return r[1:]
        return None

    # --- command wrappers ------------------------------------------------- #
    def info(self):
        r = self.query_echo(CMD_GET_USB_VERSION)
        if not r:
            return None
        dev_id = int.from_bytes(r[1:5], "little")
        ver = int.from_bytes(r[7:9], "little")
        return {
            "device_id": dev_id,
            "version_raw": ver,
            "version": f"v{ver >> 8}{ver & 0xFF:02d}",
        }

    def active_profile(self):
        r = self.query_echo(CMD_GET_PROFILE)
        return r[1] if r else 0

    def get_keymatrix(self, profile, layer, pages=6):
        out = b""
        for page in range(pages):
            pg = self.query_page(CMD_GET_KEYMATRIX, bytes([profile, 0xFF, page, layer]))
            if pg is None:
                return None
            out += pg
        return out

    def get_keymatrix_entry(self, profile, layer, idx):
        page = (idx * 4) // INPUT_REPORT_SIZE
        pg = self.query_page(CMD_GET_KEYMATRIX, bytes([profile, 0xFF, page, layer]))
        if pg is None:
            return None
        off = (idx * 4) % INPUT_REPORT_SIZE
        return pg[off:off + 4]

    def get_fn(self, profile, sysmode=0, pages=6):
        out = b""
        for page in range(pages):
            pg = self.query_page(CMD_GET_FN, bytes([sysmode, profile, 0xFF, page]))
            if pg is None:
                return None
            out += pg
        return out

    def get_fn_entry(self, profile, idx, sysmode=0):
        page = (idx * 4) // INPUT_REPORT_SIZE
        pg = self.query_page(CMD_GET_FN, bytes([sysmode, profile, 0xFF, page]))
        if pg is None:
            return None
        off = (idx * 4) % INPUT_REPORT_SIZE
        return pg[off:off + 4]

    def get_magnetism(self, sub, pages=3):
        out = b""
        for page in range(pages):
            pg = self.query_page(CMD_GET_MULTI_MAGNETISM, bytes([sub, 0x01, page]))
            if pg is None:
                return None
            out += pg
        return out

    def get_led(self):
        return self.query_echo(CMD_GET_LEDPARAM)

    def get_userpic(self, slot, blocks=6):
        out = b""
        for block in range(blocks):
            pg = self.query_page(CMD_GET_USERPIC, bytes([slot, 0xFF, block]))
            if pg is None:
                return None
            out += pg
        return out[:USERPIC_BYTES]

    # --- writes ----------------------------------------------------------- #
    def set_keymatrix(self, profile, idx, hid_code, layer=0, enabled=1):
        data = bytes([profile, idx, 0, 0, enabled, layer, 0, 0, 0, hid_code, 0])
        self.send(CMD_SET_KEYMATRIX, data)

    def set_fn(self, profile, idx, hid_code, fn_sys=0):
        data = bytes([fn_sys, profile, idx, 0, 0, 0, 0, 0, 0, hid_code, 0])
        self.send(CMD_SET_FN, data)

    def set_keymatrix_verified(self, profile, idx, hid_code, layer=0, tries=8):
        """Write and read back: the firmware sometimes drops back-to-back writes."""
        for _ in range(tries):
            self.set_keymatrix(profile, idx, hid_code, layer=layer)
            time.sleep(0.15)
            entry = self.get_keymatrix_entry(profile, layer, idx)
            if entry is not None and len(entry) == 4 and entry[2] == hid_code:
                return True
        return False

    def set_fn_verified(self, profile, idx, hid_code, fn_sys=0, tries=8):
        for _ in range(tries):
            self.set_fn(profile, idx, hid_code, fn_sys=fn_sys)
            time.sleep(0.15)
            entry = self.get_fn_entry(profile, idx, sysmode=fn_sys)
            if entry is not None and len(entry) == 4 and entry[2] == hid_code:
                return True
        return False

    def set_magnetism(self, sub, values_u16, key_count=90):
        raw = b"".join(int(v).to_bytes(2, "little") for v in values_u16[:key_count])
        pages = max(1, (len(raw) + 55) // 56)
        for page in range(pages):
            chunk = raw[page * 56:(page + 1) * 56]
            is_last = 1 if page == pages - 1 else 0
            data = bytes([sub, 0x01, page, is_last, 0, 0, 0]) + chunk
            self.send(CMD_SET_MULTI_MAGNETISM, data, delay=0.25 if is_last else 0.03)

    def set_userpic(self, slot, data):
        slot_data = bytes(data[:USERPIC_BYTES]).ljust(USERPIC_BYTES, b"\x00")
        pages = (USERPIC_BYTES + 55) // 56
        for page in range(pages):
            chunk = slot_data[page * 56:(page + 1) * 56]
            payload = bytes([slot, 0xFF, page, len(chunk),
                             1 if page == pages - 1 else 0, 0, 0]) + chunk
            self.send(CMD_SET_USERPIC, payload, delay=0.012)

    def set_led_params(self, params):
        """Write the 7 LED parameters [mode, speed, brightness, option, r, g, b]."""
        self.send(CMD_SET_LEDPARAM, bytes(params[:7]), bit8=True)

    def set_led_userpic(self, slot, mode=13, speed=4, brightness=4, flash=(0, 200, 200)):
        params = bytes([mode, speed, brightness, (slot << 4) & 0xF0, *flash])
        self.set_led_params(params)
