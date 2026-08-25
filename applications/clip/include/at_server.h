/*
 * Copyright (c) 2025 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef CLIP_AT_SERVER_H
#define CLIP_AT_SERVER_H

#include <zephyr/kernel.h>
#include <stdbool.h>
#include <stdint.h>

/* AT Command Types */
#define AT_CMD_TYPE_TEST   0  /* AT+CMD? - Query */
#define AT_CMD_TYPE_SET    1  /* AT+CMD=... - Set */
#define AT_CMD_TYPE_EXEC   2  /* AT+CMD - Execute */
#define AT_CMD_TYPE_READ   3  /* AT+CMD? - Read (same as TEST) */

/* AT Server Error Codes */
#define AT_OK              0   /* Success */
#define AT_ERR_PARSE       1   /* Command parsing error */
#define AT_ERR_PARAM       2   /* Parameter error */
#define AT_ERR_STATE       3   /* State error */
#define AT_ERR_NOMEM       4   /* Memory insufficient */
#define AT_ERR_STORAGE     5   /* Storage error */
#define AT_ERR_NETWORK     6   /* Network error */
#define AT_ERR_TIMEOUT     7   /* Timeout */
#define AT_ERR_NOT_FOUND   8   /* Resource not found */
#define AT_ERR_NOT_ALLOWED 9   /* Operation not allowed */

/* AT Command Flags */
#define AT_CMD_SET    (1 << 0)  /* Supports SET operation */
#define AT_CMD_QUERY  (1 << 1)  /* Supports QUERY operation */
#define AT_CMD_EXEC   (1 << 2)  /* Supports EXEC operation */

/* AT Command Context */
struct at_cmd_ctx {
    const char *name;           /* Command name (e.g., "GSTAT") */
    uint8_t type;               /* Command type (SET/QUERY/EXEC) */
    const char *args;           /* Arguments string */
    uint8_t transport_type;     /* Transport type for response */
};

/* AT Command Handler */
typedef int (*at_cmd_handler_t)(struct at_cmd_ctx *ctx, char *response, size_t len);

/* AT Command Definition */
struct at_command {
    const char *name;           /* Command name */
    uint8_t flags;              /* Supported operations */
    at_cmd_handler_t handler;   /* Command handler */
};

/**
 * @brief Register an AT command
 *
 * @param cmd Command definition
 * @return 0 on success, negative error code on failure
 */
int at_server_register_cmd(const struct at_command *cmd);

/**
 * @brief Initialize AT server
 *
 * @return 0 on success, negative error code on failure
 */
int at_server_init(void);

/**
 * @brief Submit AT command to server queue
 *
 * @param data Command data
 * @param len Data length
 * @param transport_type Transport type (for response routing)
 * @return 0 on success, negative error code on failure
 */
int at_server_submit_cmd(const uint8_t *data, uint16_t len, uint8_t transport_type);

/**
 * @brief Get error message for error code
 *
 * @param err_code Error code
 * @return Error message string
 */
const char *at_server_err_msg(uint8_t err_code);

#endif /* CLIP_AT_SERVER_H */
