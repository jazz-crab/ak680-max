"""Reading, printing, backing up and restoring device state."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .layout import KEY_COUNT
from .protocol import MAG_LIFT, MAG_MODE, MAG_PRESS


def entries(blob: bytes, count: int = KEY_COUNT) -> list[bytes]:
    return [blob[i * 4:i * 4 + 4] for i in range(count)] if blob else []


def read_state(kb, profile: int, key_count: int = KEY_COUNT,
               userpic_slot: int = 0, want_userpic: bool = False) -> dict:
    st = {"profile": profile}
    st["info"] = kb.info()
    st["keymatrix"] = {
        f"layer{layer}": (kb.get_keymatrix(profile, layer) or b"").hex()
        for layer in range(4)
    }
    st["fn_win"] = (kb.get_fn(profile, 0) or b"").hex()
    led = kb.get_led()
    st["led"] = led.hex() if led else None

    press = kb.get_magnetism(MAG_PRESS)
    lift = kb.get_magnetism(MAG_LIFT)
    mode = kb.get_magnetism(MAG_MODE)
    if press:
        st["actuation_raw"] = [
            int.from_bytes(press[i:i + 2], "little")
            for i in range(0, min(len(press), key_count * 2), 2)
        ]
    else:
        st["actuation_raw"] = None
    if lift:
        st["release_raw"] = [
            int.from_bytes(lift[i:i + 2], "little")
            for i in range(0, min(len(lift), key_count * 2), 2)
        ]
    else:
        st["release_raw"] = None
    st["mode_raw"] = list(mode[:key_count]) if mode else None

    if want_userpic:
        up = kb.get_userpic(userpic_slot)
        st["userpic_slot0"] = up.hex() if up else None
    return st


def _nonzero(blob_hex: str | None, count: int = KEY_COUNT) -> int:
    if not blob_hex:
        return 0
    return sum(1 for entry in entries(bytes.fromhex(blob_hex), count)
               if entry != b"\x00\x00\x00\x00")


def print_state(st: dict, precision: int = 100) -> None:
    info = st.get("info") or {}
    print(f"  device_id={info.get('device_id')} firmware={info.get('version')} "
          f"profile={st.get('profile')}")
    print(f"  LED: {(st.get('led') or '')[:20]}")
    for layer in range(4):
        blob = st["keymatrix"].get(f"layer{layer}", "")
        print(f"  keymatrix layer{layer}: {_nonzero(blob)} непустых")
    fn = st.get("fn_win", "")
    fn_entries = entries(bytes.fromhex(fn)) if fn else []
    fn_pos32 = fn_entries[32].hex() if len(fn_entries) > 32 else "-"
    print(f"  Fn(Win): {_nonzero(fn)} непустых;  Fn+T(idx32)={fn_pos32}")
    if st.get("actuation_raw"):
        values = sorted(set(st["actuation_raw"]))
        print(f"  активация: raw={values} ({values[0] / precision:g} мм)")
    if st.get("release_raw"):
        values = sorted(set(st["release_raw"]))
        print(f"  отпускание: raw={values} ({values[0] / precision:g} мм)")


def describe_backup(st: dict, precision: int = 100) -> list[str]:
    info = st.get("info") or {}
    lines = [f"profile={st.get('profile')} firmware={info.get('version')} "
             f"device_id={info.get('device_id')}"]
    lines.append("keymatrix: " + ", ".join(
        f"layer{layer}={_nonzero(st.get('keymatrix', {}).get(f'layer{layer}'))}"
        for layer in range(4)))
    lines.append(f"Fn(Win)={_nonzero(st.get('fn_win'))}")
    if st.get("actuation_raw"):
        lines.append(f"активация raw={sorted(set(st['actuation_raw']))} "
                     f"({st['actuation_raw'][0] / precision:g} мм)")
    if st.get("release_raw"):
        lines.append(f"отпускание raw={sorted(set(st['release_raw']))} "
                     f"({st['release_raw'][0] / precision:g} мм)")
    lines.append(f"userpic={'есть' if st.get('userpic_slot0') else 'нет'}")
    led = st.get("led")
    if led:
        mode = int(led[2:4], 16) if len(led) >= 4 else None
        lines.append(f"LED mode={mode}")
    return lines


def save_backup(st: dict, directory: str | Path) -> Path:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out / f"backup-{stamp}.json"
    counter = 1
    while path.exists():
        path = out / f"backup-{stamp}-{counter}.json"
        counter += 1
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def restore_state(kb, st: dict, key_count: int = KEY_COUNT,
                  userpic_slot: int = 0, log=print) -> dict:
    """Best-effort restore of the fields stored in a backup file.

    Keymatrix and Fn entries are written only where the current value differs.
    Only the Win Fn layer is restored (the backup format stores fn_win).
    """
    profile = int(st.get("profile", 0))
    result = {"written": 0, "failed": 0, "skipped": 0}

    for layer in range(4):
        blob_hex = st.get("keymatrix", {}).get(f"layer{layer}", "")
        if not blob_hex:
            result["skipped"] += 1
            continue
        want = bytes.fromhex(blob_hex)
        if len(want) < key_count * 4:
            result["skipped"] += 1
            continue
        current = kb.get_keymatrix(profile, layer) or b""
        changed = 0
        for idx in range(key_count):
            w = want[idx * 4:idx * 4 + 4]
            h = current[idx * 4:idx * 4 + 4]
            if w == h:
                continue
            if kb.set_keymatrix_verified(profile, idx, w[2], layer=layer):
                changed += 1
                result["written"] += 1
            else:
                result["failed"] += 1
        log(f"  keymatrix layer{layer}: изменено {changed}")

    fn_hex = st.get("fn_win", "")
    if fn_hex:
        want = bytes.fromhex(fn_hex)
        if len(want) >= key_count * 4:
            current = kb.get_fn(profile, 0) or b""
            changed = 0
            for idx in range(key_count):
                w = want[idx * 4:idx * 4 + 4]
                h = current[idx * 4:idx * 4 + 4]
                if w == h:
                    continue
                if kb.set_fn_verified(profile, idx, w[2], fn_sys=0):
                    changed += 1
                    result["written"] += 1
                else:
                    result["failed"] += 1
            log(f"  Fn(Win): изменено {changed}")
    else:
        result["skipped"] += 1

    if st.get("actuation_raw"):
        kb.set_magnetism(MAG_PRESS, st["actuation_raw"], key_count)
        result["written"] += key_count
        log(f"  активация: {sorted(set(st['actuation_raw']))}")
    if st.get("release_raw"):
        kb.set_magnetism(MAG_LIFT, st["release_raw"], key_count)
        result["written"] += key_count
        log(f"  отпускание: {sorted(set(st['release_raw']))}")

    if st.get("userpic_slot0"):
        kb.set_userpic(userpic_slot, bytes.fromhex(st["userpic_slot0"]))
        result["written"] += 1
        log("  userpic восстановлен")
        led_hex = st.get("led") or ""
        if len(led_hex) >= 16:
            kb.set_led_params(bytes.fromhex(led_hex)[1:8])
            log("  LED-параметры восстановлены")
        else:
            kb.set_led_userpic(userpic_slot)
            log("  LED: включён режим UserPicture (в бэкапе не было параметров)")
    return result
