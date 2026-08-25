/*
 * Copyright (c) 2025 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef CLIP_TRANSPORT_H
#define CLIP_TRANSPORT_H

#include <zephyr/kernel.h>
#include <stdint.h>
#include <stdbool.h>

/* Transport Types */
#define TRANSPORT_TYPE_BLE  0
#define TRANSPORT_TYPE_UDP  1
#define TRANSPORT_TYPE_USB  2
#define TRANSPORT_TYPE_MAX  3

/* Transport Events */
#define TRANSPORT_EVT_CONNECTED    0
#define TRANSPORT_EVT_DISCONNECTED 1
#define TRANSPORT_EVT_DATA_RECEIVED 2
#define TRANSPORT_EVT_READY        3  /* Transport ready for data */
#define TRANSPORT_EVT_NOT_READY    4  /* Transport not ready */

/* Transport Configuration */
#define TRANSPORT_MAX_DATA_LEN  512

/**
 * @brief Transport event callback
 *
 * @param type Transport type
 * @param event Event ID
 * @param data Event data
 * @param len Data length
 * @param user_data User data
 */
typedef void (*transport_event_cb_t)(uint8_t type, uint8_t event,
                                     const uint8_t *data, size_t len,
                                     void *user_data);

/**
 * @brief Transport operations
 */
struct fs_file_t;  /* forward decl — repair_missing() reads an open file */

struct transport_ops {
    /**
     * @brief Send data through transport (for AT command responses)
     *
     * @param data Data to send
     * @param len Data length
     * @return Bytes sent on success, negative error code on failure
     */
    int (*send)(const uint8_t *data, uint16_t len);

    /**
     * @brief Send file data through transport (uses FILE_DATA characteristic for BLE)
     *
     * @param data Data to send
     * @param len Data length
     * @return Bytes sent on success, negative error code on failure
     */
    int (*send_file_data)(const uint8_t *data, uint16_t len);

    /**
     * @brief Selective-repeat repair: retransmit only the DATA frames the
     *        client reported missing in the last NACK bitmap. Optional: NULL
     *        means the transport can't repair by seq → caller retransmits the
     *        whole file. Reads the missing-seq bitmap from the last FILE_ACK,
     *        seeks/reads each missing frame from @p file, and resends it at its
     *        original seq with @p pace_us delay between frames.
     *
     * @param file      Open file being transferred
     * @param file_size File size in bytes (for seq→offset + last-frame length)
     * @param pace_us   Inter-frame delay during repair (0 = full speed)
     * @return Frames retransmitted on success (≥0), negative error code on failure
     */
    int (*repair_missing)(struct fs_file_t *file, uint32_t file_size, uint32_t pace_us);

    /**
     * @brief Send file start event (called before file data)
     *
     * @param session_id Session ID
     * @param filename Filename
     * @param size File size in bytes
     * @return 0 on success, negative error code on failure
     */
    int (*send_file_start)(const char *session_id, const char *filename, uint32_t size);

    /**
     * @brief Send file complete event (called after file data)
     *
     * @param filename Filename
     * @return 0 on success, negative error code on failure
     */
    int (*send_file_end)(const char *filename);

    /**
     * @brief Send transfer complete event
     *
     * @param session_id Session ID
     * @param file_count Number of files transferred
     * @return 0 on success, negative error code on failure
     */
    int (*send_transfer_done)(const char *session_id, uint32_t file_count);

    /**
     * @brief Check if transport is connected
     *
     * @return true if connected, false otherwise
     */
    bool (*is_connected)(void);

    /**
     * @brief Get transport connection pointer
     *
     * @return Connection pointer (transport-specific)
     */
    void *(*get_conn)(void);
};

/**
 * @brief Transport structure
 */
struct transport {
    uint8_t type;                      /* Transport type */
    bool ready;                         /* Ready flag */
    void *conn;                         /* Connection pointer */
    const struct transport_ops *ops;    /* Transport operations */
    transport_event_cb_t event_cb;      /* Event callback */
    void *user_data;                    /* User data for callbacks */
};

/**
 * @brief Initialize transport layer
 *
 * @return 0 on success, negative error code on failure
 */
int transport_init(void);

/**
 * @brief Register transport
 *
 * @param tp Transport structure
 * @return 0 on success, negative error code on failure
 */
int transport_register(struct transport *tp);

/**
 * @brief Unregister transport
 *
 * @param type Transport type
 * @return 0 on success, negative error code on failure
 */
int transport_unregister(uint8_t type);

/**
 * @brief Get transport by type
 *
 * @param type Transport type
 * @return Transport pointer or NULL if not found
 */
struct transport *transport_get(uint8_t type);

/**
 * @brief Get active transport (priority: BLE > TCP)
 *
 * @return Transport pointer or NULL if none active
 */
struct transport *transport_get_active(void);

/**
 * @brief Send data through specific transport
 *
 * @param type Transport type
 * @param data Data to send
 * @param len Data length
 * @return Bytes sent on success, negative error code on failure
 */
int transport_send_to(uint8_t type, const uint8_t *data, uint16_t len);

/**
 * @brief Send data through active transport
 *
 * @param data Data to send
 * @param len Data length
 * @return Bytes sent on success, negative error code on failure
 */
int transport_send(const uint8_t *data, uint16_t len);

/**
 * @brief Send file data through active transport (uses FILE_DATA characteristic for BLE)
 *
 * @param data Data to send
 * @param len Data length
 * @return Bytes sent on success, negative error code on failure
 */
int transport_send_file_data(const uint8_t *data, uint16_t len);

/**
 * @brief Send file start event through active transport
 *
 * @param session_id Session ID
 * @param filename Filename
 * @param size File size in bytes
 * @return 0 on success, negative error code on failure
 */
int transport_send_file_start(const char *session_id, const char *filename, uint32_t size);

/**
 * @brief Send file end event through active transport
 *
 * @param filename Filename
 * @return 0 on success, negative error code on failure
 */
int transport_send_file_end(const char *filename);

/**
 * @brief Send transfer done event through active transport
 *
 * @param session_id Session ID
 * @param file_count Number of files transferred
 * @return 0 on success, negative error code on failure
 */
int transport_send_transfer_done(const char *session_id, uint32_t file_count);

/**
 * @brief Check if any transport is connected
 *
 * @return true if connected, false otherwise
 */
bool transport_is_connected(void);

/**
 * @brief Notify transport event
 *
 * @param type Transport type
 * @param event Event ID
 * @param data Event data
 * @param len Data length
 */
void transport_notify_event(uint8_t type, uint8_t event,
                            const uint8_t *data, size_t len);

#endif /* CLIP_TRANSPORT_H */
