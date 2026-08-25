/*
 * Copyright (c) 2025 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef CLIP_TRANSPORT_UDP_H
#define CLIP_TRANSPORT_UDP_H

#include <stdint.h>
#include <stdbool.h>
#include <sys/socket.h>

/**
 * @brief CLIP UDP Transfer Protocol Frame Types
 *
 * Fire-and-forget DATA frames with per-file CRC32 verification.
 * Minimal RAM footprint — no frame buffering required.
 */
#define UDP_FRAME_DATA          0x01  /* Server→Client: file data with seq + CRC */
#define UDP_FRAME_FILE_ACK      0x03  /* Client→Server: file verification result (OK/NACK) */
#define UDP_FRAME_FILE_START    0x10  /* Server→Client: begin file transfer */
#define UDP_FRAME_FILE_END      0x11  /* Server→Client: end file (full-file CRC32) */
#define UDP_FRAME_TRANSFER_DONE 0x12  /* Server→Client: all files complete */
#define UDP_FRAME_AT_RESP       0x20  /* Server→Client: AT command response (JSON) */
#define UDP_FRAME_HEARTBEAT     0x30  /* Bidirectional: keepalive */

/**
 * @brief Frame header sizes
 */
#define UDP_DATA_HEADER_SIZE    9   /* type(1) + seq(2) + len(2) + crc32(4) */
#define UDP_FILE_ACK_FRAME_SIZE 2   /* type(1) + result(1) */
#define UDP_HEARTBEAT_SIZE      5   /* type(1) + timestamp(4) */

/**
 * @brief Protocol limits
 */
#define UDP_MAX_DATA_PER_FRAME  1024 /* Max data payload per UDP frame */
#define UDP_SEQ_MODULO          4096 /* Sequence number space (12-bit effective) */
#define UDP_MAX_RETRIES         5    /* Max file-level retransmissions before abort */

/**
 * @brief DATA frame format (Server→Client)
 *
 * [type: 1][seq_lo: 1][seq_hi: 1][len_lo: 1][len_hi: 1][crc32: 4][data: len]
 *
 * - type: UDP_FRAME_DATA (0x01)
 * - seq: uint16 LE, per-file sequence number
 * - len: uint16 LE, data length (0 to UDP_MAX_DATA_PER_FRAME)
 * - crc32: IEEE CRC32 of data field only (initial 0xFFFFFFFF)
 * - data: raw file data
 */

/**
 * @brief FILE_ACK frame format (Client→Server)
 *
 * [type: 1][result: 1]
 *
 * - type: UDP_FRAME_FILE_ACK (0x03)
 * - result: 0x00 = CRC OK, 0x01 = CRC mismatch (request retransmit)
 *
 * Sent by client after receiving FILE_END and verifying full-file CRC32.
 */

/**
 * @brief FILE_START frame format (Server→Client)
 *
 * [type: 1][fn_len: 1][filename: fn_len][file_size: 4 bytes LE]
 */

/**
 * @brief FILE_END frame format (Server→Client)
 *
 * [type: 1][crc32: 4 bytes LE]
 *
 * CRC32 of complete file data (IEEE, initial 0xFFFFFFFF).
 * Client independently computes and compares.
 */

/**
 * @brief TRANSFER_DONE frame format (Server→Client)
 *
 * [type: 1][sid_len: 1][session_id: sid_len][file_count: 4 bytes LE]
 */

/**
 * @brief AT_RESP frame format (Server→Client)
 *
 * [type: 1][len_lo: 1][len_hi: 1][json_data: len]
 */

/**
 * @brief HEARTBEAT frame format (Bidirectional)
 *
 * [type: 1][timestamp: 4 bytes LE]
 */

/* ---- Public API ---- */

/**
 * @brief Initialize UDP transport
 *
 * @return 0 on success, negative error code on failure
 */
int transport_udp_init(void);

/**
 * @brief Send data through UDP (for AT command responses)
 *
 * @param data Data to send
 * @param len Data length
 * @return Bytes sent on success, negative error code on failure
 */
int transport_udp_send(const uint8_t *data, uint16_t len);

/**
 * @brief Send file data through UDP (fire-and-forget with pacing)
 *
 * Sends DATA frames without waiting for per-frame ACK.
 * Slices data > UDP_MAX_DATA_PER_FRAME into multiple frames.
 *
 * @param data Data to send
 * @param len Data length
 * @return Bytes sent on success, negative error code on failure
 */
int transport_udp_send_file_data(const uint8_t *data, uint16_t len);

/**
 * @brief Send file start frame (fire-and-forget)
 *
 * @param filename Filename
 * @param file_size File size in bytes
 * @return 0 on success, negative error code on failure
 */
int transport_udp_send_file_start(const char *filename, uint32_t file_size);

/**
 * @brief Send file end frame with full-file CRC32, wait for FILE_ACK
 *
 * Returns 0 on CRC OK, -EAGAIN if client requests retransmit,
 * -ETIMEDOUT if no response received.
 *
 * @return 0 on success, negative error code on failure
 */
int transport_udp_send_file_end(void);

/**
 * @brief Send transfer done frame (fire-and-forget)
 *
 * @param session_id Session ID
 * @param file_count Number of files transferred
 * @return 0 on success, negative error code on failure
 */
int transport_udp_send_transfer_done(const char *session_id, uint32_t file_count);

/**
 * @brief Send AT command response with FRAME_AT_RESP framing
 *
 * @param data Response data
 * @param len Response length
 * @return Bytes sent on success, negative error code on failure
 */
int transport_udp_send_response(const uint8_t *data, uint16_t len);

/**
 * @brief Check if UDP transport is active
 */
bool transport_udp_is_active(void);

/**
 * @brief Update UDP connection state (called from wifi_udp)
 */
void transport_udp_update_active(bool active);

/**
 * @brief Update client address for responses (called from wifi_udp)
 */
void transport_udp_update_client_addr(const struct sockaddr *addr, socklen_t len);

/**
 * @brief Notify FILE_ACK received (called from wifi_udp server thread)
 *
 * Signals the send thread that file verification result has arrived.
 *
 * @param result 0x00 = CRC OK, 0x01 = CRC mismatch
 * @param bitmap   Missing-seq bitmap if result is NACK and the client supports
 *                 selective retransmit (bit i set = seq i missing), NULL otherwise.
 * @param bitmap_len Bitmap length in bytes (0 = no bitmap → whole-file retransmit).
 * @param total_seqs Total DATA frames in the file (bitmap coverage).
 */
void transport_udp_notify_file_ack(uint8_t result, const uint8_t *bitmap,
				   uint16_t bitmap_len, uint16_t total_seqs);

/**
 * @brief Get UDP transport pointer for registration
 */
struct transport *transport_udp_get(void);

/**
 * @brief Reset per-file transfer state (call at start of each file)
 */
void transport_udp_reset_file_state(void);

#endif /* CLIP_TRANSPORT_UDP_H */
