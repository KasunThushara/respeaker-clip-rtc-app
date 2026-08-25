# Current AT and BLE contract

Read `applications/clip/src/at_commands.c` before making protocol claims. The
registered command list is the source of truth; `docs/protocol.md` must follow
it.

## Syntax and response

```text
AT+COMMAND
AT+COMMAND?
AT+COMMAND=value
```

- Normal success: `{"ok":true,"data":...}`.
- Failure: `{"ok":false,"msg":"..."}`. Do not use an `error` field or
  invent numeric host error codes.
- `AT+VERSION` and `AT+DEVICE` have top-level payload fields.
- `AT+PAIR?` is exceptional: its pairing text is returned in `msg`.

## Registered commands

| Group | Commands |
|---|---|
| Status | `GSTAT`, `BATT`, `STORAGE`, `DEVICE`, `VERSION`, `TIME` |
| Settings | `MODE`, `AUTODEL`, `BRIGHTNESS`, `NAME`, `LOG`, `WIFICFG` |
| Recording | `START`, `STOP`, `PAUSE`, `RESUME`, `MARK` |
| Sessions | `LIST`, `MARKS`, `DOWNLOAD`, `CANCEL`, `DELETE`, `FORMAT` |
| System | `POWEROFF`, `FACTORY`, `PAIR`, `REBOOT`, `DFU` |
| Interfaces | `WIFI`, `USB` |

Do not add host wrappers for removed runtime controls (`BITRATE`, `COMPLEXITY`,
`NOISE`, `AGC`, `DEREVERB`, `PURGE`, or `PROGRESS`). Normal/enhanced codec and
DSP behavior are firmware configuration, not an AT tuning interface.

## Session and download validation

- A session ID is exactly 14 decimal digits: `YYYYMMDDHHMMSS`.
- `LIST` supports `AT+LIST`, `AT+LIST?page&per_page`, `AT+LIST=<session>`, and
  `AT+LIST=<session>?page&per_page`.
- A logical file name is exactly `NNNN.opus`, starting at `0001.opus`.
- `DOWNLOAD` accepts `AT+DOWNLOAD=<session>` or
  `AT+DOWNLOAD=<session>:NNNN.opus`. A slash separator is not valid.
- Validate all input before touching the SD card or starting a transfer.

## BLE GATT transfer

Service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` uses command write `...0002`,
JSON notify `...0003`, file-data notify `...0004`, and audio visualization
`...0005`.

BLE file frames:

```text
DATA          0x01 [seq:u16 LE][len:u16 LE][payload]
FILE_START    0x10 [name_len:u8][name][size:u32 LE]
FILE_END      0x11 [file_crc32:u32 LE]
TRANSFER_DONE 0x12 [sid_len:u8][session][count:u32 LE]
```

BLE has no application ACK, but clients must check final file length and CRC32.
Serialize host commands: the protocol carries no request identifier, so after a
timeout reconnect before issuing a new command.
