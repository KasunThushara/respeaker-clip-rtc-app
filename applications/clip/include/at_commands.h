/*
 * Copyright (c) 2025 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef CLIP_AT_COMMANDS_H
#define CLIP_AT_COMMANDS_H

#include <zephyr/kernel.h>
#include "at_server.h"

/**
 * @brief Register all AT commands
 *
 * @return 0 on success, negative error code on failure
 */
int at_commands_register(void);

#endif /* CLIP_AT_COMMANDS_H */
