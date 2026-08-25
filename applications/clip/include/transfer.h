/*
 * Copyright (c) 2025 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef CLIP_TRANSFER_H
#define CLIP_TRANSFER_H

#include <stdint.h>
#include <stdbool.h>
#include <zephyr/kernel.h>
#include "transport.h"
#include "storage.h"

/* Transfer configuration */
#define TRANSFER_MAX_FILE_RETRIES  10  /* Max file-level retransmissions before abort */

/* Transfer states */
enum transfer_state {
    TRANSFER_STATE_IDLE = 0,
    TRANSFER_STATE_TRANSMITTING,
    TRANSFER_STATE_PAUSED,
    TRANSFER_STATE_COMPLETED,
    TRANSFER_STATE_ERROR
};

/* Transfer direction */
enum transfer_direction {
    TRANSFER_DIR_NONE = 0,
    TRANSFER_DIR_UPLOAD,   /* Device -> App (download) */
    TRANSFER_DIR_DOWNLOAD  /* App -> Device (upload) */
};

/* Transfer information */
struct transfer_info {
    enum transfer_state state;
    enum transfer_direction direction;
    char session_id[32];           /* Session being transferred */
    char current_file[64];         /* Current file being transferred */
    uint32_t file_index;           /* Current file index in session */
    uint32_t total_files;          /* Total files to transfer */
    uint32_t synced_files;         /* Number of files successfully synced */
    uint64_t bytes_transferred;    /* Bytes transferred so far */
    uint64_t total_bytes;          /* Total bytes to transfer */
    uint8_t progress_percent;      /* 0-100 */
    /* File number range for sequential filename generation */
    uint32_t first_file_num;       /* First file number (e.g., 1 for 0001.opus) */
    uint32_t last_file_num;        /* Last file number (e.g., 2000 for 2000.opus) */
    bool continuous;               /* Continuous mode: session is being recorded */
};

/**
 * @brief Initialize transfer subsystem
 *
 * @return 0 on success, negative error code on failure
 */
int transfer_init(void);

/**
 * @brief Start file transfer (device to app)
 *
 * @param session_id Session ID to transfer
 * @param filename Specific filename, or NULL for all files in session
 * @param tp Transport for sending data (NULL to use active transport)
 * @return 0 on success, negative error code on failure
 */
int transfer_start(const char *session_id, const char *filename, struct transport *tp);

/**
 * @brief Resume transfer starting from a specific file
 *
 * Used for reconnect scenarios - starts transfer from the specified file
 * and continues with all subsequent files in the session.
 *
 * @param session_id Session ID to transfer
 * @param start_file Filename to start from (this file and after will be transferred)
 * @param tp Transport for sending data (NULL to use active transport)
 * @return 0 on success, negative error code on failure
 */
int transfer_resume_from(const char *session_id, const char *start_file, struct transport *tp);

/**
 * @brief Cancel ongoing transfer
 *
 * @return 0 on success, negative error code on failure
 */
int transfer_cancel(void);

/**
 * @brief Get transfer progress
 *
 * @param info Output transfer information
 * @return 0 on success, negative error code on failure
 */
int transfer_get_progress(struct transfer_info *info);

/**
 * @brief Check if transfer is active
 *
 * @return true if transferring, false otherwise
 */
bool transfer_is_active(void);

/**
 * @brief Get current transfer state
 *
 * @return Current transfer state
 */
enum transfer_state transfer_get_state(void);

/**
 * @brief Get current transfer session info
 *
 * @param session_id Output buffer for session ID (can be NULL)
 * @param len Size of session_id buffer
 * @param filename Output buffer for current filename (can be NULL)
 * @param filename_len Size of filename buffer
 * @return 0 on success, negative error code on failure
 */
int transfer_get_current_session(char *session_id, size_t len, char *filename, size_t filename_len);

/**
 * @brief Get total files count for current transfer
 *
 * @return Total files count, or 0 if no active transfer
 */
uint32_t transfer_get_total_files(void);

/**
 * @brief Set synced files count for a session
 *
 * Updates the synced field in session.json
 *
 * @param session_id Session ID
 * @param count Number of synced files
 * @return 0 on success, negative error code on failure
 */
int transfer_set_synced_files(const char *session_id, uint32_t count);

#endif /* CLIP_TRANSFER_H */
