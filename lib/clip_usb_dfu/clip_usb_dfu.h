/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * 1200-baud USB CDC -> mcuboot serial recovery (DFU) trigger.
 * Board-level helper: any app on the clip board gets this via the
 * reSpeaker_Clip module (CONFIG_CLIP_USB_DFU, default y).
 */

#ifndef CLIP_USB_DFU_H_
#define CLIP_USB_DFU_H_

#include <zephyr/usb/usbd.h>

/**
 * @brief Check a USBD message for the 1200-baud DFU trigger.
 *
 * Call this from the app's USB message callback (usbd_msg_register_cb), or
 * rely on the module's default CDC (CLIP_USB_DFU_DEFAULT_CDC) which wires it
 * up automatically. Self-contained: when the host sets the CDC ACM line
 * coding to 1200 baud, it sets the mcuboot boot-mode retention register and
 * schedules a deferred reboot into mcuboot serial recovery. No-op for every
 * other message / baud rate.
 *
 * @param msg USBD message passed to the message callback (may be NULL).
 */
void clip_usb_dfu_check(const struct usbd_msg *msg);

#endif /* CLIP_USB_DFU_H_ */
