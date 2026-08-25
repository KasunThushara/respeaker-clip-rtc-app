/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * Battery discharge/charge cycle test state machine. Polls the NPM1300
 * charger every few seconds, drives the charger enable to alternate between
 * discharging (WiFi TX load drains the cell) and charging, and keeps the
 * OLED updated with % / state / voltage. The displayed % comes from the nRF
 * Fuel Gauge (stable under the pulsed WiFi TX load); the charge/discharge
 * *switching* is deliberately voltage-based for clean hysteresis around the
 * cell's knee voltages.
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <stdio.h>
#include "discharge.h"
#include "pmic.h"
#include "oled.h"
#include "wifi.h"
#include "sdcard.h"

LOG_MODULE_REGISTER(discharge, LOG_LEVEL_INF);

/* Voltage-hysteresis thresholds (cell voltage, not fuel-gauge SoC):
 *  - DISCHARGE -> CHARGE when the cell sinks to 3.5 V,
 *  - CHARGE    -> DISCHARGE when the cell rises to 4.12 V.
 * The 3.5 V floor stays above the ~3.3 V point where BUCK2 can no longer hold
 * the 3.3 V rail (buck dropout) and WiFi brownouts, with headroom for the
 * transient voltage sag under the WiFi TX load. The 0.62 V gap prevents
 * oscillation around the switching point. */
#define DISCHARGE_VOLTAGE_MV		3500U	/* start charging at/below */
#define CHARGE_VOLTAGE_MV		4120U	/* start discharging at/above */
/* Control-loop poll interval. The cycle is voltage-driven, so this sets how
 * often the state machine re-reads the cell voltage and re-evaluates the
 * charge/discharge switch + refreshes the OLED. 1 s makes the display and
 * threshold-crossing response feel live (was 5 s). The cell voltage moves
 * slowly, so going below ~500 ms just adds I2C/OLED traffic for no benefit. */
#define POLL_INTERVAL_MS		1000U

/* High-temperature charge cutoff (software hysteresis). The NPM1300 HW hot
 * threshold (thermistor-hot-millidegrees=45C in the board DTS) inhibits
 * charging autonomously, but the NTC path has no register hysteresis, so a
 * cell resting at ~45C would oscillate charge on/off. Software latches OFF
 * at STOP and re-enables at RESUME (5C gap). Matches the clip app. Active
 * only during CHARGE (during DISCHARGE the charger is already off). */
#define CHARGE_STOP_TEMP_C		45	/* stop charging at/above */
#define CHARGE_RESUME_TEMP_C		40	/* resume charging below */

enum cycle_state {
	STATE_DISCHARGE,
	STATE_CHARGE,
};

void discharge_run(void)
{
	enum cycle_state state = STATE_DISCHARGE;
	uint32_t cycles = 0U;
	uint8_t pct = 0U;
	uint32_t mv = 0U;
	int32_t temp = 0;
	bool charging = false;
	bool thermal_charge_disabled = false;  /* sticky: latched hot, held off until resume */

	printk("\n=== Battery discharge/charge cycle test ===\n");
	printk("Discharging to %u mV, then charging to %u mV, repeat.\n\n",
	       DISCHARGE_VOLTAGE_MV, CHARGE_VOLTAGE_MV);

	/* Start in DISCHARGE: charger off, WiFi TX + SD read loads on. */
	pmic_charger_set(false);
	wifi_discharge_load_enable(true);
	sdcard_discharge_load_enable(true);

	for (;;) {
		int ret = pmic_get_battery_status(&mv, &pct, &charging, &temp);
		const char *label = (state == STATE_DISCHARGE) ?
				    "DISCHARGE" : "CHARGE";

		if (ret == 0) {
			oled_show_battery(pct, charging, mv, temp, label, cycles);

			if (state == STATE_DISCHARGE) {
				if (mv <= DISCHARGE_VOLTAGE_MV) {
					LOG_INF("cycle %u: %u mV reached -> CHARGE",
						cycles, mv);
					state = STATE_CHARGE;
					/* Charge with minimal load: WiFi off
					 * (AP down + TX idle) + SD read off. */
					wifi_discharge_load_enable(false);
					sdcard_discharge_load_enable(false);
					pmic_charger_set(true);
				}
			} else { /* STATE_CHARGE */
				if (mv >= CHARGE_VOLTAGE_MV) {
					cycles++;
					LOG_INF("cycle %u: %u mV reached -> DISCHARGE",
						cycles, mv);
					state = STATE_DISCHARGE;
					pmic_charger_set(false);
					wifi_discharge_load_enable(true);
					sdcard_discharge_load_enable(true);
				}
			}

			/* Thermal charge gating (software hysteresis). The HW
			 * NPM1300 hot threshold (45C, board DTS) is the
			 * autonomous safety net; this adds the 5C resume gap the
			 * NTC path lacks so a cell at ~45C doesn't oscillate.
			 * Active only during CHARGE. */
			if (state == STATE_CHARGE) {
				if (temp >= CHARGE_STOP_TEMP_C && !thermal_charge_disabled) {
					pmic_charger_set(false);
					thermal_charge_disabled = true;
					LOG_WRN("Thermal: charge off (temp %dC >= %dC)",
						(int)temp, CHARGE_STOP_TEMP_C);
				} else if (thermal_charge_disabled &&
					   temp <= CHARGE_RESUME_TEMP_C) {
					pmic_charger_set(true);
					thermal_charge_disabled = false;
					LOG_INF("Thermal: charge resume (temp %dC <= %dC)",
						(int)temp, CHARGE_RESUME_TEMP_C);
				}
			}
		} else {
			LOG_WRN("battery read failed: %d", ret);
		}

		k_sleep(K_MSEC(POLL_INTERVAL_MS));
	}
}
