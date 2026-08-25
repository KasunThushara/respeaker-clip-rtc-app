/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * PM_STATE_SUSPEND_TO_RAM test for reSpeaker Clip (nRF5340) with the
 * peripheral rails turned off. No nRF7002 / MPSL / WiFi / BT stack.
 *
 * Tests SD card mount/unmount/poweroff in a loop every 30s to verify
 * current returns to ~250µA after each cycle.
 *
 * Measure with a Power Profiler Kit on the 3V3 rail.
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/pm.h>
#include <zephyr/pm/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/sys/__assert.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/dt-bindings/regulator/npm13xx.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/fs/fs.h>
#include <ff.h>

LOG_MODULE_REGISTER(suspend_to_ram, LOG_LEVEL_INF);

#define SUSPEND_INDICATE_PIN 15
#define SUSPEND_INDICATE_PORT gpio1
#define SPI4_CS_PIN          9  /* gpio0.9 - SD card CS (active-low) */

static const struct device *gpio0 = DEVICE_DT_GET(DT_NODELABEL(gpio0));
static const struct device *gpio1 = DEVICE_DT_GET(DT_NODELABEL(gpio1));
static const struct device *buck2 = DEVICE_DT_GET(DT_NODELABEL(npm1300_buck2));
static const struct device *ldo1  = DEVICE_DT_GET(DT_NODELABEL(npm1300_ldo1));
static const struct device *ldo2  = DEVICE_DT_GET(DT_NODELABEL(npm1300_ldo2));
static const struct device *spi4  = DEVICE_DT_GET(DT_NODELABEL(spi4));

static FATFS fat_fs;
static struct fs_mount_t mp = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
	.mnt_point = "/SD:",
};

static void on_pm_state_entry(enum pm_state state)
{
	if (state == PM_STATE_SUSPEND_TO_RAM) {
		gpio_pin_set(SUSPEND_INDICATE_PORT, SUSPEND_INDICATE_PIN, 1);
	}
}

static void on_pm_state_exit(enum pm_state state)
{
	ARG_UNUSED(state);
	gpio_pin_set(SUSPEND_INDICATE_PORT, SUSPEND_INDICATE_PIN, 0);
}

static struct pm_notifier notifier = {
	.state_entry = on_pm_state_entry,
	.state_exit = on_pm_state_exit,
};

/*
 * Suspend SPI4 so pinctrl applies the sleep state (pins disconnected +
 * pulled down). Also park CS as input+pull-down to prevent leakage
 * through the unpowered SD card's ESD diodes.
 */
static void spi4_suspend(void)
{
	gpio_pin_configure(gpio0, SPI4_CS_PIN, GPIO_INPUT | GPIO_PULL_DOWN);
	pm_device_action_run(spi4, PM_DEVICE_ACTION_SUSPEND);
	LOG_INF("SPI4 suspended (sleep pinctrl)");
}

/*
 * Resume SPI4 so pinctrl restores the default state (SCK/MOSI/MISO
 * back in SPIM function). Restore CS as output with GPIO_ACTIVE_LOW
 * preserved — physical HIGH = deselected.
 */
static void spi4_resume(void)
{
	pm_device_action_run(spi4, PM_DEVICE_ACTION_RESUME);
	gpio_pin_configure(gpio0, SPI4_CS_PIN,
			   GPIO_OUTPUT_HIGH | GPIO_ACTIVE_LOW);
	LOG_INF("SPI4 resumed (default pinctrl)");
}

static void shutdown_peripheral_rails(void)
{
	/* OLED_EN kept ON for display test */

	if (device_is_ready(ldo1)) {
		regulator_disable(ldo1);
		LOG_INF("LDO1 (mic) disabled");
	}
	if (device_is_ready(ldo2)) {
		regulator_disable(ldo2);
		LOG_INF("LDO2 (SD) disabled");
	}
	if (device_is_ready(buck2)) {
		/* PFM skipped for baseline test */
		LOG_INF("BUCK2 PFM skipped");
	}

	spi4_suspend();

	/* Park all SPI flash pins as input+pull-down to prevent leakage */
	static const uint8_t flash_pins[] = {19, 20, 21, 22, 23, 24};
	for (int i = 0; i < ARRAY_SIZE(flash_pins); i++) {
		gpio_pin_configure(gpio0, flash_pins[i],
				   GPIO_INPUT | GPIO_PULL_DOWN);
	}
	/* P0.27 flash VDD — drive low since regulator-fixed is disabled */
	gpio_pin_configure(gpio0, 27, GPIO_OUTPUT_INACTIVE);
	LOG_INF("Flash pins parked (P0.19-24 input+pd, P0.27 output low)");
}

static int test_sd_card(void)
{
	int rc;
	struct fs_statvfs stat;

	memset(&fat_fs, 0, sizeof(fat_fs));

	/* Power on SD card */
	if (device_is_ready(ldo2)) {
		regulator_enable(ldo2);
		k_msleep(100);
		LOG_INF("LDO2 (SD) enabled");
	}

	/* Restore SPI4 pins to SPI function */
	spi4_resume();

	rc = disk_access_init("SD");
	if (rc) {
		LOG_ERR("disk_access_init failed: %d", rc);
		goto power_off;
	}
	LOG_INF("SD disk initialized");

	rc = fs_mount(&mp);
	if (rc) {
		LOG_ERR("fs_mount failed: %d", rc);
		goto power_off;
	}
	LOG_INF("SD mounted");

	rc = fs_statvfs("/SD:", &stat);
	if (rc == 0) {
		LOG_INF("SD: %u MB free",
			(unsigned)(stat.f_bfree * stat.f_bsize / (1024 * 1024)));
	}

	struct fs_file_t file;

	fs_file_t_init(&file);
	rc = fs_open(&file, "/SD:/test_suspend.txt", FS_O_WRITE | FS_O_CREATE | FS_O_TRUNC);
	if (rc == 0) {
		fs_write(&file, "SD card test before suspend\n", 28);
		fs_close(&file);
		LOG_INF("Test file written");
	}

	rc = fs_unmount(&mp);
	if (rc) {
		LOG_ERR("fs_unmount failed: %d", rc);
		goto power_off;
	}
	LOG_INF("SD unmounted");

	disk_access_ioctl("SD", DISK_IOCTL_CTRL_DEINIT, NULL);
	LOG_INF("SD disk deinitialized");

	k_msleep(100);

power_off:
	if (device_is_ready(ldo2)) {
		regulator_disable(ldo2);
		LOG_INF("LDO2 (SD) disabled");
	}

	spi4_suspend();

	LOG_INF("SD card cycle complete");
	return rc;
}

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
	BT_DATA_BYTES(BT_DATA_NAME_COMPLETE, 'C', 'l', 'i', 'p'),
};

static void bt_ready(int err)
{
	if (err) {
		LOG_ERR("Bluetooth init failed: %d", err);
		return;
	}
	LOG_INF("Bluetooth initialized");

	err = bt_le_adv_start(BT_LE_ADV_NCONN, ad, ARRAY_SIZE(ad), NULL, 0);
	if (err) {
		LOG_ERR("Advertising failed: %d", err);
		return;
	}
	LOG_INF("Advertising as \"Clip\" started");
}

int main(void)
{
	if (!device_is_ready(gpio0) || !device_is_ready(gpio1)) {
		LOG_ERR("gpio not ready");
		return -1;
	}

	int ret = gpio_pin_configure(SUSPEND_INDICATE_PORT, SUSPEND_INDICATE_PIN, GPIO_OUTPUT_INACTIVE);

	if (ret != 0) {
		LOG_ERR("gpio_pin_configure failed: %d", ret);
		return -1;
	}

	shutdown_peripheral_rails();

	pm_notifier_register(&notifier);

	bt_enable(bt_ready);

	LOG_INF("=== suspend_to_ram ready (30s SD cycle) ===");
	LOG_INF("Probe GPIO1.%d: HIGH = in suspend-to-RAM.",
		SUSPEND_INDICATE_PIN);

	while (1) {
		LOG_INF("--- SD cycle start ---");
		test_sd_card();
		LOG_INF("--- SD cycle end, sleeping 30s ---");
		k_sleep(K_SECONDS(30));
	}

	return 0;
}
