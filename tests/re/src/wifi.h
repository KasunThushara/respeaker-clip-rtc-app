/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef WIFI_H__
#define WIFI_H__

#include <zephyr/kernel.h>

/**
 * @brief Initialize WiFi AP mode
 *
 * Generates SSID from chip ID and registers event callbacks.
 * Use 'wifi on' shell command to actually start the AP.
 *
 * @return 0 on success, negative errno on failure
 */
int wifi_init_and_connect(void);

/**
 * @brief Start WiFi throughput test
 *
 * @return 0 on success, negative errno on failure
 */
int wifi_start_throughput_test(void);

/**
 * @brief Run WiFi initialization
 * This function initializes WiFi AP mode.
 *
 * @return 0 on success, negative errno on failure
 */
int wifi_run_test(void);

bool wifi_ap_is_running(void);

#endif /* WIFI_H__ */
