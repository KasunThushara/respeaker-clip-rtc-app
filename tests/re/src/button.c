/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/input/button.h>
#include <zephyr/logging/log.h>
#include "button.h"
#include "pmic.h"

LOG_MODULE_REGISTER(button, LOG_LEVEL_INF);

static void button_event_cb(const struct device *dev, enum button_action action)
{
	switch (action) {
	case BUTTON_DOUBLE_CLICK:
		LOG_INF("Double click — entering ship mode");
		pmic_enter_ship_mode();
		LOG_ERR("Ship mode failed");
		break;
	case BUTTON_SINGLE_CLICK:
		LOG_INF("Button click");
		break;
	default:
		break;
	}
}

int button_init(void)
{
	const struct device *btn = DEVICE_DT_GET(DT_ALIAS(sw0));
	int ret;

	if (!device_is_ready(btn)) {
		LOG_ERR("Button device not ready");
		return -ENODEV;
	}

	ret = button_callback_register(btn, button_event_cb);
	if (ret < 0) {
		LOG_ERR("Button callback register failed: %d", ret);
		return ret;
	}

	LOG_INF("Button ready (double click = ship mode)");

	return 0;
}
