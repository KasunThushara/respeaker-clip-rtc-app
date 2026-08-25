/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/fs/fs.h>
#include <ff.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/shell/shell.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sdcard.h"

LOG_MODULE_REGISTER(sdcard, LOG_LEVEL_INF);

static FATFS fat_fs;
static struct fs_mount_t mp = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};

static const char *disk_mount_pt = "/SD:";
static bool sd_mounted = false;

bool sdcard_is_mounted(void)
{
	return sd_mounted;
}

int sdcard_unmount(void)
{
	int rc;

	if (!sd_mounted) {
		return 0;
	}

	rc = fs_unmount(&mp);
	if (rc != 0) {
		LOG_ERR("Unmount failed: %d", rc);
		return rc;
	}

	sd_mounted = false;
	LOG_INF("SD card unmounted");
	return 0;
}

int sdcard_mount(void)
{
	int rc;

	if (sd_mounted) {
		return 0;
	}

	rc = disk_access_init("SD");
	if (rc != 0) {
		LOG_ERR("SD card init failed: %d", rc);
		return rc;
	}

	mp.mnt_point = disk_mount_pt;
	rc = fs_mount(&mp);
	if (rc != 0) {
		LOG_ERR("Mount failed: %d", rc);
		return rc;
	}

	sd_mounted = true;
	LOG_INF("SD card mounted at %s", mp.mnt_point);
	return 0;
}

/* Format SD card */
static int cmd_sd_format(const struct shell *sh, size_t argc, char **argv)
{
	int rc;

	if (sd_mounted) {
		shell_print(sh, "Unmounting SD card first...");
		rc = fs_unmount(&mp);
		if (rc != 0) {
			shell_error(sh, "Failed to unmount: %d", rc);
			return rc;
		}
		sd_mounted = false;
	}

	shell_print(sh, "Formatting SD card (this may take a while)...");

	/* Format the SD card */
	rc = fs_mkfs(FS_FATFS, (uintptr_t)disk_mount_pt, NULL, 0);
	if (rc != 0) {
		shell_error(sh, "Format failed: %d", rc);
		return rc;
	}

	shell_print(sh, "Format complete! Mounting...");

	/* Re-mount after format */
	mp.mnt_point = disk_mount_pt;
	rc = fs_mount(&mp);
	if (rc != 0) {
		shell_error(sh, "Mount failed after format: %d", rc);
		return rc;
	}

	sd_mounted = true;
	shell_print(sh, "SD card ready at %s", mp.mnt_point);

	return 0;
}

/* Speed test */
static int cmd_sd_speed(const struct shell *sh, size_t argc, char **argv)
{
	int rc;
	struct fs_file_t file;
	char *write_buf;
	char *read_buf;
	uint32_t file_size = 1024 * 1024; /* 1MB test file */
	uint32_t chunk_size = 4096;
	uint64_t start_time, end_time, write_time, read_time;

	if (!sd_mounted) {
		shell_error(sh, "SD card not mounted");
		return -ENODEV;
	}

	/* Parse optional file size argument */
	if (argc >= 2) {
		file_size = atoi(argv[1]) * 1024; /* Convert KB to bytes */
		if (file_size < 1024) file_size = 1024;
		if (file_size > 10 * 1024 * 1024) file_size = 10 * 1024 * 1024; /* Max 10MB */
	}

	shell_print(sh, "SD card speed test (file size: %u KB)...", file_size / 1024);

	/* Allocate buffers */
	write_buf = k_malloc(chunk_size);
	read_buf = k_malloc(chunk_size);
	if (!write_buf || !read_buf) {
		shell_error(sh, "Failed to allocate buffers");
		rc = -ENOMEM;
		goto cleanup;
	}

	/* Fill write buffer with pattern */
	for (uint32_t i = 0; i < chunk_size; i++) {
		write_buf[i] = (char)(i & 0xFF);
	}

	/* Write test */
	shell_print(sh, "Write test...");
	fs_file_t_init(&file);
	rc = fs_open(&file, "/SD:/speedtest.tmp", FS_O_CREATE | FS_O_WRITE);
	if (rc != 0) {
		shell_error(sh, "Failed to create file: %d", rc);
		goto cleanup;
	}

	start_time = k_uptime_get();
	uint32_t total_written = 0;
	while (total_written < file_size) {
		uint32_t to_write = chunk_size;
		if (total_written + to_write > file_size) {
			to_write = file_size - total_written;
		}

		rc = fs_write(&file, write_buf, to_write);
		if (rc < 0) {
			shell_error(sh, "Write failed: %d", rc);
			fs_close(&file);
			goto cleanup;
		}
		total_written += rc;
	}
	fs_close(&file);
	end_time = k_uptime_get();

	write_time = end_time - start_time;
	uint32_t write_speed_kb = (file_size / 1024 * 1000) / write_time; /* KB/s */

	/* Read test */
	shell_print(sh, "Read test...");
	rc = fs_open(&file, "/SD:/speedtest.tmp", FS_O_READ);
	if (rc != 0) {
		shell_error(sh, "Failed to open file: %d", rc);
		goto cleanup;
	}

	start_time = k_uptime_get();
	uint32_t total_read = 0;
	while (total_read < file_size) {
		uint32_t to_read = chunk_size;
		if (total_read + to_read > file_size) {
			to_read = file_size - total_read;
		}

		rc = fs_read(&file, read_buf, to_read);
		if (rc < 0) {
			shell_error(sh, "Read failed: %d", rc);
			fs_close(&file);
			goto cleanup;
		}
		total_read += rc;
	}
	fs_close(&file);
	end_time = k_uptime_get();

	read_time = end_time - start_time;
	uint32_t read_speed_kb = (file_size / 1024 * 1000) / read_time; /* KB/s */

	/* Print results */
	shell_print(sh, "");
	shell_print(sh, "=== SD Card Speed Test Results ===");
	shell_print(sh, "File size: %u KB", file_size / 1024);
	shell_print(sh, "Write: %u KB/s (%u ms)", write_speed_kb, (uint32_t)write_time);
	shell_print(sh, "Read:  %u KB/s (%u ms)", read_speed_kb, (uint32_t)read_time);
	shell_print(sh, "================================");

	/* Delete test file */
	fs_unlink("/SD:/speedtest.tmp");
	shell_print(sh, "Test file deleted");

	rc = 0;

cleanup:
	if (write_buf) k_free(write_buf);
	if (read_buf) k_free(read_buf);
	return rc;
}

/* ============================================================================
 * SD reliability test: write a pattern to a file, read back, verify
 * byte-for-byte. Multi-round + pattern sweep for repeated verification of a
 * new card. Test file SD_TEST_FILE is deleted after each pass. File-level
 * (FAT) -- tests the card through the same path the app uses.
 * ============================================================================ */
#define SD_TEST_FILE    "/SD:/sdtest.bin"
#define SD_TEST_CHUNK   4096

enum sd_pattern {
	SD_PAT_ZERO = 0, SD_PAT_FF, SD_PAT_55, SD_PAT_AA, SD_PAT_ADDR, SD_PAT_PRBS,
};

static const char *sd_pat_name(enum sd_pattern p)
{
	static const char *const names[] = {"00", "FF", "55", "AA", "addr", "prbs"};
	return names[p % 6];
}

/* Deterministic pattern fill of len bytes at absolute offset base_off. */
static void sd_fill_pattern(uint8_t *buf, uint32_t len, enum sd_pattern p, uint32_t base_off)
{
	switch (p) {
	case SD_PAT_ZERO:
		memset(buf, 0x00, len);
		break;
	case SD_PAT_FF:
		memset(buf, 0xFF, len);
		break;
	case SD_PAT_55:
		memset(buf, 0x55, len);
		break;
	case SD_PAT_AA:
		memset(buf, 0xAA, len);
		break;
	case SD_PAT_ADDR:
		for (uint32_t i = 0; i < len; i++) {
			buf[i] = (uint8_t)((base_off + i) & 0xFF);
		}
		break;
	case SD_PAT_PRBS:
		for (uint32_t i = 0; i < len; i++) {
			uint32_t o = base_off + i;
			/* deterministic LCG hash of the absolute offset */
			buf[i] = (uint8_t)(((o * 1103515245u) + 12345u) >> 16);
		}
		break;
	}
}

/* One write+verify pass over SD_TEST_FILE. Returns 0 on success (data
 * mismatches are counted in *errors, not a negative return), <0 on I/O
 * failure. Metrics out: errors, first_err_off (-1 if none), write/read ms. */
static int sd_run_pass(uint32_t size, enum sd_pattern pattern,
		       uint32_t *errors, int32_t *first_err_off,
		       uint32_t *write_ms, uint32_t *read_ms)
{
	struct fs_file_t file;
	static uint8_t wbuf[SD_TEST_CHUNK];
	static uint8_t rbuf[SD_TEST_CHUNK];
	int rc;
	uint32_t off;
	uint64_t t;

	*errors = 0;
	*first_err_off = -1;
	*write_ms = *read_ms = 0;

	/* Write */
	fs_file_t_init(&file);
	rc = fs_open(&file, SD_TEST_FILE, FS_O_CREATE | FS_O_WRITE);
	if (rc) {
		return -1;
	}
	t = k_uptime_get();
	for (off = 0; off < size; off += SD_TEST_CHUNK) {
		uint32_t n = (size - off < SD_TEST_CHUNK) ? (size - off) : SD_TEST_CHUNK;
		sd_fill_pattern(wbuf, n, pattern, off);
		rc = fs_write(&file, wbuf, n);
		if (rc < 0) {
			fs_close(&file);
			return -2;
		}
	}
	fs_close(&file);
	*write_ms = (uint32_t)(k_uptime_get() - t);

	/* Read + verify */
	rc = fs_open(&file, SD_TEST_FILE, FS_O_READ);
	if (rc) {
		return -3;
	}
	t = k_uptime_get();
	for (off = 0; off < size; off += SD_TEST_CHUNK) {
		uint32_t n = (size - off < SD_TEST_CHUNK) ? (size - off) : SD_TEST_CHUNK;
		int got = fs_read(&file, rbuf, n);
		if (got < 0) {
			fs_close(&file);
			return -4;
		}
		sd_fill_pattern(wbuf, got, pattern, off);  /* expected */
		for (int i = 0; i < got; i++) {
			if (rbuf[i] != wbuf[i]) {
				(*errors)++;
				if (*first_err_off < 0) {
					*first_err_off = (int32_t)(off + i);
				}
			}
		}
		if (got < (int)n) {
			break;  /* short read (EOF) */
		}
	}
	fs_close(&file);
	*read_ms = (uint32_t)(k_uptime_get() - t);

	fs_unlink(SD_TEST_FILE);  /* delete after */
	return 0;
}

/* sd verify [size_kb] [pattern] -- single write+verify pass */
static int cmd_sd_verify(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t size = 1024 * 1024;
	enum sd_pattern pattern = SD_PAT_PRBS;
	uint32_t errors, wms, rms;
	int32_t first;
	int rc;

	if (!sd_mounted) {
		shell_error(sh, "SD card not mounted");
		return -ENODEV;
	}
	if (argc >= 2) {
		size = (uint32_t)atoi(argv[1]) * 1024;
	}
	if (argc >= 3) {
		pattern = (enum sd_pattern)atoi(argv[2]);
	}
	if (size < SD_TEST_CHUNK) {
		size = SD_TEST_CHUNK;
	}

	rc = sd_run_pass(size, pattern, &errors, &first, &wms, &rms);
	if (rc < 0) {
		shell_error(sh, "verify I/O failed: %d", rc);
		return rc;
	}
	shell_print(sh, "verify %s %uKB: %s  err=%u  W=%uKB/s(%ums) R=%uKB/s(%ums)",
		    sd_pat_name(pattern), size / 1024, errors ? "FAIL" : "OK", errors,
		    wms ? (size / 1024 * 1000 / wms) : 0, wms,
		    rms ? (size / 1024 * 1000 / rms) : 0, rms);
	if (errors && first >= 0) {
		shell_print(sh, "  first error @0x%x", first);
	}
	return errors ? -EIO : 0;
}

/* sd test <rounds> [size_kb] -- multi-round write+verify (prbs), per-round
 * output for cross-run comparison. */
static int cmd_sd_test(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t rounds = 10;
	uint32_t size = 1024 * 1024;
	uint32_t total_err = 0, fails = 0;

	if (!sd_mounted) {
		shell_error(sh, "SD card not mounted");
		return -ENODEV;
	}
	if (argc >= 2) {
		rounds = (uint32_t)atoi(argv[1]);
	}
	if (argc >= 3) {
		size = (uint32_t)atoi(argv[2]) * 1024;
	}
	if (rounds == 0) {
		rounds = 1;
	}
	if (size < SD_TEST_CHUNK) {
		size = SD_TEST_CHUNK;
	}

	shell_print(sh, "=== SD reliability: %u rounds, %u KB/round, pattern=prbs ===",
		    rounds, size / 1024);

	for (uint32_t r = 1; r <= rounds; r++) {
		uint32_t errors, wms, rms;
		int32_t first;
		int rc = sd_run_pass(size, SD_PAT_PRBS, &errors, &first, &wms, &rms);

		if (rc < 0) {
			shell_print(sh, "Round %2u: ERROR  pass=%d", r, rc);
			fails++;
			total_err++;
			continue;
		}
		if (errors) {
			fails++;
			total_err += errors;
			shell_print(sh, "Round %2u: FAIL  W=%uKB/s R=%uKB/s  err=%u first@0x%x",
				    r,
				    wms ? (size / 1024 * 1000 / wms) : 0,
				    rms ? (size / 1024 * 1000 / rms) : 0,
				    errors, first);
		} else {
			shell_print(sh, "Round %2u: OK    W=%uKB/s R=%uKB/s",
				    r,
				    wms ? (size / 1024 * 1000 / wms) : 0,
				    rms ? (size / 1024 * 1000 / rms) : 0);
		}
	}

	shell_print(sh, "=== Summary: %u rounds, %u KB total, %u errors, %u failed ===",
		    rounds, rounds * size / 1024, total_err, fails);
	return fails ? -EIO : 0;
}

/* sd patterns [size_kb] -- sweep all patterns, one pass each */
static int cmd_sd_patterns(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t size = 1024 * 1024;
	static const enum sd_pattern pats[] = {
		SD_PAT_ZERO, SD_PAT_FF, SD_PAT_55, SD_PAT_AA, SD_PAT_ADDR, SD_PAT_PRBS,
	};
	uint32_t total_err = 0;

	if (!sd_mounted) {
		shell_error(sh, "SD card not mounted");
		return -ENODEV;
	}
	if (argc >= 2) {
		size = (uint32_t)atoi(argv[1]) * 1024;
	}
	if (size < SD_TEST_CHUNK) {
		size = SD_TEST_CHUNK;
	}

	shell_print(sh, "=== SD pattern sweep: %u KB, %u patterns ===",
		    size / 1024, (uint32_t)(ARRAY_SIZE(pats)));

	for (uint32_t k = 0; k < ARRAY_SIZE(pats); k++) {
		uint32_t errors, wms, rms;
		int32_t first;
		int rc = sd_run_pass(size, pats[k], &errors, &first, &wms, &rms);
		if (rc < 0) {
			shell_print(sh, "  %-4s: I/O ERROR %d", sd_pat_name(pats[k]), rc);
			total_err++;
			continue;
		}
		if (errors) {
			total_err += errors;
			shell_print(sh, "  %-4s: FAIL  err=%u first@0x%x",
				    sd_pat_name(pats[k]), errors, first);
		} else {
			shell_print(sh, "  %-4s: OK", sd_pat_name(pats[k]));
		}
	}
	shell_print(sh, "=== Summary: %u total errors across patterns ===", total_err);
	return total_err ? -EIO : 0;
}

/* Shell command to show SD card status */
static int cmd_sd_status(const struct shell *sh, size_t argc, char **argv)
{
	if (sd_mounted) {
		shell_print(sh, "SD card status: MOUNTED at %s", disk_mount_pt);
	} else {
		shell_print(sh, "SD card status: NOT MOUNTED");
	}

	return 0;
}

/* Mount SD card */
static int cmd_sd_mount(const struct shell *sh, size_t argc, char **argv)
{
	if (sd_mounted) {
		shell_print(sh, "SD card already mounted at %s", disk_mount_pt);
		return 0;
	}

	shell_print(sh, "Mounting SD card...");
	int rc = sdcard_mount();
	if (rc != 0) {
		shell_error(sh, "Mount failed: %d (not formatted?)", rc);
		shell_print(sh, "Use 'sd format' to format the SD card");
	}

	return rc;
}

/* Unmount SD card */
static int cmd_sd_umount(const struct shell *sh, size_t argc, char **argv)
{
	if (!sd_mounted) {
		shell_print(sh, "SD card not mounted");
		return 0;
	}

	shell_print(sh, "Unmounting SD card...");
	int rc = sdcard_unmount();
	if (rc != 0) {
		shell_error(sh, "Unmount failed: %d", rc);
	} else {
		shell_print(sh, "SD card unmounted");
	}

	return rc;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sd_cmds,
	SHELL_CMD(mount, NULL, "Mount SD card", cmd_sd_mount),
	SHELL_CMD(umount, NULL, "Unmount SD card", cmd_sd_umount),
	SHELL_CMD(format, NULL, "Format SD card as FAT32", cmd_sd_format),
	SHELL_CMD_ARG(speed, NULL, "Speed test [size_kb]", cmd_sd_speed, 1, 1),
	SHELL_CMD_ARG(verify, NULL, "Reliability verify [size_kb] [pattern 0-5]", cmd_sd_verify, 0, 2),
	SHELL_CMD_ARG(test, NULL, "Multi-round reliability <rounds> [size_kb]", cmd_sd_test, 1, 2),
	SHELL_CMD_ARG(patterns, NULL, "Pattern sweep [size_kb]", cmd_sd_patterns, 0, 1),
	SHELL_CMD(status, NULL, "Show SD card status", cmd_sd_status),
	SHELL_SUBCMD_SET_END
);

SHELL_CMD_REGISTER(sd, &sd_cmds, "SD card commands", NULL);

int sdcard_init(void)
{
	LOG_INF("Initializing SD card...");

	/* Enable SD card power via NPM1300 LDO2 */
	const struct device *ldo2 = DEVICE_DT_GET(DT_NODELABEL(npm1300_ldo2));
	if (device_is_ready(ldo2)) {
		regulator_enable(ldo2);
		k_sleep(K_MSEC(5));
		LOG_INF("SD card power enabled (LDO2)");
	} else {
		LOG_WRN("LDO2 not ready");
	}

	int rc = sdcard_mount();
	if (rc != 0) {
		LOG_WRN("SD card mount failed: %d (not formatted?)", rc);
		LOG_INF("Use 'sd format' to format the SD card as FAT32");
		return 0;
	}

	LOG_INF("Commands: sd status, sd speed, sd verify, sd test <rounds>, sd patterns, sd format");
	return 0;
}
