/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef OLED_H
#define OLED_H

#include <zephyr/kernel.h>

/**
 * @brief Initialize OLED display
 * @return 0 on success, negative errno on failure
 */
int oled_init(void);

/**
 * @brief Render the persistent battery status screen
 *
 * The hardware test firmware refreshes this screen once per second after
 * PMIC initialization. It shows SoC, battery voltage, charge/discharge state,
 * and NTC temperature.
 */
void oled_show_battery(uint8_t percent, uint32_t voltage_mv, bool charging,
		       int32_t temp_c);

/**
 * @brief Render a battery-status placeholder when the PMIC is unavailable
 *
 * This keeps the test OLED visibly alive rather than leaving it blank while
 * the PMIC channel is being diagnosed.
 */
void oled_show_battery_unavailable(void);

/**
 * @brief Test 1: Clear display
 */
void oled_test_clear(void);

/**
 * @brief Test 2: Fill display
 */
void oled_test_fill(void);

/**
 * @brief Test 3: Display test pattern
 */
void oled_test_pattern(void);

/**
 * @brief Test 4: Circle animation (breathing effect)
 */
void oled_test_circle_anim(void);

/**
 * @brief Test 5: Pixel manipulation test (checkerboard)
 */
void oled_test_pixels(void);

/**
 * @brief Run all OLED tests sequentially
 */
void oled_run_all_tests(void);

#endif /* OLED_H */
