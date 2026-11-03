# HID-протокол AK680 MAX (подмножество, используемое репозиторием)

Источник: публичная документация monsgeek/akko (`docs/PROTOCOL.md`) и
проверки на этой плате (RY5088, прошивка v306). Здесь описано только то, что
реально использует код.

## Интерфейс

- Вид: HID feature reports.
- Конфигурационный интерфейс: `usage_page = 0xFFFF`, `usage = 0x02`.
- VID:PID: `3151:502D`.
- Драйвер: стандартный HID Windows, вендорский драйвер не нужен.

## Формат отчёта

64-байтовый feature report + report id:

```
[0]      report_id = 0
[1]      command
[2..64]  payload (63 байта)
[8]      checksum (обычные команды)
[9]      checksum (LED-команды, bit8)
```

Checksum:

```
обычный:  buf[8] = 255 - (sum(buf[1:8]) & 0xFF) & 0xFF
bit8:     buf[9] = 255 - (sum(buf[1:9]) & 0xFF) & 0xFF
```

Ответ читается как 65 байт; `response[0]` — report id, `response[1:]` — payload.

Два вида ответов:

- **echo** — `payload[0] == command` (например, `GET_PROFILE`);
- **page** — ровно 64 байта данных без эха (например, `GET_KEYMATRIX`).

## Команды

| Код | Имя | Назначение |
|---|---|---|
| `0x01` | `SET_RESET` | **не используется и запрещён** |
| `0x07` | `SET_LEDPARAM` | параметры LED (bit8 checksum) |
| `0x0A` | `SET_KEYMATRIX` | запись 4-байтовой записи keymatrix |
| `0x0C` | `SET_USERPIC` | запись страницы userpic |
| `0x10` | `SET_FN` | запись записи Fn-слоя |
| `0x65` | `SET_MULTI_MAGNETISM` | запись страницы порогов магнитов |
| `0x84` | `GET_PROFILE` | активный профиль |
| `0x87` | `GET_LEDPARAM` | текущие параметры LED |
| `0x8A` | `GET_KEYMATRIX` | чтение страницы keymatrix |
| `0x8C` | `GET_USERPIC` | чтение блока userpic |
| `0x8F` | `GET_USB_VERSION` | device_id + версия прошивки |
| `0x90` | `GET_FN` | чтение страницы Fn-слоя |
| `0xE5` | `GET_MULTI_MAGNETISM` | чтение страницы магнитов |

## Keymatrix

Чтение:

```
payload = [profile, 0xFF, page, layer]
pages = 6
```

Каждая запись — 4 байта; HID-код лежит в третьем байте (`entry[2]`).
Запись:

```
payload = [profile, idx, 0, 0, enabled, layer, 0, 0, 0, hid_code, 0]
```

После записи код обязательно читает запись назад: прошивка иногда «глотает»
подряд идущие `SET_KEYMATRIX`. Повторы — до 8 раз с паузой 0.15 с.

## Fn-слой

Чтение:

```
payload = [sysmode, profile, 0xFF, page]
pages = 6
```

`sysmode = 0` — Windows (в бэкапе это `fn_win`). Запись:

```
payload = [fn_sys, profile, idx, 0, 0, 0, 0, 0, 0, hid_code, 0]
```

## Hall Effect (магниты)

Чтение:

```
payload = [sub, 0x01, page]
pages = 3
sub: 0x00 — активация, 0x01 — отпускание, 0x07 — режим
```

Значения — little-endian `uint16`, по одному на позицию матрицы. Для v306
`precision = 100`, то есть 1.0 мм = raw 100.

Запись:

```
payload = [sub, 0x01, page, is_last, 0, 0, 0] + chunk
chunk   = до 56 байт (28 значений)
```

Последняя страница пишется с задержкой 0.25 с.

## Userpic (подсветка)

Слот хранит до 21×6 позиций; эта плата использует 15×6 = 90 позиций, 378 байт.
Байты `[3*i : 3*i+3]` — цвет позиции `i` в порядке **электрической матрицы**,
column-major: `x = i // 6`, `y = i % 6`. Это не физические ряды клавиатуры.

Запись:

```
payload = [slot, 0xFF, page, len(chunk), is_last, 0, 0] + chunk
pages   = 7 (по 56 байт)
```

Чтение:

```
payload = [slot, 0xFF, block]
blocks  = 6 (по 64 байта; используется 378)
```

## LED-параметры

Запись (bit8 checksum):

```
payload = [mode, speed, brightness, option, r, g, b]
```

Для режима `13` (UserPicture) `option = (slot << 4) & 0xF0`, а `r,g,b` — цвет
вспышки при нажатии. Ответ `GET_LEDPARAM` — echo-байт `0x87` + те же 7 полей,
поэтому режим в ответе лежит по индексу 1.

## Версия прошивки

`GET_USB_VERSION` (echo):

```
device_id = little-endian uint32 из payload[1:5]
version   = little-endian uint16 из payload[7:9]
```

Версия `0x0306` печатается как `v306`.

## Ограничения

- Документ описывает только команды, используемые в `src/ak680_max`.
- `SET_RESET` (`0x01`) не вызывается: это не нужно для записи профиля и
  потенциально опасно.
- Поведение других прошивок не гарантируется; перед записью — `status`.
