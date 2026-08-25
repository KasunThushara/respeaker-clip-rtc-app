/*
 * Copyright (c) 2025 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef CLIP_ICONS_H
#define CLIP_ICONS_H

#include <stdint.h>

/**
 * @file icons.h
 * @brief Icon library for CLIP display
 *
 * Icons are stored as const bitmap data in Flash (ROM), not RAM.
 * Format: 16x16 pixels, row-major order, 1 bit per pixel
 * Each row uses 2 bytes (16 bits = 16 pixels)
 */

#define ICON_WIDTH  24
#define ICON_HEIGHT 24
#define ICON_SIZE_BYTES 72  /* 24 rows * 3 bytes per row */

/**
 * @brief Icon identifiers
 */
typedef enum {
	ICON_NONE = 0,
	ICON_WIFI_CONNECTED,     /**< WiFi connected icon */
	ICON_WIFI_TRANSFER,      /**< WiFi transfer icon */
	ICON_BLE_CONNECTED,      /**< BLE connected icon */
	ICON_BLE_TRANSFER,       /**< BLE transfer icon */
	ICON_BATTERY_FULL,       /**< Battery full icon */
	ICON_BATTERY_CHARGING,   /**< Battery charging icon */
	ICON_BATTERY_LOW,        /**< Battery low icon */
	ICON_USB_CONNECTED,      /**< USB connected icon */
	ICON_MIC_NORMAL,         /**< Normal microphone icon */
	ICON_MIC_ENHANCED,       /**< Enhanced microphone icon */
	ICON_MIC_MUTED,          /**< Muted microphone icon */
	ICON_CONNECTED,          /**< Generic connected icon */
	ICON_DISCONNECTED,       /**< Generic disconnected icon */
	ICON_PHONE,              /**< Phone icon */
	ICON_WIRED_CHARGING,     /**< Wired charging icon (power plug) */
	ICON_ARROW,              /**< Arrow icon */
	ICON_WIFI_CLIENT,        /**< WiFi client connected icon */
	ICON_WIFI_UDP,           /**< WiFi UDP transfer icon */
	ICON_WIRED_TRANSFER,     /**< Wired transfer icon */
	ICON_LOW_BATTERY_DISPLAY, /**< Low battery display icon */
	ICON_DISCONNECT_NOT_TRANSFORM, /**< Disconnect not transfer icon */
	ICON_OTA,                 /**< OTA upgrade icon */
	ICON_POWER,               /**< Power button icon */
} icon_id_t;

/**
 * @brief Get icon bitmap data by ID
 *
 * @param id Icon identifier
 * @param width Output: icon width in pixels (always 16)
 * @param height Output: icon height in pixels (always 16)
 * @return Pointer to icon bitmap data, or NULL if not found
 */
const uint8_t* icon_get_bitmap(icon_id_t id, uint8_t *width, uint8_t *height);

/**
 * @brief Draw 16x16 bitmap icon to buffer
 *
 * @param buf Frame buffer
 * @param x X position
 * @param y Y position
 * @param bitmap Icon bitmap data (32 bytes for 16x16)
 * @param width Icon width in pixels
 * @param height Icon height in pixels
 */
void icon_draw_bitmap(uint8_t *buf, int x, int y,
                      const uint8_t *bitmap, uint8_t width, uint8_t height);

#endif /* CLIP_ICONS_H */
