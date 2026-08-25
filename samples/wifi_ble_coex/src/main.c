/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * WiFi AP + BLE Coexistence Test Sample
 *
 * Features:
 * - 5GHz WiFi AP (ch36), DHCP server
 * - BLE throughput test: GATT notify service, measures device→phone throughput
 * - WiFi iperf: zperf UDP upload to PC connected to AP
 * - Coexistence PTA configuration (NRF70_SR_COEX)
 *
 * Shell commands:
 *   wifi_ap start/stop/status
 *   ble start/stop/status
 *   iperf [server_ip] [duration_sec] [rate_kbps]
 *
 * BLE throughput test:
 *   1. Connect phone to "ClipCoex" BLE device
 *   2. Enable notifications on the throughput characteristic
 *   3. Device streams data, prints kbps every second
 *
 * WiFi iperf test:
 *   1. Connect PC to WiFi AP (SSID=ClipAP_XXXX, pass=12345678)
 *   2. Run on PC: iperf -s -i 1 -u
 *   3. Run on device: iperf <PC_IP>
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/shell/shell.h>
#include <zephyr/drivers/hwinfo.h>
#include <nrfx_clock.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* WiFi includes */
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/net/net_event.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/net/dhcpv4_server.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/zperf.h>

/* BLE includes */
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>

#ifdef CONFIG_NRF70_SR_COEX
#include <coex.h>
#endif

LOG_MODULE_REGISTER(wifi_ble_coex, LOG_LEVEL_INF);

/* =========================================================================
 * WiFi AP
 * ========================================================================= */
#define WIFI_AP_SSID_PREFIX "ClipAP_"
#define WIFI_AP_PASSWORD "12345678"
#define WIFI_AP_CHANNEL 36
#define WIFI_AP_REG_DOMAIN "US"
#define DHCPV4_POOL_START "192.168.4.10"

#define IPERF_PORT 5001
#define IPERF_PACKET_SIZE 1400
#define IPERF_DURATION_SEC 10

static bool ap_started;
static char ap_ssid[32] = "ClipAP_Test";
static struct net_mgmt_event_callback wifi_mgmt_cb;

static void generate_ap_ssid(void)
{
    uint8_t chip_id[16];
    ssize_t len = hwinfo_get_device_id(chip_id, sizeof(chip_id));

    if (len > 0)
    {
        uint32_t suffix = 0;
        int off = len > 4 ? len - 4 : 0;

        for (int i = 0; i < 4 && (off + i) < len; i++)
        {
            suffix = (suffix << 8) | chip_id[off + i];
        }
        snprintf(ap_ssid, sizeof(ap_ssid), "%s%04X",
                 WIFI_AP_SSID_PREFIX, (unsigned)(suffix & 0xFFFF));
    }
}

static void wifi_event_handler(struct net_mgmt_event_callback *cb,
                               uint64_t mgmt_event, struct net_if *iface)
{
    switch (mgmt_event)
    {
    case NET_EVENT_WIFI_AP_ENABLE_RESULT:
        LOG_INF("WiFi: AP enable result");
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

    if (!iface)
    {
        return -ENODEV;
    }
    net_addr_pton(AF_INET, DHCPV4_POOL_START, &pool_start.s_addr);
    ret = net_dhcpv4_server_start(iface, &pool_start);
    return (ret == -EALREADY) ? 0 : ret;
}

#ifdef CONFIG_NRF70_SR_COEX
static void wifi_coex_configure(void)
{
    bool sep = IS_ENABLED(CONFIG_COEX_SEP_ANTENNAS);
    bool ble = IS_ENABLED(CONFIG_SR_PROTOCOL_BLE);
    int ret;

    ret = nrf_wifi_coex_config_non_pta(sep, ble);
    if (ret)
    {
        LOG_WRN("Coex non-PTA config failed: %d", ret);
    }
    ret = nrf_wifi_coex_config_pta(NRF_WIFI_PTA_WLAN_OP_BAND_5_GHZ, sep, ble);
    if (ret)
    {
        LOG_WRN("Coex PTA config failed: %d", ret);
    }
    LOG_INF("Coex PTA configured (5GHz, sep=%d, ble=%d)", sep, ble);
}
#endif

static int do_wifi_ap_start(void)
{
    struct net_if *iface = net_if_get_default();
    struct wifi_connect_req_params req;
    struct wifi_reg_domain regd = {0};
    int ret;

    if (!iface)
    {
        return -ENODEV;
    }
    if (ap_started)
    {
        return 0;
    }

    net_if_up(iface);

    k_sleep(K_SECONDS(2));

    regd.oper = WIFI_MGMT_SET;
    strncpy(regd.country_code, WIFI_AP_REG_DOMAIN, WIFI_COUNTRY_CODE_LEN + 1);
    ret = net_mgmt(NET_REQUEST_WIFI_REG_DOMAIN, iface, &regd, sizeof(regd));
    if (ret)
    {
        LOG_WRN("reg domain failed: %d", ret);
    }

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
    if (ret)
    {
        LOG_ERR("AP enable failed: %d", ret);
        return ret;
    }

    k_sleep(K_SECONDS(2));

    ret = configure_dhcp_server();
    if (ret)
    {
        LOG_WRN("DHCP server start failed: %d", ret);
    }

    ap_started = true;
    LOG_INF("WiFi AP started: SSID=%s ch=%d IP=192.168.4.1", ap_ssid, WIFI_AP_CHANNEL);

#ifdef CONFIG_NRF70_SR_COEX
    wifi_coex_configure();
#endif
    return 0;
}

static int do_wifi_ap_stop(void)
{
    struct net_if *iface = net_if_get_default();

    if (!iface || !ap_started)
    {
        return 0;
    }
    net_dhcpv4_server_stop(iface);
    net_mgmt(NET_REQUEST_WIFI_AP_DISABLE, iface, NULL, 0);
    ap_started = false;
    net_if_down(iface);
    LOG_INF("WiFi AP stopped");
    return 0;
}

/* =========================================================================
 * WiFi iperf (zperf UDP upload: device → PC)
 * ========================================================================= */
static K_SEM_DEFINE(zperf_done_sem, 0, 1);
static atomic_t zperf_sessions = ATOMIC_INIT(0);
static volatile bool zperf_error;
static char iperf_server_ip[32] = "192.168.4.10";

static void zperf_cb(enum zperf_status status,
                     struct zperf_results *result,
                     void *user_data)
{
    const struct shell *sh = (const struct shell *)user_data;

    switch (status)
    {
    case ZPERF_SESSION_STARTED:
        atomic_inc(&zperf_sessions);
        break;
    case ZPERF_SESSION_FINISHED:
        if (result && !zperf_error)
        {
            uint64_t bytes = (uint64_t)result->nb_packets_sent * result->packet_size;
            uint64_t time_ms = result->client_time_in_us / 1000;
            uint32_t kbps = 0;

            if (result->client_time_in_us > 0)
            {
                kbps = (uint32_t)(((uint64_t)result->nb_packets_sent *
                                   result->packet_size * 8ULL * 1000000ULL) /
                                  (result->client_time_in_us * 1024ULL));
            }
            shell_print(sh, "[WiFi iperf] pkts=%u lost=%u bytes=%llu time=%llums",
                        result->nb_packets_sent, result->nb_packets_lost,
                        bytes, time_ms);
            shell_print(sh, "[WiFi iperf] Throughput: %u kbps (%u.%03u Mbps)",
                        kbps, kbps / 1000, kbps % 1000);
        }
        if (atomic_dec(&zperf_sessions) <= 1)
        {
            k_sem_give(&zperf_done_sem);
        }
        break;
    case ZPERF_SESSION_ERROR:
        zperf_error = true;
        if (atomic_dec(&zperf_sessions) <= 1)
        {
            shell_print(sh, "[WiFi iperf] Test failed");
            k_sem_give(&zperf_done_sem);
        }
        break;
    default:
        break;
    }
}

/* =========================================================================
 * BLE throughput GATT service (from tests/clip/src/ble.c)
 * ========================================================================= */
#define MTU_SIZE 247
#define NOTIFY_DATA_SIZE (MTU_SIZE - 3)

static const struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(
    BT_UUID_128_ENCODE(0x1234, 0x5678, 0x1234, 0x5678, 0x123456789abc));
static const struct bt_uuid_128 data_uuid = BT_UUID_INIT_128(
    BT_UUID_128_ENCODE(0x1234, 0x5678, 0x1234, 0x5678, 0x123456789abd));

static struct bt_conn *ble_conn;
static volatile bool ble_notify_enabled;
static volatile bool ble_mtu_exchanged;
static uint8_t notify_buf[NOTIFY_DATA_SIZE];
static uint64_t ble_test_start;
static uint64_t ble_bytes_sent;
static uint32_t ble_pkt_count;
static uint64_t ble_stats_time;
static uint64_t ble_stats_bytes;
static bool ble_advertising;

static struct k_thread ble_notify_thr;
static K_THREAD_STACK_DEFINE(ble_notify_stack, 2048);
static struct k_work ble_adv_work;

static void ble_adv_restart_fn(struct k_work *w)
{
    const struct bt_data ad[] = {
        BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
        BT_DATA(BT_DATA_NAME_COMPLETE,
                CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
    };

    bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), NULL, 0);
}

static void notify_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    bool notify = (value == BT_GATT_CCC_NOTIFY);

    if (notify == ble_notify_enabled)
    {
        return;
    }
    if (notify)
    {
        ble_notify_enabled = true;
        if (ble_mtu_exchanged)
        {
            ble_test_start = k_uptime_get();
            ble_bytes_sent = 0;
            ble_pkt_count = 0;
            ble_stats_time = ble_test_start;
            ble_stats_bytes = 0;
            k_wakeup(&ble_notify_thr);
        }
    }
    else
    {
        uint64_t elapsed = k_uptime_get() - ble_test_start;
        uint32_t kbps = elapsed > 0 ? (uint32_t)((ble_bytes_sent * 8) / elapsed) : 0;

        ble_notify_enabled = false;
        printk("\n=== BLE Throughput Results ===\n");
        printk("Packets: %u\n", ble_pkt_count);
        printk("Bytes:   %llu\n", ble_bytes_sent);
        printk("Time:    %llu ms\n", elapsed);
        printk("Speed:   %u kbps (%u.%03u Mbps)\n",
               kbps, kbps / 1000, kbps % 1000);
        printk("==============================\n");
    }
}

static ssize_t read_notify_data(struct bt_conn *conn,
                                const struct bt_gatt_attr *attr,
                                void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset,
                             notify_buf, sizeof(notify_buf));
}

BT_GATT_SERVICE_DEFINE(throughput_svc,
                       BT_GATT_PRIMARY_SERVICE(&svc_uuid),
                       BT_GATT_CHARACTERISTIC(&data_uuid.uuid,
                                              BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                                              BT_GATT_PERM_READ,
                                              read_notify_data, NULL, NULL),
                       BT_GATT_CCC(notify_ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE), );

static void ble_notify_thread_fn(void *p1, void *p2, void *p3)
{
    while (1)
    {
        if (ble_notify_enabled && ble_conn && ble_mtu_exchanged)
        {
            int err = bt_gatt_notify(ble_conn, &throughput_svc.attrs[2],
                                     notify_buf, sizeof(notify_buf));

            if (err == 0)
            {
                ble_bytes_sent += sizeof(notify_buf);
                ble_pkt_count++;
            }
            else if (err == -ENOMEM || err == -EAGAIN)
            {
                k_sleep(K_MSEC(1));
                continue;
            }
            else if (err == -ENOTCONN)
            {
                ble_notify_enabled = false;
                continue;
            }

            uint64_t now = k_uptime_get();

            if (now - ble_stats_time >= 1000)
            {
                uint64_t delta = ble_bytes_sent - ble_stats_bytes;
                uint32_t rate = (delta * 8) / 1000;

                printk("[BLE] %u kbps (%u.%03u Mbps), total=%llu B\n",
                       rate, rate / 1000, rate % 1000, ble_bytes_sent);
                ble_stats_time = now;
                ble_stats_bytes = ble_bytes_sent;
            }
        }
        else
        {
            k_sleep(K_MSEC(10));
        }
    }
}

static void ble_mtu_cb(struct bt_conn *conn, uint8_t err,
                       struct bt_gatt_exchange_params *params)
{
    if (!err)
    {
        ble_mtu_exchanged = true;
        if (ble_notify_enabled)
        {
            ble_test_start = k_uptime_get();
            ble_bytes_sent = 0;
            ble_pkt_count = 0;
            k_wakeup(&ble_notify_thr);
        }
    }
}

static struct bt_gatt_exchange_params mtu_params = {.func = ble_mtu_cb};

static void ble_connected(struct bt_conn *conn, uint8_t err)
{
    if (err)
    {
        LOG_ERR("BLE connect failed: 0x%02x", err);
        return;
    }
    ble_conn = bt_conn_ref(conn);
    ble_mtu_exchanged = false;
    bt_gatt_exchange_mtu(conn, &mtu_params);
    printk("[BLE] Connected - enable notify to start throughput test\n");
}

static void ble_disconnected(struct bt_conn *conn, uint8_t reason)
{
    printk("[BLE] Disconnected (0x%02x)\n", reason);
    if (ble_conn)
    {
        bt_conn_unref(ble_conn);
        ble_conn = NULL;
    }
    ble_notify_enabled = false;
    if (ble_advertising)
    {
        k_work_submit(&ble_adv_work);
    }
}

static void ble_param_updated(struct bt_conn *conn, uint16_t interval,
                              uint16_t latency, uint16_t timeout)
{
    ble_mtu_exchanged = true;
    if (ble_notify_enabled && ble_test_start == 0)
    {
        ble_test_start = k_uptime_get();
        ble_bytes_sent = 0;
        ble_pkt_count = 0;
        k_wakeup(&ble_notify_thr);
    }
}

static struct bt_conn_cb ble_conn_cb = {
    .connected = ble_connected,
    .disconnected = ble_disconnected,
    .le_param_updated = ble_param_updated,
};

static int do_ble_start(void)
{
    const struct bt_data ad[] = {
        BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
        BT_DATA(BT_DATA_NAME_COMPLETE,
                CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
    };
    int ret;

    if (ble_advertising)
    {
        return 0;
    }
    ret = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), NULL, 0);
    if (ret)
    {
        LOG_ERR("BLE adv start failed: %d", ret);
        return ret;
    }
    ble_advertising = true;
    LOG_INF("BLE advertising: %s", CONFIG_BT_DEVICE_NAME);
    return 0;
}

static int do_ble_stop(void)
{
    if (!ble_advertising)
    {
        return 0;
    }
    bt_le_adv_stop();
    ble_advertising = false;
    return 0;
}

/* =========================================================================
 * Shell commands
 * ========================================================================= */
static int cmd_wifi_start(const struct shell *sh, size_t argc, char **argv)
{
    int ret = do_wifi_ap_start();

    if (ret)
    {
        shell_error(sh, "WiFi AP start failed: %d", ret);
    }
    else
    {
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
    struct net_if *iface = net_if_get_default();
    struct wifi_iface_status status;

    if (!iface || net_mgmt(NET_REQUEST_WIFI_IFACE_STATUS, iface, &status, sizeof(status)))
    {
        shell_error(sh, "Failed to get status");
        return -EIO;
    }
    shell_print(sh, "Mode=%s state=%s SSID=%s ch=%d started=%s",
                status.iface_mode == WIFI_MODE_AP ? "AP" : "other",
                status.state == WIFI_STATE_COMPLETED ? "RUNNING" : "idle",
                status.ssid, status.channel,
                ap_started ? "yes" : "no");
    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(wifi_ap_cmds,
                               SHELL_CMD(start, NULL, "Start WiFi AP (5GHz ch36)", cmd_wifi_start),
                               SHELL_CMD(stop, NULL, "Stop WiFi AP", cmd_wifi_stop),
                               SHELL_CMD(status, NULL, "Show WiFi AP status", cmd_wifi_status),
                               SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(wifi_ap, &wifi_ap_cmds, "WiFi AP commands", NULL);

/* iperf [server_ip] [duration_sec] [rate_kbps] */
static int cmd_iperf(const struct shell *sh, size_t argc, char **argv)
{
    struct sockaddr_in addr;
    struct zperf_upload_params params;
    int duration = IPERF_DURATION_SEC;
    uint32_t rate_kbps = 100000;
    int ret;

    if (!ap_started)
    {
        shell_error(sh, "WiFi AP not started. Use: wifi_ap start");
        return -ENETDOWN;
    }
    if (argc >= 2)
    {
        strncpy(iperf_server_ip, argv[1], sizeof(iperf_server_ip) - 1);
    }
    if (argc >= 3)
    {
        duration = atoi(argv[2]);
    }
    if (argc >= 4)
    {
        rate_kbps = (uint32_t)atoi(argv[3]);
    }

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(IPERF_PORT);
    if (inet_pton(AF_INET, iperf_server_ip, &addr.sin_addr) != 1)
    {
        shell_error(sh, "Invalid IP: %s", iperf_server_ip);
        return -EINVAL;
    }

    memset(&params, 0, sizeof(params));
    params.duration_ms = (uint32_t)duration * 1000;
    params.packet_size = IPERF_PACKET_SIZE;
    params.rate_kbps = rate_kbps;
    memcpy(&params.peer_addr, &addr, sizeof(addr));

    shell_print(sh, "[WiFi iperf] → %s:%d  %ds  %ukbps", iperf_server_ip, IPERF_PORT,
                duration, rate_kbps);
    shell_print(sh, "Run on PC first: iperf -s -i 1 -u");

    zperf_error = false;
    atomic_set(&zperf_sessions, 0);
    k_sem_reset(&zperf_done_sem);

    ret = zperf_udp_upload_async(&params, zperf_cb, (void *)sh);
    if (ret)
    {
        shell_error(sh, "zperf start failed: %d", ret);
        return ret;
    }

    return k_sem_take(&zperf_done_sem, K_SECONDS(duration + 30));
}

SHELL_CMD_REGISTER(iperf, NULL,
                   "WiFi UDP iperf test [server_ip] [duration_sec] [rate_kbps]", cmd_iperf);

static int cmd_ble_start(const struct shell *sh, size_t argc, char **argv)
{
    int ret = do_ble_start();

    if (ret)
    {
        shell_error(sh, "BLE start failed: %d", ret);
    }
    else
    {
        shell_print(sh, "Advertising \"%s\" - connect phone, enable notify",
                    CONFIG_BT_DEVICE_NAME);
    }
    return ret;
}

static int cmd_ble_stop(const struct shell *sh, size_t argc, char **argv)
{
    do_ble_stop();
    shell_print(sh, "BLE stopped");
    return 0;
}

static int cmd_ble_status(const struct shell *sh, size_t argc, char **argv)
{
    uint64_t elapsed = ble_test_start > 0 ? k_uptime_get() - ble_test_start : 0;
    uint32_t kbps = elapsed > 0 ? (uint32_t)((ble_bytes_sent * 8) / elapsed) : 0;

    shell_print(sh, "advertising=%s connected=%s notify=%s",
                ble_advertising ? "yes" : "no",
                ble_conn ? "yes" : "no",
                ble_notify_enabled ? "yes" : "no");
    if (ble_bytes_sent > 0)
    {
        shell_print(sh, "bytes=%llu  speed=%u kbps (%u.%03u Mbps)",
                    ble_bytes_sent, kbps, kbps / 1000, kbps % 1000);
    }
    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(ble_cmds,
                               SHELL_CMD(start, NULL, "Start BLE (GATT throughput service)", cmd_ble_start),
                               SHELL_CMD(stop, NULL, "Stop BLE advertising", cmd_ble_stop),
                               SHELL_CMD(status, NULL, "Show BLE status and throughput", cmd_ble_status),
                               SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(ble, &ble_cmds, "BLE commands", NULL);

/* =========================================================================
 * Main
 * ========================================================================= */
int main(void)
{
    int ret;

// #ifdef CLOCK_FEATURE_HFCLK_DIVIDE_PRESENT
//     nrfx_clock_divider_set(NRF_CLOCK_DOMAIN_HFCLK, NRF_CLOCK_HFCLK_DIV_1);
// #endif

    generate_ap_ssid();

    for (size_t i = 0; i < sizeof(notify_buf); i++)
    {
        notify_buf[i] = i & 0xFF;
    }

    net_mgmt_init_event_callback(&wifi_mgmt_cb, wifi_event_handler,
                                 NET_EVENT_WIFI_AP_ENABLE_RESULT |
                                     NET_EVENT_WIFI_AP_STA_CONNECTED |
                                     NET_EVENT_WIFI_AP_STA_DISCONNECTED);
    net_mgmt_add_event_callback(&wifi_mgmt_cb);

    k_work_init(&ble_adv_work, ble_adv_restart_fn);
    bt_conn_cb_register(&ble_conn_cb);
    ret = bt_enable(NULL);
    if (ret)
    {
        LOG_ERR("bt_enable failed: %d", ret);
    }

    k_thread_create(&ble_notify_thr, ble_notify_stack,
                    K_THREAD_STACK_SIZEOF(ble_notify_stack),
                    ble_notify_thread_fn, NULL, NULL, NULL,
                    K_PRIO_COOP(-1), 0, K_NO_WAIT);

    printk("\n================================================\n");
    printk("  reSpeaker Clip: WiFi AP + BLE Coex Test\n");
    printk("================================================\n\n");

    /* BLE starts first so phone can connect immediately */
    ret = do_ble_start();
    if (ret)
    {
        printk("BLE start failed: %d - use: ble start\n", ret);
    }
    else
    {
        printk("[BLE] Advertising \"%s\"\n", CONFIG_BT_DEVICE_NAME);
        printk("[BLE] Connect phone, enable notify → throughput test starts\n\n");
    }

    /* WiFi AP starts after BLE is up */
    k_sleep(K_SECONDS(2));

    // ret = do_wifi_ap_start();
    // if (ret)
    // {
    //     printk("WiFi AP start failed: %d - use: wifi_ap start\n", ret);
    // }
    // else
    // {
    //     printk("[WiFi] SSID=%s pass=%s IP=192.168.4.1\n", ap_ssid, WIFI_AP_PASSWORD);
    //     printk("[WiFi] Connect PC to AP, then: iperf <PC_IP>\n");
    //     printk("[WiFi] PC side: iperf -s -i 1 -u\n\n");
    // }

    printk("Shell: wifi_ap start/stop/status | ble start/stop/status | iperf [ip]\n\n");

    return 0;
}
