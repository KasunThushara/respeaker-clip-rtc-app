/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef RE_TEST_H
#define RE_TEST_H

#include <zephyr/kernel.h>

struct re_test_stats {
	const char *name;
	uint32_t pass;
	uint32_t fail;
};

void re_test_loop(void);
void re_test_request_stop(void);

#endif /* RE_TEST_H */
