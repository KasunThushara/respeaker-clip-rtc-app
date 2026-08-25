/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Shared 1200-baud -> mcuboot DFU trigger. When the host sets the CDC ACM
 * line coding to 1200 baud, set the mcuboot boot-mode retention register
 * (gpregret1) and reboot into serial recovery. mcuboot's
 * io_detect_boot_mode() (CONFIG_BOOT_SERIAL_BOOT_MODE) picks up the retained
 * boot mode on the next boot and enters serial recovery; the retention path
 * is not VBUS-gated (unlike the button path), but VBUS is present anyway
 * because the trigger arrives over USB.
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/usb/usbd.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/retention/bootmode.h>

#include "clip_usb_dfu.h"

LOG_MODULE_REGISTER(clip_usb_dfu, LOG_LEVEL_INF);

/* Host opens the CDC port at this baud to request DFU (Arduino convention). */
#define CLIP_USB_DFU_TRIGGER_BAUD	1200
/* Let the USB stack / logs settle before the cold reset. */
#define CLIP_USB_DFU_REBOOT_DELAY_MS	500

static void dfu_reboot_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);
	sys_reboot(SYS_REBOOT_COLD);
}

static struct k_work_delayable dfu_reboot_work;

static int clip_usb_dfu_init(void)
{
	k_work_init_delayable(&dfu_reboot_work, dfu_reboot_work_handler);
	return 0;
}
SYS_INIT(clip_usb_dfu_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);

void clip_usb_dfu_check(const struct usbd_msg *msg)
{
	if (msg == NULL || msg->type != USBD_MSG_CDC_ACM_LINE_CODING) {
		return;
	}

	uint32_t baud = 0U;

	if (uart_line_ctrl_get(msg->dev, UART_LINE_CTRL_BAUD_RATE, &baud)) {
		return;
	}

	if (baud != CLIP_USB_DFU_TRIGGER_BAUD) {
		return;
	}

	LOG_INF("USB CDC: %u baud -> DFU recovery", baud);
	(void)bootmode_set(BOOT_MODE_TYPE_BOOTLOADER);
	(void)k_work_schedule(&dfu_reboot_work, K_MSEC(CLIP_USB_DFU_REBOOT_DELAY_MS));
}
