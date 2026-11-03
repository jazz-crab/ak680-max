"""Static map of the AK680 MAX: matrix positions, physical layout, key names.

Nothing here is user configurable at runtime; the *meaning* of the remaps and
the lighting palette live in config/default.toml.
"""

KEY_COUNT = 90          # last occupied matrix position is 89
LAYOUT_COLS = 15        # userpic: 6 rows, 15 columns (column-major)
LAYOUT_ROWS = 6
USERPIC_BYTES = 126 * 3  # slot capacity: 21x6; this board uses 15x6

KEY = {
    "Escape": 0x29,
    "Delete": 0x4C,
    "Home": 0x4A,
    "PrintScr": 0x46,
    "End": 0x4D,
    "grave": 0x35,
}

# Factory HID usage per matrix position (data/device_matrices.json,
# 12625:20525:2255 / Common68_K80X68). 0 = no key at this position.
MATRIX_USAGE = [
    0, 41, 43, 57, 225, 224, 0, 30, 20, 4,
    0, 0, 0, 31, 26, 22, 29, 227, 0, 32,
    8, 7, 27, 226, 0, 33, 21, 9, 6, 0,
    0, 34, 23, 10, 25, 0, 0, 35, 28, 11,
    5, 44, 0, 36, 24, 13, 17, 0, 0, 37,
    12, 14, 16, 0, 0, 38, 18, 15, 54, 230,
    0, 39, 19, 51, 55, 0, 0, 45, 47, 52,
    56, 228, 0, 46, 48, 0, 229, 80, 0, 42,
    49, 40, 82, 81, 0, 74, 76, 75, 78, 79,
] + [0] * (LAYOUT_COLS * LAYOUT_ROWS - 90)

# Fn has no HID usage in the matrix (position 65, bottom row between right
# Alt and right Ctrl), so the firmware never colours it. The address was
# verified on hardware: writing this position lights the Fn key.
FN_POS = 65
FN_USAGE = KEY["Escape"]  # service colour (red)

# Physical 65% layout -- preview image only: (usage, label, width in units).
# Labels show what the key *does* after the base remap.
PHYS_LAYOUT = [
    [(0x35, "`", 1), (0x1E, "1", 1), (0x1F, "2", 1), (0x20, "3", 1), (0x21, "4", 1),
     (0x22, "5", 1), (0x23, "6", 1), (0x24, "7", 1), (0x25, "8", 1), (0x26, "9", 1),
     (0x27, "0", 1), (0x2D, "-", 1), (0x2E, "=", 1), (0x2A, "Bksp", 2), (0x4C, "Del", 1)],
    [(0x2B, "Tab", 1.5), (0x14, "Q", 1), (0x1A, "W", 1), (0x08, "E", 1), (0x15, "R", 1),
     (0x17, "T", 1), (0x1C, "Y", 1), (0x18, "U", 1), (0x0C, "I", 1), (0x12, "O", 1),
     (0x13, "P", 1), (0x2F, "[", 1), (0x30, "]", 1), (0x31, "\\", 1.5), (0x4A, "Home", 1)],
    [(0x29, "Esc", 1.75), (0x04, "A", 1), (0x16, "S", 1), (0x07, "D", 1), (0x09, "F", 1),
     (0x0A, "G", 1), (0x0B, "H", 1), (0x0D, "J", 1), (0x0E, "K", 1), (0x0F, "L", 1),
     (0x33, ";", 1), (0x34, "'", 1), (0x28, "Enter", 2.25), (0x46, "PrtSc", 1)],
    [(0xE1, "Shift", 2.25), (0x1D, "Z", 1), (0x1B, "X", 1), (0x06, "C", 1), (0x19, "V", 1),
     (0x05, "B", 1), (0x11, "N", 1), (0x10, "M", 1), (0x36, ",", 1), (0x37, ".", 1),
     (0x38, "/", 1), (0xE6, "Shift", 1.75), (0x52, "Up", 1), (0x4D, "End", 1)],
    [(0xE0, "Ctrl", 1.25), (0xE3, "Code", 1.25), (0xE2, "Alt", 1.25), (0x2C, "Space", 5.5),
     (0xE5, "Alt", 1.25), (None, "Fn", 1.25), (0xE4, "Ctrl", 1.25),
     (0x50, "Left", 1), (0x51, "Down", 1), (0x4F, "Right", 1)],
]

BG = (0x1A, 0x1B, 0x26)
LEGEND = [
    ((0x35,), "letters, punctuation"),
    ((0x1E,), "digits, Space, arrows"),
    ((0x28,), "Enter, Bksp, Del, Esc, Code, PrtSc, Fn"),
    ((0x2B,), "Home, End, Tab, modifiers"),
]
