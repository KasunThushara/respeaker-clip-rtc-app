/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Default USB CDC ACM for the 1200-baud DFU trigger (CLIP_USB_DFU_DEFAULT_CDC).
 * A minimal single-CDC-interface USB device, auto-initialized and enabled via
 * SYS_INIT (Arduino-style) so apps without their own USB stack (e.g. samples)
 * get the DFU trigger with zero code. Apps that bring their own CDC (the clip
 * app, BLE-gated) set CLIP_USB_DFU_DEFAULT_CDC=n and call clip_usb_dfu_check()
 * from their own USB message callback instead.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/logging/log.h>
#include <zephyr/usb/usbd.h>

#include "clip_usb_dfu.h"

LOG_MODULE_REGISTER(clip_usb_cdc_default, LOG_LEVEL_INF);

/* Minimal USB device: Seeed VID 0x2886, PID 0x0069 (mcuboot recovery uses
 * 0x8069 — the 0x8000 bit distinguishes bootloader from app). */
USBD_DEVICE_DEFINE(clip_dfu_usbd,
		   DEVICE_DT_GET(DT_NODELABEL(usbd)),
		   0x2886, 0x0069);

USBD_DESC_LANG_DEFINE(clip_dfu_lang);
USBD_DESC_MANUFACTURER_DEFINE(clip_dfu_mfr, "Seeed Studio");
USBD_DESC_PRODUCT_DEFINE(clip_dfu_product, "reSpeaker Clip");
USBD_DESC_CONFIG_DEFINE(clip_dfu_cfg, "Default");
USBD_CONFIGURATION_DEFINE(clip_dfu_config, 0, 100, &clip_dfu_cfg);

static void clip_dfu_msg_cb(struct usbd_context *const ctx,
			    const struct usbd_msg *msg)
{
	ARG_UNUSED(ctx);
	clip_usb_dfu_check(msg);
}

static int clip_usb_cdc_default_init(void)
{
	int err;

	usbd_add_descriptor(&clip_dfu_usbd, &clip_dfu_lang);
	usbd_add_descriptor(&clip_dfu_usbd, &clip_dfu_mfr);
	usbd_add_descriptor(&clip_dfu_usbd, &clip_dfu_product);

	err = usbd_add_configuration(&clip_dfu_usbd, USBD_SPEED_FS,
				     &clip_dfu_config);
	if (err) {
		LOG_ERR("DFU CDC: add config: %d", err);
		return err;
	}

	err = usbd_register_class(&clip_dfu_usbd, "cdc_acm_0", USBD_SPEED_FS, 1);
	if (err) {
		LOG_ERR("DFU CDC: register class: %d", err);
		return err;
	}

	err = usbd_init(&clip_dfu_usbd);
	if (err) {
		LOG_ERR("DFU CDC: usbd init: %d", err);
		return err;
	}

	usbd_msg_register_cb(&clip_dfu_usbd, clip_dfu_msg_cb);

	/* Arduino-style: auto-enable so the host sees the CDC port and can
	 * touch 1200 baud to enter DFU. */
	err = usbd_enable(&clip_dfu_usbd);
	if (err) {
		LOG_ERR("DFU CDC: usbd enable: %d", err);
		return err;
	}

	LOG_INF("DFU CDC ACM auto-enabled (1200 baud -> recovery)");
	return 0;
}
SYS_INIT(clip_usb_cdc_default_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
