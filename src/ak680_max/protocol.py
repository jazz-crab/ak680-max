"""HID feature-report protocol used by the AK680 MAX configuration interface.

The keyboard exposes a vendor HID interface (usage page 0xFFFF, usage 0x02).
Feature reports are 65 bytes: [report_id=0][cmd][payload 63][checksum].
Two checksum variants exist; LED commands use the "bit8" one.
"""

REPORT_SIZE = 65
INPUT_REPORT_SIZE = 64

CMD_SET_RESET = 0x01
CMD_SET_LEDPARAM = 0x07
CMD_SET_KEYMATRIX = 0x0A
CMD_SET_USERPIC = 0x0C
CMD_SET_FN = 0x10
CMD_SET_MULTI_MAGNETISM = 0x65

CMD_GET_PROFILE = 0x84
CMD_GET_LEDPARAM = 0x87
CMD_GET_KEYMATRIX = 0x8A
CMD_GET_USERPIC = 0x8C
CMD_GET_USB_VERSION = 0x8F
CMD_GET_FN = 0x90
CMD_GET_MULTI_MAGNETISM = 0xE5

MAG_PRESS = 0x00
MAG_LIFT = 0x01
MAG_MODE = 0x07


def build(cmd, data=b"", bit8=False):
    """Build a 65-byte feature report with the protocol checksum."""
    buf = bytearray(REPORT_SIZE)
    buf[0] = 0
    buf[1] = cmd
    n = min(len(data), REPORT_SIZE - 2)
    buf[2:2 + n] = data[:n]
    if bit8:
        buf[9] = (255 - (sum(buf[1:9]) & 0xFF)) & 0xFF
    else:
        buf[8] = (255 - (sum(buf[1:8]) & 0xFF)) & 0xFF
    return bytes(buf)
