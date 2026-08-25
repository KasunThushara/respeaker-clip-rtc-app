# SD recording storage

`storage.c` owns FATFS at `/SD:` and treats the physical directory layout as an
implementation detail. AT and SDK clients must use a 14-digit session ID and
logical `NNNN.opus` chunk names only.

## Physical layout

For session `20260716022113`, current storage is:

```text
/SD:/REC/20260716/02/21/13/
  session.json
  marks.bin
  0/0001.opus
  0/0002.opus
  1/....opus
```

The trailing `SS` directory is the session root. Chunk group is
`(chunk_index - 1) / CONFIG_CLIP_STORAGE_FILES_PER_GROUP`; grouping prevents a
large FAT directory from slowing recording and listing. Never reconstruct paths
outside `storage_build_chunk_path()` or the storage APIs.

## Lifecycle and metadata

`storage_create_session()` creates metadata and directories. Audio opens/writes
chunks through `storage_create_file()` and `storage_write_file()`; closing a
chunk signals transfer readiness. `storage_close_session()` finalizes
`session.json`.

`session.json` stores file count, byte count, synchronized file count, channel
count, sample rate, and mode. Use it before walking directories; a directory
scan is fallback/recovery logic.

## Low-power lifecycle

When storage is idle and not recording, transferring, USB-MSC mounted, or FS
logging, firmware unmounts FATFS, deinitializes the disk, suspends SPI4, parks
CS low, and disables NPM1300 LDO2. New storage access must use
`storage_ensure_mounted()`; never assume LDO2 or SPI4 is ready after idle.
