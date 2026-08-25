/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * HTTP Server Sample for reSpeaker Clip
 *
 * Features:
 * - WiFi AP mode with DHCP server
 * - HTTP server on port 80
 * - SD card file server
 * - REST API endpoints:
 *   - GET /            - Welcome page
 *   - GET /status      - System status (JSON)
 *   - GET /led/{id}    - Get LED state
 *   - PUT /led/{id}    - Set LED state (body: 0 or 1)
 *   - GET /echo?msg=xxx - Echo message
 *   - GET /files       - List SD card files (JSON)
 *   - GET /files/*     - Download file from SD card
 *
 * Usage:
 *   1. Device starts WiFi AP (SSID=ClipHTTP_xxxx, pass=12345678)
 *   2. Connect your phone/PC to the AP
 *   3. Open browser: http://192.168.4.1/
 *   4. Or use curl:
 *      curl http://192.168.4.1/status
 *      curl http://192.168.4.1/files
 *      curl -O http://192.168.4.1/files/REC/20260319_120000/001.opus
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/shell/shell.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/drivers/gpio.h>
#include <nrfx_clock.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* Networking includes */
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/net/net_event.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/net/dhcpv4_server.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/http/parser.h>
#include <zephyr/net/dns_sd.h>
#include <zephyr/net/conn_mgr_monitor.h>
#include <zephyr/net/conn_mgr_connectivity.h>

/* File system includes */
#include <zephyr/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/fs/fs.h>
#include <ff.h>

/* JSON includes */
#include <zephyr/data/json.h>

LOG_MODULE_REGISTER(http_server, LOG_LEVEL_INF);

/* =========================================================================
 * Configuration
 * ========================================================================= */
#define HTTP_PORT            80
#define MAX_CLIENT_QUEUE     2
#define STACK_SIZE           4096
#define THREAD_PRIORITY      K_PRIO_COOP(CONFIG_NUM_COOP_PRIORITIES - 1)

#define WIFI_AP_SSID_PREFIX  "ClipHTTP_"
#define WIFI_AP_PASSWORD     "12345678"
#define WIFI_AP_CHANNEL      36
#define WIFI_AP_REG_DOMAIN   "US"
#define DHCPV4_POOL_START    "192.168.4.10"

/* SD Card mount point */
#define SD_MOUNT_POINT       "/SD:"
#define FILE_CHUNK_SIZE      1024

/* =========================================================================
 * DNS-SD Service Registration
 * ========================================================================= */
DNS_SD_REGISTER_TCP_SERVICE(http_server_sd, CONFIG_NET_HOSTNAME, "_http", "local",
                            DNS_SD_EMPTY_TXT, HTTP_PORT);

/* =========================================================================
 * HTTP Request Structure
 * ========================================================================= */
struct http_req {
    struct http_parser parser;
    int socket;
    bool received_all;
    enum http_method method;
    const char *url;
    size_t url_len;
    const char *body;
    size_t body_len;
};

/* =========================================================================
 * LED State (using GPIO directly since no DK library on this board)
 * ========================================================================= */
#define LED0_NODE DT_ALIAS(led0)
#if DT_NODE_HAS_STATUS(LED0_NODE, okay)
static const struct gpio_dt_spec led0 = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
#define HAS_LED0 1
#else
#define HAS_LED0 0
#endif

#define LED1_NODE DT_ALIAS(led1)
#if DT_NODE_HAS_STATUS(LED1_NODE, okay)
static const struct gpio_dt_spec led1 = GPIO_DT_SPEC_GET(LED1_NODE, gpios);
#define HAS_LED1 1
#else
#define HAS_LED1 0
#endif

static uint8_t led_states[2] = {0, 0};
static bool leds_initialized;

/* =========================================================================
 * SD Card Storage
 * ========================================================================= */
static FATFS fat_fs;
static struct fs_mount_t sd_mp = {
    .type = FS_FATFS,
    .fs_data = &fat_fs,
    .mnt_point = SD_MOUNT_POINT,
};
static bool sd_mounted;

static int sd_init(void)
{
    int ret;

    ret = disk_access_init("SD");
    if (ret != 0) {
        LOG_WRN("SD card init failed: %d", ret);
        return ret;
    }

    ret = fs_mount(&sd_mp);
    if (ret != 0) {
        LOG_WRN("SD card mount failed: %d", ret);
        return ret;
    }

    sd_mounted = true;
    LOG_INF("SD card mounted at %s", SD_MOUNT_POINT);
    return 0;
}

/* Get MIME type based on file extension */
static const char *get_mime_type(const char *filename)
{
    const char *ext = strrchr(filename, '.');
    if (!ext) {
        return "application/octet-stream";
    }

    if (strcasecmp(ext, ".opus") == 0) return "audio/opus";
    if (strcasecmp(ext, ".mp3") == 0) return "audio/mpeg";
    if (strcasecmp(ext, ".wav") == 0) return "audio/wav";
    if (strcasecmp(ext, ".json") == 0) return "application/json";
    if (strcasecmp(ext, ".txt") == 0) return "text/plain";
    if (strcasecmp(ext, ".html") == 0) return "text/html";
    if (strcasecmp(ext, ".css") == 0) return "text/css";
    if (strcasecmp(ext, ".js") == 0) return "application/javascript";
    if (strcasecmp(ext, ".png") == 0) return "image/png";
    if (strcasecmp(ext, ".jpg") == 0 || strcasecmp(ext, ".jpeg") == 0) return "image/jpeg";
    if (strcasecmp(ext, ".gif") == 0) return "image/gif";
    if (strcasecmp(ext, ".bin") == 0) return "application/octet-stream";

    return "application/octet-stream";
}

/* =========================================================================
 * HTTP Response Strings
 * ========================================================================= */
static const char response_200[] = "HTTP/1.1 200 OK\r\n";
static const char response_206[] = "HTTP/1.1 206 Partial Content\r\n";
static const char response_403[] = "HTTP/1.1 403 Forbidden\r\n\r\nForbidden";
static const char response_404[] = "HTTP/1.1 404 Not Found\r\n\r\nNot Found";
static const char response_405[] = "HTTP/1.1 405 Method Not Allowed\r\n\r\nMethod Not Allowed";
static const char response_500[] = "HTTP/1.1 500 Internal Server Error\r\n\r\nInternal Server Error";
static const char content_type_html[] = "Content-Type: text/html\r\n";
static const char content_type_json[] = "Content-Type: application/json\r\n";
static const char content_type_octet[] = "Content-Type: application/octet-stream\r\n";

/* =========================================================================
 * Threads and Sockets
 * ========================================================================= */
K_THREAD_STACK_ARRAY_DEFINE(tcp_handler_stack, MAX_CLIENT_QUEUE, STACK_SIZE);
static struct k_thread tcp_handler_thread[MAX_CLIENT_QUEUE];
static k_tid_t tcp_handler_tid[MAX_CLIENT_QUEUE];

static int tcp_listen_sock = -1;
static int tcp_accepted[MAX_CLIENT_QUEUE];
static bool http_running;

static struct http_parser_settings parser_settings;

/* =========================================================================
 * WiFi AP State
 * ========================================================================= */
static bool ap_started;
static bool l4_connected;
static char ap_ssid[32] = "ClipHTTP_Test";
static struct net_mgmt_event_callback wifi_mgmt_cb;
static struct net_mgmt_event_callback l4_mgmt_cb;
static K_SEM_DEFINE(network_ready, 0, 1);

/* =========================================================================
 * LED Functions
 * ========================================================================= */
static int leds_init(void)
{
    int ret = 0;

    if (leds_initialized) {
        return 0;
    }

#if HAS_LED0
    if (!gpio_is_ready_dt(&led0)) {
        LOG_WRN("LED0 not ready");
    } else {
        ret = gpio_pin_configure_dt(&led0, GPIO_OUTPUT_INACTIVE);
        if (ret < 0) {
            LOG_WRN("LED0 config failed: %d", ret);
        }
    }
#endif

#if HAS_LED1
    if (!gpio_is_ready_dt(&led1)) {
        LOG_WRN("LED1 not ready");
    } else {
        ret = gpio_pin_configure_dt(&led1, GPIO_OUTPUT_INACTIVE);
        if (ret < 0) {
            LOG_WRN("LED1 config failed: %d", ret);
        }
    }
#endif

    leds_initialized = true;
    return ret;
}

static void led_set(size_t led_id, uint8_t state)
{
    if (led_id < 1 || led_id > 2) {
        return;
    }

    size_t idx = led_id - 1;
    led_states[idx] = state ? 1 : 0;

#if HAS_LED0
    if (idx == 0) {
        gpio_pin_set_dt(&led0, led_states[idx]);
    }
#endif

#if HAS_LED1
    if (idx == 1) {
        gpio_pin_set_dt(&led1, led_states[idx]);
    }
#endif

    LOG_INF("LED%d set to %s", led_id, state ? "ON" : "OFF");
}

/* =========================================================================
 * HTTP Request Handlers
 * ========================================================================= */

/* GET / - Welcome page */
static void handle_root(struct http_req *request)
{
    char buf[768];
    int len;

    static const char html[] =
        "<!DOCTYPE html>"
        "<html><head><title>reSpeaker Clip</title>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>body{font-family:Arial,sans-serif;margin:40px;background:#f5f5f5}"
        "h1{color:#333}.endpoint{background:#fff;padding:15px;margin:10px 0;"
        "border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}"
        "code{background:#e8e8e8;padding:2px 6px;border-radius:3px}"
        "a{color:#0066cc;text-decoration:none}a:hover{text-decoration:underline}</style></head>"
        "<body><h1>reSpeaker Clip HTTP Server</h1>"
        "<div class='endpoint'><h3>API Endpoints</h3>"
        "<p><code>GET /</code> - This page</p>"
        "<p><code>GET /status</code> - System status (JSON)</p>"
        "<p><code>GET /led/1</code> - Get LED1 state</p>"
        "<p><code>PUT /led/1</code> - Set LED1 (body: 0 or 1)</p>"
        "<p><code>GET /echo?msg=hello</code> - Echo message</p>"
        "</div>"
        "<div class='endpoint'><h3>File Server</h3>"
        "<p><a href='/files'><code>GET /files</code></a> - List SD card files</p>"
        "<p><code>GET /files/path/to/file</code> - Download file</p>"
        "</div></body></html>";

    len = snprintk(buf, sizeof(buf), "%s%sContent-Length: %d\r\n\r\n%s",
                   response_200, content_type_html, (int)strlen(html), html);

    send(request->socket, buf, len, 0);
}

/* GET /status - System status JSON */
static void handle_status(struct http_req *request)
{
    char buf[256];
    char json[128];
    int len;

    len = snprintk(json, sizeof(json),
                   "{\"ssid\":\"%s\",\"uptime\":%lld,\"leds\":[%d,%d],\"sd_mounted\":%s}",
                   ap_ssid, k_uptime_get() / 1000, led_states[0], led_states[1],
                   sd_mounted ? "true" : "false");

    len = snprintk(buf, sizeof(buf), "%s%sContent-Length: %d\r\n\r\n%s",
                   response_200, content_type_json, len, json);

    send(request->socket, buf, len, 0);
}

/* GET/PUT /led/{id} - LED control */
static void handle_led(struct http_req *request, size_t led_id)
{
    char buf[256];
    int len;

    if (led_id < 1 || led_id > 2) {
        len = snprintk(buf, sizeof(buf), "%sContent-Length: 10\r\n\r\nBad LED ID", response_404);
        send(request->socket, buf, len, 0);
        return;
    }

    size_t idx = led_id - 1;

    if (request->method == HTTP_GET) {
        char json[64];
        len = snprintk(json, sizeof(json), "{\"led\":%d,\"state\":%d}", led_id, led_states[idx]);
        len = snprintk(buf, sizeof(buf), "%s%sContent-Length: %d\r\n\r\n%s",
                       response_200, content_type_json, len, json);
        send(request->socket, buf, len, 0);
        return;
    }

    if (request->method == HTTP_PUT) {
        if (request->body_len < 1) {
            len = snprintk(buf, sizeof(buf), "%sContent-Length: 16\r\n\r\nBody required", response_403);
            send(request->socket, buf, len, 0);
            return;
        }

        uint8_t state = (request->body[0] != '0');
        led_set(led_id, state);

        char json[64];
        len = snprintk(json, sizeof(json), "{\"led\":%d,\"state\":%d}", led_id, state);
        len = snprintk(buf, sizeof(buf), "%s%sContent-Length: %d\r\n\r\n%s",
                       response_200, content_type_json, len, json);
        send(request->socket, buf, len, 0);
        return;
    }

    len = snprintk(buf, sizeof(buf), "%sContent-Length: 18\r\n\r\nMethod not allowed", response_405);
    send(request->socket, buf, len, 0);
}

/* GET /echo?msg=xxx - Echo message */
static void handle_echo(struct http_req *request)
{
    char buf[512];
    char url[128];
    char msg[64] = "";
    int len;

    /* Copy URL for parsing */
    size_t url_len = MIN(sizeof(url) - 1, request->url_len);
    memcpy(url, request->url, url_len);
    url[url_len] = '\0';

    /* Parse query parameter msg= */
    char *query = strchr(url, '?');
    if (query) {
        query++; /* Skip '?' */
        if (strncmp(query, "msg=", 4) == 0) {
            query += 4;
            /* URL decode simple (just handle spaces) */
            size_t i = 0;
            while (*query && i < sizeof(msg) - 1) {
                if (*query == '+') {
                    msg[i++] = ' ';
                } else if (*query == '%' && isxdigit(query[1]) && isxdigit(query[2])) {
                    char hex[3] = {query[1], query[2], 0};
                    msg[i++] = (char)strtol(hex, NULL, 16);
                    query += 2;
                } else {
                    msg[i++] = *query;
                }
                query++;
            }
            msg[i] = '\0';
        }
    }

    char json[128];
    len = snprintk(json, sizeof(json), "{\"echo\":\"%s\"}", msg);
    len = snprintk(buf, sizeof(buf), "%s%sContent-Length: %d\r\n\r\n%s",
                   response_200, content_type_json, len, json);
    send(request->socket, buf, len, 0);
}

/* =========================================================================
 * SD Card File Server
 * ========================================================================= */

/* URL decode in place */
static void url_decode(char *str)
{
    char *dst = str;
    while (*str) {
        if (*str == '%') {
            if (isxdigit(str[1]) && isxdigit(str[2])) {
                char hex[3] = {str[1], str[2], 0};
                *dst++ = (char)strtol(hex, NULL, 16);
                str += 3;
            } else {
                *dst++ = *str++;
            }
        } else if (*str == '+') {
            *dst++ = ' ';
            str++;
        } else {
            *dst++ = *str++;
        }
    }
    *dst = '\0';
}

/* GET /files - List files in directory (JSON) */
static void handle_file_list(struct http_req *request, const char *dir_path)
{
    char buf[1024];
    char full_path[128];
    struct fs_dir_t dir;
    struct fs_dirent entry;
    int len;
    int ret;

    if (!sd_mounted) {
        len = snprintk(buf, sizeof(buf), "%s%sContent-Length: 24\r\n\r\n{\"error\":\"SD not mounted\"}",
                       response_200, content_type_json);
        send(request->socket, buf, len, 0);
        return;
    }

    /* Build full path */
    if (dir_path[0] == '\0' || strcmp(dir_path, "/") == 0) {
        snprintk(full_path, sizeof(full_path), "%s", SD_MOUNT_POINT);
    } else {
        snprintk(full_path, sizeof(full_path), "%s%s", SD_MOUNT_POINT, dir_path);
    }

    fs_dir_t_init(&dir);
    ret = fs_opendir(&dir, full_path);
    if (ret != 0) {
        LOG_ERR("Failed to open dir %s: %d", full_path, ret);
        len = snprintk(buf, sizeof(buf), "%sContent-Length: 9\r\n\r\nNot Found", response_404);
        send(request->socket, buf, len, 0);
        return;
    }

    /* Start JSON response */
    len = snprintk(buf, sizeof(buf), "%s%sTransfer-Encoding: chunked\r\n\r\n",
                   response_200, content_type_json);
    send(request->socket, buf, len, 0);

    /* Send opening brace */
    len = snprintk(buf, sizeof(buf), "%lX\r\n{\r\n\"path\":\"%s\",\r\n\"files\":[\r\n",
                   (unsigned long)strlen("{\"path\":\"\",\r\n\"files\":[\r\n"),
                   dir_path[0] ? dir_path : "/");
    send(request->socket, buf, len, 0);

    bool first = true;
    while (fs_readdir(&dir, &entry) == 0 && entry.name[0] != '\0') {
        char entry_json[256];
        const char *type_str = (entry.type == FS_DIR_ENTRY_DIR) ? "dir" : "file";

        len = snprintk(entry_json, sizeof(entry_json),
                       "%s{\"name\":\"%s\",\"type\":\"%s\",\"size\":%u}",
                       first ? "" : ",\r\n",
                       entry.name, type_str, (unsigned int)entry.size);

        /* Send chunk */
        char chunk_header[16];
        int header_len = snprintk(chunk_header, sizeof(chunk_header), "%X\r\n", len);
        send(request->socket, chunk_header, header_len, 0);
        send(request->socket, entry_json, len, 0);
        send(request->socket, "\r\n", 2, 0);

        first = false;
    }

    fs_closedir(&dir);

    /* Send closing */
    const char *closing = "]\r\n}\r\n";
    char chunk_header[16];
    int header_len = snprintk(chunk_header, sizeof(chunk_header), "%zX\r\n", strlen(closing));
    send(request->socket, chunk_header, header_len, 0);
    send(request->socket, closing, strlen(closing), 0);
    send(request->socket, "\r\n", 2, 0);

    /* Send final chunk */
    send(request->socket, "0\r\n\r\n", 5, 0);
}

/* GET /files/path/to/file - Download file */
static void handle_file_download(struct http_req *request, const char *file_path)
{
    char buf[512];
    char full_path[192];
    struct fs_file_t file;
    struct fs_dirent entry;
    int len;
    int ret;
    ssize_t bytes_read;

    if (!sd_mounted) {
        len = snprintk(buf, sizeof(buf), "%sContent-Length: 24\r\n\r\nSD card not mounted", response_404);
        send(request->socket, buf, len, 0);
        return;
    }

    /* Build full path */
    snprintk(full_path, sizeof(full_path), "%s%s", SD_MOUNT_POINT, file_path);

    /* Check if file exists and get size */
    ret = fs_stat(full_path, &entry);
    if (ret != 0 || entry.type != FS_DIR_ENTRY_FILE) {
        LOG_WRN("File not found: %s", full_path);
        len = snprintk(buf, sizeof(buf), "%sContent-Length: 9\r\n\r\nNot Found", response_404);
        send(request->socket, buf, len, 0);
        return;
    }

    /* Open file */
    fs_file_t_init(&file);
    ret = fs_open(&file, full_path, FS_O_READ);
    if (ret != 0) {
        LOG_ERR("Failed to open file %s: %d", full_path, ret);
        len = snprintk(buf, sizeof(buf), "%sContent-Length: 14\r\n\r\nInternal Error", response_500);
        send(request->socket, buf, len, 0);
        return;
    }

    /* Get filename for Content-Disposition */
    const char *filename = strrchr(file_path, '/');
    filename = filename ? filename + 1 : file_path;

    /* Get MIME type */
    const char *mime_type = get_mime_type(filename);

    /* Send HTTP headers */
    len = snprintk(buf, sizeof(buf),
                   "HTTP/1.1 200 OK\r\n"
                   "Content-Type: %s\r\n"
                   "Content-Length: %u\r\n"
                   "Content-Disposition: attachment; filename=\"%s\"\r\n"
                   "\r\n",
                   mime_type, (unsigned int)entry.size, filename);
    send(request->socket, buf, len, 0);

    LOG_INF("Downloading %s (%u bytes)", filename, (unsigned int)entry.size);

    /* Send file content in chunks */
    while ((bytes_read = fs_read(&file, buf, sizeof(buf))) > 0) {
        ssize_t sent = send(request->socket, buf, bytes_read, 0);
        if (sent < 0) {
            LOG_ERR("Send error: %d", -errno);
            break;
        }
    }

    fs_close(&file);
    LOG_INF("Download complete: %s", filename);
}

/* Main HTTP request router */
static void handle_http_request(struct http_req *request)
{
    char url[128];
    size_t url_len = MIN(sizeof(url) - 1, request->url_len);

    memcpy(url, request->url, url_len);
    url[url_len] = '\0';

    /* Remove query string for routing */
    char *query = strchr(url, '?');
    if (query) {
        *query = '\0';
    }

    LOG_INF("%s %s", http_method_str(request->method), url);

    /* Route: GET / */
    if (strcmp(url, "/") == 0 && request->method == HTTP_GET) {
        handle_root(request);
        return;
    }

    /* Route: GET /status */
    if (strcmp(url, "/status") == 0 && request->method == HTTP_GET) {
        handle_status(request);
        return;
    }

    /* Route: GET/PUT /led/{id} */
    size_t led_id;
    if (sscanf(url, "/led/%u", &led_id) == 1) {
        handle_led(request, led_id);
        return;
    }

    /* Route: GET /echo */
    if (strncmp(url, "/echo", 5) == 0 && request->method == HTTP_GET) {
        handle_echo(request);
        return;
    }

    /* Route: GET /files - File server */
    if (strncmp(url, "/files", 6) == 0 && request->method == HTTP_GET) {
        if (!sd_mounted) {
            char buf[128];
            int len = snprintk(buf, sizeof(buf), "%sContent-Length: 20\r\n\r\nSD card not mounted", response_404);
            send(request->socket, buf, len, 0);
            return;
        }

        /* Check if listing directory or downloading file */
        if (strlen(url) == 6 || strcmp(url, "/files/") == 0) {
            /* List root directory */
            handle_file_list(request, "/");
        } else {
            /* Download file: /files/path/to/file */
            const char *file_path = url + 6; /* Skip "/files" */
            if (*file_path == '/') {
                file_path++; /* Skip leading slash */
            }
            handle_file_download(request, file_path);
        }
        return;
    }

    /* 404 Not Found */
    char buf[128];
    int len = snprintk(buf, sizeof(buf), "%sContent-Length: 9\r\n\r\nNot Found", response_404);
    send(request->socket, buf, len, 0);
}

/* =========================================================================
 * HTTP Parser Callbacks
 * ========================================================================= */
static int on_body(struct http_parser *parser, const char *at, size_t length)
{
    struct http_req *req = CONTAINER_OF(parser, struct http_req, parser);
    req->body = at;
    req->body_len = length;
    return 0;
}

static int on_headers_complete(struct http_parser *parser)
{
    struct http_req *req = CONTAINER_OF(parser, struct http_req, parser);
    req->method = parser->method;
    return 0;
}

static int on_message_begin(struct http_parser *parser)
{
    struct http_req *req = CONTAINER_OF(parser, struct http_req, parser);
    req->received_all = false;
    req->url = NULL;
    req->url_len = 0;
    req->body = NULL;
    req->body_len = 0;
    return 0;
}

static int on_message_complete(struct http_parser *parser)
{
    struct http_req *req = CONTAINER_OF(parser, struct http_req, parser);
    req->received_all = true;
    return 0;
}

static int on_url(struct http_parser *parser, const char *at, size_t length)
{
    struct http_req *req = CONTAINER_OF(parser, struct http_req, parser);
    req->url = at;
    req->url_len = length;
    return 0;
}

static void parser_init(void)
{
    http_parser_settings_init(&parser_settings);
    parser_settings.on_body = on_body;
    parser_settings.on_headers_complete = on_headers_complete;
    parser_settings.on_message_begin = on_message_begin;
    parser_settings.on_message_complete = on_message_complete;
    parser_settings.on_url = on_url;
}

/* =========================================================================
 * TCP Server
 * ========================================================================= */
static int setup_server(int *sock, struct sockaddr *bind_addr, socklen_t bind_addrlen)
{
    int ret;

    *sock = socket(bind_addr->sa_family, SOCK_STREAM, IPPROTO_TCP);
    if (*sock < 0) {
        LOG_ERR("Failed to create socket: %d", errno);
        return -errno;
    }

    ret = bind(*sock, bind_addr, bind_addrlen);
    if (ret < 0) {
        LOG_ERR("Failed to bind socket: %d", errno);
        close(*sock);
        *sock = -1;
        return -errno;
    }

    ret = listen(*sock, MAX_CLIENT_QUEUE);
    if (ret < 0) {
        LOG_ERR("Failed to listen: %d", errno);
        close(*sock);
        *sock = -1;
        return -errno;
    }

    return 0;
}

static void client_conn_handler(void *ptr1, void *ptr2, void *ptr3)
{
    ARG_UNUSED(ptr1);
    int *sock = ptr2;
    k_tid_t *in_use = ptr3;
    int received;
    char buf[1024];
    size_t offset = 0;
    struct http_req request = {
        .socket = *sock,
    };

    http_parser_init(&request.parser, HTTP_REQUEST);

    while (http_running) {
        received = recv(request.socket, buf + offset, sizeof(buf) - offset, 0);
        if (received == 0) {
            LOG_INF("[sock %d] Connection closed by peer", request.socket);
            break;
        } else if (received < 0) {
            LOG_ERR("[sock %d] Recv error: %d", request.socket, -errno);
            break;
        }

        http_parser_execute(&request.parser, &parser_settings, buf + offset, received);
        offset += received;

        if (offset >= sizeof(buf)) {
            offset = 0;
        }

        if (request.received_all) {
            handle_http_request(&request);
            break;
        }
    }

    close(request.socket);
    *sock = -1;
    *in_use = NULL;
}

static int get_free_slot(int *accepted)
{
    for (int i = 0; i < MAX_CLIENT_QUEUE; i++) {
        if (accepted[i] < 0) {
            return i;
        }
    }
    return -1;
}

static int process_tcp(int *sock, int *accepted)
{
    int client;
    int slot;
    struct sockaddr_in client_addr;
    socklen_t client_addr_len = sizeof(client_addr);
    char addr_str[INET_ADDRSTRLEN];

    client = accept(*sock, (struct sockaddr *)&client_addr, &client_addr_len);
    if (client < 0) {
        LOG_ERR("Accept error: %d", -errno);
        return -errno;
    }

    slot = get_free_slot(accepted);
    if (slot < 0) {
        LOG_WRN("No free slot, rejecting connection");
        close(client);
        return 0;
    }

    accepted[slot] = client;

    net_addr_ntop(client_addr.sin_family, &client_addr.sin_addr, addr_str, sizeof(addr_str));
    LOG_INF("[sock %d] Connection from %s:%d", client, addr_str,
            ntohs(client_addr.sin_port));

    tcp_handler_tid[slot] = k_thread_create(
        &tcp_handler_thread[slot], tcp_handler_stack[slot],
        K_THREAD_STACK_SIZEOF(tcp_handler_stack[slot]),
        (k_thread_entry_t)client_conn_handler,
        INT_TO_POINTER(slot), &accepted[slot], &tcp_handler_tid[slot],
        THREAD_PRIORITY, 0, K_NO_WAIT);

    return 0;
}

/* HTTP server thread */
static void http_server_thread(void *p1, void *p2, void *p3)
{
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    int ret;
    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_port = htons(HTTP_PORT),
        .sin_addr.s_addr = INADDR_ANY,
    };

    for (int i = 0; i < MAX_CLIENT_QUEUE; i++) {
        tcp_accepted[i] = -1;
    }

    ret = setup_server(&tcp_listen_sock, (struct sockaddr *)&addr, sizeof(addr));
    if (ret < 0) {
        LOG_ERR("Failed to setup HTTP server: %d", ret);
        return;
    }

    LOG_INF("HTTP server listening on port %d", HTTP_PORT);
    printk("[HTTP] Server started on http://192.168.4.1/\n");

    while (http_running) {
        ret = process_tcp(&tcp_listen_sock, tcp_accepted);
        if (ret < 0) {
            break;
        }
    }

    /* Cleanup */
    for (int i = 0; i < MAX_CLIENT_QUEUE; i++) {
        if (tcp_accepted[i] >= 0) {
            close(tcp_accepted[i]);
            tcp_accepted[i] = -1;
        }
    }
    if (tcp_listen_sock >= 0) {
        close(tcp_listen_sock);
        tcp_listen_sock = -1;
    }

    LOG_INF("HTTP server stopped");
}

K_THREAD_DEFINE(http_thread_id, STACK_SIZE, http_server_thread, NULL, NULL, NULL,
                THREAD_PRIORITY, 0, -1);

/* =========================================================================
 * WiFi AP Functions
 * ========================================================================= */
static void generate_ap_ssid(void)
{
    uint8_t chip_id[16];
    ssize_t len = hwinfo_get_device_id(chip_id, sizeof(chip_id));

    if (len > 0) {
        uint32_t suffix = 0;
        int off = len > 4 ? len - 4 : 0;

        for (int i = 0; i < 4 && (off + i) < len; i++) {
            suffix = (suffix << 8) | chip_id[off + i];
        }
        snprintf(ap_ssid, sizeof(ap_ssid), "%s%04X",
                 WIFI_AP_SSID_PREFIX, (unsigned)(suffix & 0xFFFF));
    }
}

static void l4_event_handler(struct net_mgmt_event_callback *cb,
                              uint64_t mgmt_event, struct net_if *iface)
{
    switch (mgmt_event) {
    case NET_EVENT_L4_CONNECTED:
        LOG_INF("Network layer connected");
        l4_connected = true;
        k_sem_give(&network_ready);
        break;
    case NET_EVENT_L4_DISCONNECTED:
        LOG_INF("Network layer disconnected");
        if (l4_connected) {
            l4_connected = false;
        }
        k_sem_reset(&network_ready);
        break;
    default:
        break;
    }
}

static void wifi_event_handler(struct net_mgmt_event_callback *cb,
                               uint64_t mgmt_event, struct net_if *iface)
{
    switch (mgmt_event) {
    case NET_EVENT_WIFI_AP_ENABLE_RESULT:
        LOG_INF("WiFi AP enabled");
        break;
    case NET_EVENT_WIFI_AP_STA_CONNECTED:
        printk("[WiFi] Station connected\n");
        break;
    case NET_EVENT_WIFI_AP_STA_DISCONNECTED:
        printk("[WiFi] Station disconnected\n");
        break;
    default:
        break;
    }
}

static int configure_dhcp_server(void)
{
    struct net_if *iface = net_if_get_default();
    struct in_addr pool_start;
    int ret;

    if (!iface) {
        return -ENODEV;
    }

    net_addr_pton(AF_INET, DHCPV4_POOL_START, &pool_start.s_addr);
    ret = net_dhcpv4_server_start(iface, &pool_start);
    return (ret == -EALREADY) ? 0 : ret;
}

static int do_wifi_ap_start(void)
{
    struct net_if *iface = net_if_get_default();
    struct wifi_connect_req_params req;
    struct wifi_reg_domain regd = {0};
    int ret;

    if (!iface) {
        return -ENODEV;
    }

    if (ap_started) {
        return 0;
    }

    /* Set regulatory domain */
    regd.oper = WIFI_MGMT_SET;
    strncpy(regd.country_code, WIFI_AP_REG_DOMAIN, WIFI_COUNTRY_CODE_LEN + 1);
    ret = net_mgmt(NET_REQUEST_WIFI_REG_DOMAIN, iface, &regd, sizeof(regd));
    if (ret) {
        LOG_WRN("Reg domain set failed: %d", ret);
    }

    /* Configure AP */
    memset(&req, 0, sizeof(req));
    req.ssid = (const uint8_t *)ap_ssid;
    req.ssid_length = strlen(ap_ssid);
    req.psk = (const uint8_t *)WIFI_AP_PASSWORD;
    req.psk_length = strlen(WIFI_AP_PASSWORD);
    req.channel = WIFI_AP_CHANNEL;
    req.security = WIFI_SECURITY_TYPE_PSK;
    req.mfp = WIFI_MFP_OPTIONAL;
    req.band = WIFI_FREQ_BAND_5_GHZ;

    ret = net_mgmt(NET_REQUEST_WIFI_AP_ENABLE, iface, &req, sizeof(req));
    if (ret) {
        LOG_ERR("AP enable failed: %d", ret);
        return ret;
    }

    k_sleep(K_SECONDS(2));

    ret = configure_dhcp_server();
    if (ret) {
        LOG_WRN("DHCP server start failed: %d", ret);
    }

    ap_started = true;
    LOG_INF("WiFi AP started: SSID=%s ch=%d IP=192.168.4.1", ap_ssid, WIFI_AP_CHANNEL);

    return 0;
}

static int do_wifi_ap_stop(void)
{
    struct net_if *iface = net_if_get_default();

    if (!iface || !ap_started) {
        return 0;
    }

    net_dhcpv4_server_stop(iface);
    net_mgmt(NET_REQUEST_WIFI_AP_DISABLE, iface, NULL, 0);
    ap_started = false;
    LOG_INF("WiFi AP stopped");

    return 0;
}

/* =========================================================================
 * HTTP Server Control
 * ========================================================================= */
static int do_http_start(void)
{
    if (http_running) {
        return 0;
    }

    if (!ap_started) {
        LOG_WRN("WiFi AP not started");
        return -ENETDOWN;
    }

    /* Wait for network layer to be ready */
    if (!l4_connected) {
        LOG_INF("Waiting for network layer...");
        if (k_sem_take(&network_ready, K_SECONDS(5)) != 0) {
            LOG_ERR("Network layer not ready timeout");
            return -ENETUNREACH;
        }
    }

    http_running = true;
    k_thread_start(http_thread_id);

    return 0;
}

static int do_http_stop(void)
{
    if (!http_running) {
        return 0;
    }

    http_running = false;

    /* Wake up the thread by connecting to the socket */
    /* This will cause accept() to return and check http_running */
    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_port = htons(HTTP_PORT),
    };
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock >= 0) {
        connect(sock, (struct sockaddr *)&addr, sizeof(addr));
        close(sock);
    }

    k_thread_join(http_thread_id, K_SECONDS(2));

    return 0;
}

/* =========================================================================
 * Shell Commands
 * ========================================================================= */
static int cmd_http_start(const struct shell *sh, size_t argc, char **argv)
{
    int ret = do_http_start();
    if (ret) {
        shell_error(sh, "HTTP start failed: %d", ret);
    } else {
        shell_print(sh, "HTTP server started on http://192.168.4.1/");
    }
    return ret;
}

static int cmd_http_stop(const struct shell *sh, size_t argc, char **argv)
{
    do_http_stop();
    shell_print(sh, "HTTP server stopped");
    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(http_cmds,
    SHELL_CMD(start, NULL, "Start HTTP server", cmd_http_start),
    SHELL_CMD(stop, NULL, "Stop HTTP server", cmd_http_stop),
    SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(http, &http_cmds, "HTTP server commands", NULL);

static int cmd_wifi_start(const struct shell *sh, size_t argc, char **argv)
{
    int ret = do_wifi_ap_start();
    if (ret) {
        shell_error(sh, "WiFi AP start failed: %d", ret);
    } else {
        shell_print(sh, "SSID=%s pass=%s IP=192.168.4.1", ap_ssid, WIFI_AP_PASSWORD);
    }
    return ret;
}

static int cmd_wifi_stop(const struct shell *sh, size_t argc, char **argv)
{
    do_wifi_ap_stop();
    shell_print(sh, "WiFi AP stopped");
    return 0;
}

static int cmd_wifi_status(const struct shell *sh, size_t argc, char **argv)
{
    shell_print(sh, "SSID=%s started=%s HTTP=%s",
                ap_ssid, ap_started ? "yes" : "no", http_running ? "running" : "stopped");
    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(wifi_ap_cmds,
    SHELL_CMD(start, NULL, "Start WiFi AP", cmd_wifi_start),
    SHELL_CMD(stop, NULL, "Stop WiFi AP", cmd_wifi_stop),
    SHELL_CMD(status, NULL, "WiFi AP status", cmd_wifi_status),
    SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(wifi_ap, &wifi_ap_cmds, "WiFi AP commands", NULL);

/* =========================================================================
 * Main
 * ========================================================================= */
int main(void)
{
    int ret;

#ifdef CLOCK_FEATURE_HFCLK_DIVIDE_PRESENT
    nrfx_clock_divider_set(NRF_CLOCK_DOMAIN_HFCLK, NRF_CLOCK_HFCLK_DIV_1);
#endif

    /* Initialize */
    generate_ap_ssid();
    parser_init();
    leds_init();

    /* Initialize SD card */
    ret = sd_init();
    if (ret) {
        printk("[SD] Init failed: %d\n", ret);
    }

    /* Setup WiFi management callback */
    net_mgmt_init_event_callback(&wifi_mgmt_cb, wifi_event_handler,
                                 NET_EVENT_WIFI_AP_ENABLE_RESULT |
                                 NET_EVENT_WIFI_AP_STA_CONNECTED |
                                 NET_EVENT_WIFI_AP_STA_DISCONNECTED);
    net_mgmt_add_event_callback(&wifi_mgmt_cb);

    /* Setup L4 (IP layer) management callback */
    net_mgmt_init_event_callback(&l4_mgmt_cb, l4_event_handler,
                                 NET_EVENT_L4_CONNECTED | NET_EVENT_L4_DISCONNECTED);
    net_mgmt_add_event_callback(&l4_mgmt_cb);

    printk("\n================================================\n");
    printk("  reSpeaker Clip: HTTP Server Sample\n");
    printk("================================================\n\n");

    /* Wait for WiFi driver to initialize */
    printk("Initializing WiFi...\n");
    k_sleep(K_SECONDS(3));

    /* Start WiFi AP */
    ret = do_wifi_ap_start();
    if (ret) {
        printk("[WiFi] AP start failed: %d - use: wifi_ap start\n", ret);
    } else {
        printk("[WiFi] SSID=%s pass=%s\n", ap_ssid, WIFI_AP_PASSWORD);
        printk("[WiFi] Connect to AP, then open http://192.168.4.1/\n\n");
    }

    /* Start HTTP server */
    k_sleep(K_SECONDS(1));
    ret = do_http_start();
    if (ret) {
        printk("[HTTP] Start failed: %d - use: http start\n", ret);
    }

    printk("Shell commands:\n");
    printk("  wifi_ap start/stop/status\n");
    printk("  http start/stop\n\n");

    printk("API endpoints:\n");
    printk("  GET  /                  - Welcome page\n");
    printk("  GET  /status            - System status\n");
    printk("  GET  /led/1             - Get LED1 state\n");
    printk("  PUT  /led/1             - Set LED1 (body: 0 or 1)\n");
    printk("  GET  /echo?msg=xxx      - Echo message\n");
    printk("  GET  /files             - List SD card files\n");
    printk("  GET  /files/path/file   - Download file\n\n");

    return 0;
}
