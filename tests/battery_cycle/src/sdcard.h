/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef SDCARD_H_
#define SDCARD_H_

/**
 * @brief Initialize SD card and register shell commands
 * Shell commands:
 *   sd mount  - Mount SD card
 *   sd umount - Unmount SD card
 *   sd status - Show SD card status
 *
 * @return 0 on success, negative error code on failure
 */
int sdcard_init(void);

bool sdcard_is_mounted(void);
int sdcard_mount(void);
int sdcard_unmount(void);

/**
 * @brief Enable/disable the continuous SD-read discharge load
 *
 * On first enable, writes a fixed 1 MB read file ONCE (then pure read, no NAND
 * wear). A background thread reads it in a loop while enabled, adding ~15-25 mA
 * (card read + SPI4 + CPU) on top of the WiFi TX load for faster discharge.
 * @param enable true to run the read load (discharge), false to idle (charge)
 * @return 0
 */
int sdcard_discharge_load_enable(bool enable);

#endif /* SDCARD_H_ */
