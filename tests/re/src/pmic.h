/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef PMIC_H
#define PMIC_H

#include <zephyr/kernel.h>

/**
 * @brief Initialize PMIC (NPM1300)
 * @return 0 on success, negative errno on failure
 */
int pmic_init(void);

/**
 * @brief Get battery status
 * @param voltage_mv Pointer to store voltage in mV
 * @param percent Pointer to store battery percentage
 * @param charging Pointer to store charging state
 * @return 0 on success, negative errno on failure
 */
int pmic_get_battery_status(uint32_t *voltage_mv, uint8_t *percent, bool *charging);

/**
 * @brief Enter ship mode (power off)
 * @return 0 on success, negative errno on failure
 */
int pmic_enter_ship_mode(void);

#endif /* PMIC_H */
