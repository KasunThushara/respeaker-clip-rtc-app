/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/fs/fs.h>
#include <zephyr/logging/log.h>
#include <string.h>

#include "re_test.h"
#include "sdcard.h"
#include "oled.h"
#include "motor.h"
#include "pmic.h"
#include "mic.h"
#include "wifi.h"
#include "ble.h"

LOG_MODULE_REGISTER(re_test, LOG_LEVEL_INF);

#define NUM_TESTS 8
#define FLASH_TEST_OFFSET 0x130000

#define MIC_SAMPLE_RATE 16000
#define MIC_SAMPLE_BITS 16
#define MIC_CHANNELS 2
#define MIC_CAPTURE_MS 100
#define MIC_BLOCK_SIZE (((MIC_SAMPLE_BITS / 8) * (MIC_SAMPLE_RATE * MIC_CAPTURE_MS)) / 1000) * MIC_CHANNELS
#define MIC_BLOCK_COUNT 4

K_MEM_SLAB_DEFINE_STATIC(re_mic_slab, MIC_BLOCK_SIZE, MIC_BLOCK_COUNT, 4);

static struct re_test_stats stats[NUM_TESTS] = {
	{ "SD Card",  0, 0 },
	{ "Flash",    0, 0 },
	{ "OLED",     0, 0 },
	{ "Motor",    0, 0 },
	{ "PMIC",     0, 0 },
	{ "MIC",      0, 0 },
	{ "WiFi AP",  0, 0 },
	{ "BLE",      0, 0 },
};

static uint32_t round_count;
static volatile bool stop_requested;

typedef int (*re_test_fn)(void);

/* --- Test wrappers --- */

static int test_sd(void)
{
	int rc;

	if (!sdcard_is_mounted()) {
		rc = sdcard_mount();
		if (rc != 0) {
			return rc;
		}
	}

	struct fs_file_t file;
	char write_buf[256];
	char read_buf[256];

	for (int i = 0; i < sizeof(write_buf); i++) {
		write_buf[i] = (char)(i & 0xFF);
	}

	fs_file_t_init(&file);
	rc = fs_open(&file, "/SD:/re_test.tmp", FS_O_CREATE | FS_O_WRITE | FS_O_RDWR);
	if (rc != 0) {
		return rc;
	}

	rc = fs_write(&file, write_buf, sizeof(write_buf));
	fs_close(&file);
	if (rc < 0) {
		return rc;
	}

	fs_file_t_init(&file);
	rc = fs_open(&file, "/SD:/re_test.tmp", FS_O_READ);
	if (rc != 0) {
		return rc;
	}

	rc = fs_read(&file, read_buf, sizeof(read_buf));
	fs_close(&file);

	fs_unlink("/SD:/re_test.tmp");

	if (rc < 0) {
		return rc;
	}

	if (memcmp(write_buf, read_buf, sizeof(write_buf)) != 0) {
		return -EIO;
	}

	return 0;
}

static int test_flash(void)
{
	const struct device *flash_dev;
	uint8_t write_buf[256];
	uint8_t read_buf[256];
	int rc;

	flash_dev = DEVICE_DT_GET(DT_NODELABEL(spi_flash));
	if (!device_is_ready(flash_dev)) {
		return -ENODEV;
	}

	for (int i = 0; i < sizeof(write_buf); i++) {
		write_buf[i] = (uint8_t)(i ^ 0xAA);
	}

	rc = flash_erase(flash_dev, FLASH_TEST_OFFSET, 4096);
	if (rc != 0) {
		return rc;
	}

	rc = flash_write(flash_dev, FLASH_TEST_OFFSET, write_buf, sizeof(write_buf));
	if (rc != 0) {
		return rc;
	}

	rc = flash_read(flash_dev, FLASH_TEST_OFFSET, read_buf, sizeof(read_buf));
	if (rc != 0) {
		return rc;
	}

	if (memcmp(write_buf, read_buf, sizeof(write_buf)) != 0) {
		return -EIO;
	}

	return 0;
}

static int test_oled(void)
{
	oled_run_all_tests();
	return 0;
}

static int test_motor(void)
{
	int rc = motor_set(true);
	if (rc != 0) {
		return rc;
	}
	k_msleep(100);
	rc = motor_set(false);
	return rc;
}

static int test_pmic(void)
{
	uint32_t voltage_mv;
	uint8_t percent;
	bool charging;
	int32_t temp;

	int rc = pmic_get_battery_status(&voltage_mv, &percent, &charging, &temp);
	if (rc != 0) {
		return rc;
	}

	if (voltage_mv == 0) {
		return -EIO;
	}

	LOG_INF("  PMIC: %u mV, %u%%, %s, %dC", voltage_mv, percent,
		charging ? "charging" : "discharging", temp);
	return 0;
}

static int test_mic(void)
{
	const struct device *dmic_dev;
	void *buffer = NULL;
	uint32_t size;
	int ret;

	dmic_dev = DEVICE_DT_GET(DT_ALIAS(dmic0));
	if (!device_is_ready(dmic_dev)) {
		return -ENODEV;
	}

	mic_power_on();

	struct pcm_stream_cfg stream = {
		.pcm_rate = MIC_SAMPLE_RATE,
		.pcm_width = MIC_SAMPLE_BITS,
		.block_size = MIC_BLOCK_SIZE,
		.mem_slab = &re_mic_slab,
	};
	struct dmic_cfg cfg = {
		.io = {
			.min_pdm_clk_freq = 1000000,
			.max_pdm_clk_freq = 3500000,
			.min_pdm_clk_dc = 40,
			.max_pdm_clk_dc = 60,
		},
		.streams = &stream,
		.channel = {
			.req_num_streams = 1,
			.req_num_chan = MIC_CHANNELS,
			.req_chan_map_lo =
				dmic_build_channel_map(0, 0, PDM_CHAN_LEFT) |
				dmic_build_channel_map(1, 0, PDM_CHAN_RIGHT),
		},
	};

	ret = dmic_configure(dmic_dev, &cfg);
	if (ret < 0) {
		goto cleanup;
	}

	ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_START);
	if (ret < 0) {
		goto cleanup;
	}

	ret = dmic_read(dmic_dev, 0, &buffer, &size, 2000);
	dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);

	if (ret < 0 || buffer == NULL) {
		ret = ret < 0 ? ret : -EIO;
		goto cleanup;
	}

	/* Check for non-zero samples */
	int16_t *samples = (int16_t *)buffer;
	uint32_t num_samples = size / sizeof(int16_t);
	int32_t sum = 0;
	for (uint32_t i = 0; i < num_samples; i++) {
		sum += (int32_t)samples[i] > 0 ? samples[i] : -samples[i];
	}

	if (sum == 0) {
		ret = -EIO;
	}

	LOG_INF("  MIC: %u samples, avg_abs=%d", num_samples,
		num_samples > 0 ? (int)(sum / num_samples) : 0);

cleanup:
	if (buffer) {
		k_mem_slab_free(&re_mic_slab, buffer);
	}
	mic_power_off();
	return ret;
}

static int test_wifi(void)
{
	if (wifi_ap_is_running()) {
		return 0;
	}
	return -EIO;
}

static int test_ble(void)
{
	return 0;
}

static re_test_fn test_fns[NUM_TESTS] = {
	test_sd,
	test_flash,
	test_oled,
	test_motor,
	test_pmic,
	test_mic,
	test_wifi,
	test_ble,
};

/* --- OLED status display --- */

static void oled_show_status(int test_idx, bool pass)
{
	oled_test_clear();
	if (pass) {
		oled_test_pattern();
	} else {
		oled_test_fill();
	}
}

/* --- Summary print --- */

static void print_summary(void)
{
	uint32_t total_pass = 0, total_fail = 0;

	printk("\n=== RE Test Round #%u ===\n", round_count);
	for (int i = 0; i < NUM_TESTS; i++) {
		printk("  %-10s: %s\n", stats[i].name,
		       (stats[i].fail > 0 && stats[i].pass == 0) ? "FAIL" : "PASS");

		total_pass += stats[i].pass;
		total_fail += stats[i].fail;
	}

	printk("--- Round #%u done ---\n", round_count);
	printk("Running totals: %u pass, %u fail, %u rounds\n\n",
	       total_pass, total_fail, round_count);
}

/* --- Main test loop --- */

void re_test_request_stop(void)
{
	stop_requested = true;
}

void re_test_loop(void)
{
	printk("\n====== RE Test Starting ======\n");
	printk("Testing %d peripherals in infinite loop\n\n", NUM_TESTS);

	while (!stop_requested) {
		round_count++;

		for (int i = 0; i < NUM_TESTS && !stop_requested; i++) {
			int rc = test_fns[i]();

			if (rc == 0) {
				stats[i].pass++;
				LOG_INF("[%s] PASS", stats[i].name);
			} else {
				stats[i].fail++;
				LOG_INF("[%s] FAIL (err=%d)", stats[i].name, rc);
			}

			oled_show_status(i, rc == 0);
			k_sleep(K_MSEC(500));
		}

		print_summary();
		oled_test_clear();
	}
}
