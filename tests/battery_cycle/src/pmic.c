/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <stdio.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/sensor/npm13xx_charger.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/shell/shell.h>
#include <zephyr/logging/log.h>
#include <nrf_fuel_gauge.h>
#include "pmic.h"

LOG_MODULE_REGISTER(pmic, LOG_LEVEL_INF);

/* PMIC devices */
static const struct device *charger_dev = DEVICE_DT_GET(DT_NODELABEL(npm1300_charger));
static const struct device *pmic_gpio_dev = DEVICE_DT_GET(DT_NODELABEL(npm1300_gpio));
static const struct device *pmic_regulators = DEVICE_DT_GET(DT_NODELABEL(npm1300_regulators));

/* Charger status bitmasks (BCHGCHARGESTATUS register) */
#define CHG_STATUS_COMPLETE_MASK BIT(1)
#define CHG_STATUS_TRICKLE_MASK  BIT(2)
#define CHG_STATUS_CC_MASK       BIT(3)
#define CHG_STATUS_CV_MASK       BIT(4)

/* Voltage → SoC lookup table (same as main application) */
struct volt_soc_entry {
	uint32_t mv;
	uint8_t  soc;
};

static const struct volt_soc_entry volt_soc_table[] = {
	{ 4150, 100 },
	{ 4060,  90 },
	{ 3980,  80 },
	{ 3900,  70 },
	{ 3820,  60 },
	{ 3740,  50 },
	{ 3660,  40 },
	{ 3570,  30 },
	{ 3480,  20 },
	{ 3390,  10 },
	{ 3300,   0 },
};

static uint8_t voltage_to_soc(uint32_t mv)
{
	const int n = 10;

	if (mv >= volt_soc_table[0].mv) {
		return 100;
	}
	if (mv <= volt_soc_table[n - 1].mv) {
		return 0;
	}

	for (int i = 0; i < n - 1; i++) {
		const struct volt_soc_entry *hi = &volt_soc_table[i];
		const struct volt_soc_entry *lo = &volt_soc_table[i + 1];

		if (mv <= hi->mv && mv > lo->mv) {
			uint32_t range_mv  = hi->mv - lo->mv;
			uint32_t offset_mv = mv - lo->mv;
			uint8_t  range_soc = hi->soc - lo->soc;

			return lo->soc + (uint8_t)(offset_mv * range_soc / range_mv);
		}
	}

	return 0;
}

/* ----------------------------------------------------------------------------
 * SoC source: the nRF Fuel Gauge (Coulomb counting + the 240-cell HSZ
 * 362123 model in battery_model.inc) is the primary state-of-charge. It is
 * stable under the pulsed WiFi TX discharge load, where the old
 * voltage_to_soc() table jumped on transient cell-voltage sag and made the
 * OLED % flicker.
 *
 * The earlier removal note ("its SoC was unreliable") was wrong: the real
 * cause was a current-sign bug. The Zephyr NPM1300 sensor API returns
 * GAUGE_AVG_CURRENT with NEGATIVE = discharging, but the nrf_fuel_gauge
 * library expects NEGATIVE = charging. The current is therefore negated
 * before being fed to the library, in BOTH nrf_fuel_gauge_init (i0) and
 * nrf_fuel_gauge_process (current) — matching Nordic's npm13xx_fuel_gauge
 * sample and the clip application. voltage_to_soc() is retained as the
 * fallback when the fuel gauge fails to initialize.
 * ------------------------------------------------------------------------- */

/* Battery model — the project's 240-cell (HSZ 362123, 170 mAh) parameters. */
static const struct battery_model battery_model = {
#include "battery_model.inc"
};

/* Fuel gauge state. fg_ref_time backs the per-poll time delta;
 * chg_status_prev detects charger-state transitions to inform the gauge. */
static bool fg_initialized;
static int64_t fg_ref_time;
static int32_t chg_status_prev;

/* Inform the fuel gauge of charger state changes (improves TTF prediction). */
static int charge_status_inform(int32_t chg_status)
{
	union nrf_fuel_gauge_ext_state_info_data state_info;

	if (chg_status & CHG_STATUS_COMPLETE_MASK) {
		state_info.charge_state = NRF_FUEL_GAUGE_CHARGE_STATE_COMPLETE;
	} else if (chg_status & CHG_STATUS_TRICKLE_MASK) {
		state_info.charge_state = NRF_FUEL_GAUGE_CHARGE_STATE_TRICKLE;
	} else if (chg_status & CHG_STATUS_CC_MASK) {
		state_info.charge_state = NRF_FUEL_GAUGE_CHARGE_STATE_CC;
	} else if (chg_status & CHG_STATUS_CV_MASK) {
		state_info.charge_state = NRF_FUEL_GAUGE_CHARGE_STATE_CV;
	} else {
		state_info.charge_state = NRF_FUEL_GAUGE_CHARGE_STATE_IDLE;
	}

	return nrf_fuel_gauge_ext_state_update(NRF_FUEL_GAUGE_EXT_STATE_INFO_CHARGE_STATE_CHANGE,
					       &state_info);
}

/* Initialize PMIC */
int pmic_init(void)
{
	int ret = 0;

	LOG_INF("Initializing PMIC (NPM1300)...");

	/* Check charger device */
	if (!device_is_ready(charger_dev)) {
		LOG_WRN("npm1300 charger not ready");
		ret = -ENODEV;
	} else {
		LOG_INF("  npm1300_charger: ready");
	}

	/* Check PMIC GPIO device */
	if (!device_is_ready(pmic_gpio_dev)) {
		LOG_WRN("npm1300_gpio not ready");
		ret = -ENODEV;
	} else {
		LOG_INF("  npm1300_gpio: ready (5 GPIOs available)");
	}

	/* Check regulators device */
	if (!device_is_ready(pmic_regulators)) {
		LOG_WRN("npm1300_regulators not ready");
		ret = -ENODEV;
	} else {
		LOG_INF("  npm1300_regulators: ready");
	}

	if (ret == 0) {
		LOG_INF("PMIC initialized successfully");
	}

	/* Initialize the nRF Fuel Gauge before the first battery reading so
	 * that reading (and every pmic_get_battery_status() call thereafter)
	 * uses Coulomb-counting SoC instead of the voltage lookup. On any
	 * failure, fg_initialized stays false and voltage_to_soc() is used. */
	if (device_is_ready(charger_dev)) {
		struct nrf_fuel_gauge_init_parameters init_params = {
			.model = &battery_model,
			.opt_params = NULL,
			.state = NULL,
		};
		struct sensor_value value;
		int32_t chg_status = 0;
		int rc;

		rc = sensor_sample_fetch(charger_dev);
		if (rc < 0) {
			LOG_WRN("Fuel gauge init: sample fetch failed: %d", rc);
		} else {
			sensor_channel_get(charger_dev, SENSOR_CHAN_GAUGE_VOLTAGE, &value);
			init_params.v0 = (float)value.val1 + ((float)value.val2 / 1000000.0f);

			sensor_channel_get(charger_dev, SENSOR_CHAN_GAUGE_AVG_CURRENT, &value);
			init_params.i0 = (float)value.val1 + ((float)value.val2 / 1000000.0f);

			sensor_channel_get(charger_dev, SENSOR_CHAN_GAUGE_TEMP, &value);
			init_params.t0 = (float)value.val1 + ((float)value.val2 / 1000000.0f);

			sensor_channel_get(charger_dev, SENSOR_CHAN_NPM13XX_CHARGER_STATUS, &value);
			chg_status = value.val1;

			/* Zephyr sensor API: negative = discharging; nrf_fuel_gauge
			 * expects negative = charging -- negate i0. */
			init_params.i0 = -init_params.i0;

			LOG_INF("Fuel gauge init: V=%.3f I=%.3f T=%.1f chg=0x%02x",
				(double)init_params.v0, (double)init_params.i0,
				(double)init_params.t0, (unsigned int)chg_status);

			rc = nrf_fuel_gauge_init(&init_params, NULL);
			if (rc < 0) {
				LOG_WRN("Fuel gauge init failed: %d, using voltage-based SoC", rc);
			} else {
				/* Charge current limits (used for TTF). */
				sensor_channel_get(charger_dev,
						   SENSOR_CHAN_GAUGE_DESIRED_CHARGING_CURRENT,
						   &value);
				float max_charge_current =
					(float)value.val1 + ((float)value.val2 / 1000000.0f);
				float term_charge_current = max_charge_current / 10.0f;

				nrf_fuel_gauge_ext_state_update(
					NRF_FUEL_GAUGE_EXT_STATE_INFO_CHARGE_CURRENT_LIMIT,
					&(union nrf_fuel_gauge_ext_state_info_data){
						.charge_current_limit = max_charge_current});
				nrf_fuel_gauge_ext_state_update(
					NRF_FUEL_GAUGE_EXT_STATE_INFO_TERM_CURRENT,
					&(union nrf_fuel_gauge_ext_state_info_data){
						.charge_term_current = term_charge_current});

				charge_status_inform(chg_status);
				chg_status_prev = chg_status;

				fg_ref_time = k_uptime_get();
				fg_initialized = true;
				LOG_INF("Fuel gauge enabled (model %c%c%c, %s)",
					battery_model.name[0], battery_model.name[1],
					battery_model.name[2], nrf_fuel_gauge_version);
			}
		}
	}

	/* Initial battery reading (fuel-gauge SoC if initialized, else voltage). */
	if (device_is_ready(charger_dev)) {
		uint32_t mv = 0;
		uint8_t pct = 0;
		bool charging = false;
		int32_t temp = 0;

		if (pmic_get_battery_status(&mv, &pct, &charging, &temp) == 0) {
			LOG_INF("Battery: %u mV, %u%%, %s, %dC", mv, pct,
				charging ? "charging" : "discharging", temp);
		}
	}

	return ret;
}

/* Get battery status */
int pmic_get_battery_status(uint32_t *voltage_mv, uint8_t *percent, bool *charging,
			    int32_t *temp_c)
{
	struct sensor_value val;
	int32_t chg_status = 0;
	int ret;

	if (!device_is_ready(charger_dev)) {
		return -ENODEV;
	}

	ret = sensor_sample_fetch(charger_dev);
	if (ret < 0) {
		LOG_ERR("sensor_sample_fetch failed: %d", ret);
		return ret;
	}

	/* Read voltage (mV for the API output, volts for the fuel gauge). */
	ret = sensor_channel_get(charger_dev, SENSOR_CHAN_GAUGE_VOLTAGE, &val);
	if (ret != 0) {
		LOG_WRN("GAUGE_VOLTAGE read failed: %d", ret);
		return ret;
	}
	*voltage_mv = (uint32_t)(val.val1 * 1000 + val.val2 / 1000);
	float voltage_volts = (float)val.val1 + ((float)val.val2 / 1000000.0f);

	/* Read charging status */
	ret = sensor_channel_get(charger_dev, SENSOR_CHAN_NPM13XX_CHARGER_STATUS, &val);
	if (ret == 0) {
		chg_status = val.val1;
		*charging = (chg_status & (CHG_STATUS_TRICKLE_MASK |
					   CHG_STATUS_CC_MASK |
					   CHG_STATUS_CV_MASK)) != 0;
	} else {
		LOG_WRN("CHARGER_STATUS read failed: %d", ret);
	}

	/* Read battery temperature (NTC, degrees Celsius). */
	float temp_c_float = 0.0f;
	ret = sensor_channel_get(charger_dev, SENSOR_CHAN_GAUGE_TEMP, &val);
	if (ret == 0) {
		*temp_c = val.val1;  /* integer degrees C (sensor_value val1) */
		temp_c_float = (float)val.val1 + ((float)val.val2 / 1000000.0f);
	} else {
		LOG_WRN("GAUGE_TEMP read failed: %d", ret);
		*temp_c = 0;
	}

	/* Read average current (amps). */
	float current = 0.0f;
	ret = sensor_channel_get(charger_dev, SENSOR_CHAN_GAUGE_AVG_CURRENT, &val);
	if (ret == 0) {
		current = (float)val.val1 + ((float)val.val2 / 1000000.0f);
	} else {
		LOG_WRN("GAUGE_AVG_CURRENT read failed: %d", ret);
	}

	/* SoC: nRF Fuel Gauge (primary) or voltage lookup (fallback).
	 * Zephyr sensor API: GAUGE_AVG_CURRENT negative = discharging;
	 * nrf_fuel_gauge expects negative = charging, so the current is
	 * negated before being fed to the library (both init and process). */
	if (fg_initialized) {
		/* Inform the fuel gauge of the VBUS state on every update
		 * (matches Nordic's npm13xx_fuel_gauge sample + the clip app)
		 * — the gauge needs it for accurate TTF and its charge-state
		 * machine. */
		struct sensor_value vbus_val = {0};
		bool vbus_connected = false;
		if (sensor_channel_get(charger_dev,
				       SENSOR_CHAN_NPM13XX_CHARGER_VBUS_STATUS,
				       &vbus_val) == 0) {
			vbus_connected = (vbus_val.val1 != 0);
		}
		(void)nrf_fuel_gauge_ext_state_update(
			vbus_connected ? NRF_FUEL_GAUGE_EXT_STATE_INFO_VBUS_CONNECTED
				       : NRF_FUEL_GAUGE_EXT_STATE_INFO_VBUS_DISCONNECTED,
			NULL);

		if (chg_status != chg_status_prev) {
			chg_status_prev = chg_status;
			charge_status_inform(chg_status);
		}

		float delta = (float)k_uptime_delta(&fg_ref_time) / 1000.0f;
		float soc = nrf_fuel_gauge_process(voltage_volts, -current,
						   temp_c_float, delta, NULL);
		*percent = (uint8_t)soc;
	} else {
		*percent = voltage_to_soc(*voltage_mv);
	}

	return 0;
}

/* Enable/disable charging at runtime.
 * Uses the desired-charging-current channel: 0 clears the charger enable bit
 * (CHGR_EN_CLR), non-zero sets it (CHGR_EN_SET) — see npm13xx_charger.c. */
#define CHARGE_CURRENT_MA	220	/* matches DTS current-microamp 220000 */

int pmic_charger_set(bool enable)
{
	if (!device_is_ready(charger_dev)) {
		return -ENODEV;
	}

	struct sensor_value val = {
		.val1 = enable ? CHARGE_CURRENT_MA : 0,
		.val2 = 0,
	};

	int ret = sensor_attr_set(charger_dev,
				  SENSOR_CHAN_GAUGE_DESIRED_CHARGING_CURRENT,
				  SENSOR_ATTR_CONFIGURATION, &val);
	if (ret) {
		LOG_ERR("pmic_charger_set(%d) failed: %d", enable, ret);
	}
	return ret;
}

bool pmic_is_charge_complete(void)
{
	if (!device_is_ready(charger_dev)) {
		return false;
	}

	struct sensor_value val;
	int ret = sensor_sample_fetch(charger_dev);
	if (ret < 0) {
		return false;
	}

	ret = sensor_channel_get(charger_dev, SENSOR_CHAN_NPM13XX_CHARGER_STATUS, &val);
	if (ret < 0) {
		return false;
	}

	return (val.val1 & CHG_STATUS_COMPLETE_MASK) != 0;
}

/* Get detailed charger status */
static int pmic_get_charger_status_string(char *buf, size_t len)
{
	struct sensor_value val;
	int ret;

	if (!device_is_ready(charger_dev)) {
		snprintf(buf, len, "Device not ready");
		return -ENODEV;
	}

	ret = sensor_sample_fetch(charger_dev);
	if (ret < 0) {
		snprintf(buf, len, "Sample fetch failed: %d", ret);
		return ret;
	}

	ret = sensor_channel_get(charger_dev, SENSOR_CHAN_NPM13XX_CHARGER_STATUS, &val);
	if (ret == 0) {
		int32_t status = val.val1;
		const char *state = "Unknown";

		if (status & CHG_STATUS_COMPLETE_MASK) {
			state = "Complete";
		} else if (status & CHG_STATUS_CV_MASK) {
			state = "CV (Constant Voltage)";
		} else if (status & CHG_STATUS_CC_MASK) {
			state = "CC (Constant Current)";
		} else if (status & CHG_STATUS_TRICKLE_MASK) {
			state = "Trickle";
		} else {
			state = "Not Charging";
		}

		snprintf(buf, len, "%s (0x%02x)", state, (unsigned int)status);
	} else {
		snprintf(buf, len, "Read failed: %d", ret);
	}

	return ret;
}

/* Enter ship mode (power off) */
int pmic_enter_ship_mode(void)
{
	if (!device_is_ready(pmic_regulators)) {
		LOG_ERR("npm1300 regulators not ready");
		return -ENODEV;
	}

	LOG_INF("Entering ship mode (power off)...");
	LOG_INF("  Wake up: hold button for ~3 seconds");

	/* Flush logs before ship mode */
	k_sleep(K_MSEC(100));

	return regulator_parent_ship_mode(pmic_regulators);
}

/* ============================================================================
 * Shell Commands
 * ============================================================================ */

/* Shell command: pmic status */
static int cmd_pmic_status(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	uint32_t voltage_mv;
	uint8_t percent;
	bool charging;
	int32_t temp;
	char status_str[64];
	int ret;

	ret = pmic_get_battery_status(&voltage_mv, &percent, &charging, &temp);
	if (ret == 0) {
		shell_print(sh, "Battery Status:");
		shell_print(sh, "  Voltage: %u mV", voltage_mv);
		shell_print(sh, "  Level:   %u%%", percent);
		shell_print(sh, "  Temp:    %dC", temp);
		shell_print(sh, "  Charging: %s", charging ? "Yes" : "No");

		/* Get detailed charger status */
		pmic_get_charger_status_string(status_str, sizeof(status_str));
		shell_print(sh, "  Charger: %s", status_str);
	} else {
		shell_print(sh, "Error: Failed to read battery status (%d)", ret);
	}

	return ret;
}

/* Shell command: pmic monitor (continuous monitoring) */
static int cmd_pmic_monitor(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t voltage_mv;
	uint8_t percent;
	bool charging;
	int32_t temp;
	int iterations = 0;
	int max_iter = 10;  /* Default: 10 iterations */

	if (argc >= 2) {
		max_iter = strtol(argv[1], NULL, 10);
		if (max_iter <= 0) {
			shell_print(sh, "Usage: pmic monitor [iterations]");
			return -EINVAL;
		}
	}

	shell_print(sh, "Monitoring battery status (Ctrl+C to stop)...");

	while (iterations < max_iter) {
		if (pmic_get_battery_status(&voltage_mv, &percent, &charging, &temp) == 0) {
			shell_print(sh, "[%2d] %4u mV | %3u%% | %dC | %s",
				   iterations + 1, voltage_mv, percent, temp,
				   charging ? "Charging" : "Discharging");
		}

		iterations++;
		k_sleep(K_SECONDS(1));
	}

	shell_print(sh, "Monitoring stopped (%d iterations)", iterations);
	return 0;
}

/* Shell command: pmic ship (enter ship mode / power off) */
static int cmd_pmic_ship(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	shell_print(sh, "Entering ship mode (power off)...");
	shell_print(sh, "Wake up: hold button for ~3 seconds");

	/* Give user time to read the message */
	k_sleep(K_SECONDS(1));

	/* Enter ship mode - this will power off the system immediately */
	pmic_enter_ship_mode();

	/* Should not reach here */
	return 0;
}

/* Shell command table */
SHELL_STATIC_SUBCMD_SET_CREATE(sub_pmic,
	SHELL_CMD(status, NULL, "Show battery and charger status", cmd_pmic_status),
	SHELL_CMD_ARG(monitor, NULL, "Monitor battery status [iterations]", cmd_pmic_monitor, 0, 1),
	SHELL_CMD(ship, NULL, "Enter ship mode (power off)", cmd_pmic_ship),
	SHELL_SUBCMD_SET_END
);

/* Root command: pmic */
SHELL_CMD_REGISTER(pmic, &sub_pmic, "PMIC (NPM1300) commands", NULL);
