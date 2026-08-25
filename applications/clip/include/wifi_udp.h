/*
 * Copyright (c) 2025 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef CLIP_WIFI_UDP_H
#define CLIP_WIFI_UDP_H

#include <stdbool.h>

/**
 * @brief Initialize UDP server (called once at startup)
 *
 * @return 0 on success, negative error code on failure
 */
int wifi_udp_init(void);

/**
 * @brief Start UDP server on WIFI_AP_UDP_PORT
 *
 * Call after wifi_on() succeeds.
 * AT commands and file data are received over UDP.
 *
 * @return 0 on success, negative error code on failure
 */
int wifi_udp_start(void);

/**
 * @brief Stop the UDP server
 *
 * Call before wifi_off().
 */
void wifi_udp_stop(void);

/**
 * @brief Check if the UDP server is currently running
 *
 * @return true if server thread is running, false otherwise
 */
bool wifi_udp_is_running(void);

/**
 * @brief Check if a UDP client has sent data
 *
 * @return true if client active, false otherwise
 */
bool wifi_udp_is_active(void);

#endif /* CLIP_WIFI_UDP_H */