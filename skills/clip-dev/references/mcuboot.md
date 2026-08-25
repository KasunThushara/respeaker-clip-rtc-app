# MCUboot and sysbuild

The Clip board owns the default sysbuild configuration. Read
`boards/seeed/clip/Kconfig.sysbuild` and `boards/seeed/clip/sysbuild/` before
changing boot, signing, partitions, or network-core behavior.

- MCUboot is overwrite-only and signs the application with the board RSA key.
- The network core runs IPC radio/BLE and has its own ECDSA signing key.
- External SPI flash stores the OTA secondary images; static partition layout is
  board-provided.
- Do not replace board signing keys or add per-app sysbuild files casually:
  devices already contain the matching public key material.

For a custom app, start with `docs/custom_app_guide.md`. Build pristine after
any sysbuild change and use recovery flashing only when the operation requires
erasing existing secure images.
