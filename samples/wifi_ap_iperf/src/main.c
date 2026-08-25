/*
 * Copyright (c) 2025 Seeed Technology Co., Ltd.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * WiFi AP + iperf Throughput Test Sample for reSpeaker Clip
 *
 * WiFi-only sample (no BLE). Device acts as a WiFi AP hotspot with
 * configurable channel (2.4G/5G) and zperf UDP throughput testing.
 *
 * Shell commands:
 *   wifi on [channel]  - Start AP (default ch36, 2.4G:1-13, 5G:36-165)
 *   wifi off           - Stop AP
 *   wifi scan [band]   - Scan networks (0=all, 1=2.4G, 2=5G)
 *   wifi status        - Show AP state
 *   iperf [ip] [dur] [rate] - UDP throughput test
 */

#include <zephyr/kernel.h>
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/net/net_event.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/dhcpv4_server.h>
#include <zephyr/net/zperf.h>
#include <zephyr/logging/log.h>
#include <zephyr/shell/shell.h>
#include <zephyr/drivers/hwinfo.h>
#include <nrfx_clock.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

LOG_MODULE_REGISTER(wifi_ap_iperf, LOG_LEVEL_INF);

#define WIFI_AP_SSID_PREFIX "ClipTest_"
#define WIFI_AP_PASSWORD "12345678"
#define WIFI_AP_CHANNEL_DEFAULT 36
#define WIFI_AP_REG_DOMAIN "US"
#define WIFI_AP_ENABLE_RETRIES 2

#define IPERF_PORT 5001
#define IPERF_PACKET_SIZE 1400
#define IPERF_DURATION_SEC 10

#define DEFAULT_AP_SSID "ClipTest_Test"

static uint8_t ap_channel = WIFI_AP_CHANNEL_DEFAULT;
static bool ap_started;
static char ap_ssid[32] = "ClipTest_XXXX";
static char iperf_server_ip[32] = "192.168.4.2";

static struct net_mgmt_event_callback wifi_mgmt_cb;
static K_SEM_DEFINE(ap_enabled_sem, 0, 1);

/* Scan state */
static K_SEM_DEFINE(scan_done_sem, 0, 1);
static struct wifi_scan_result scan_results[10];
static int scan_result_count;

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
	} else {
		strncpy(ap_ssid, DEFAULT_AP_SSID, sizeof(ap_ssid) - 1);
	}
}

static void wifi_mgmt_event_handler(struct net_mgmt_event_callback *cb,
				    uint64_t mgmt_event, struct net_if *iface)
{
	switch (mgmt_event) {
	case NET_EVENT_WIFI_AP_ENABLE_RESULT:
	{
		const struct wifi_status *status =
			(const struct wifi_status *)cb->info;
		if (status && status->status == 0) {
			printk("[WiFi] AP enabled\n");
			ap_started = true;
		} else {
			printk("[WiFi] AP enable failed: %d\n",
			       status ? status->status : -999);
		}
		k_sem_give(&ap_enabled_sem);
		break;
	}
	case NET_EVENT_WIFI_AP_DISABLE_RESULT:
		printk("[WiFi] AP disabled\n");
		ap_started = false;
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

static void scan_result_callback(struct net_mgmt_event_callback *cb,
				 uint64_t mgmt_event, struct net_if *iface)
{
	if (mgmt_event == NET_EVENT_WIFI_SCAN_RESULT) {
		struct wifi_scan_result *result =
			(struct wifi_scan_result *)cb->info;

		if (scan_result_count < 10 && result) {
			memcpy(&scan_results[scan_result_count], result,
			       sizeof(struct wifi_scan_result));
			scan_result_count++;
			printk("Found: %s, RSSI: %d\n", result->ssid, result->rssi);
		}
	} else if (mgmt_event == NET_EVENT_WIFI_SCAN_DONE) {
		printk("Scan done, found %d networks\n", scan_result_count);
		k_sem_give(&scan_done_sem);
	}
}

static int wifi_set_reg_domain(struct net_if *iface)
{
	struct wifi_reg_domain regd = {0};
	int ret;

	regd.oper = WIFI_MGMT_SET;
	strncpy(regd.country_code, WIFI_AP_REG_DOMAIN, WIFI_COUNTRY_CODE_LEN + 1);

	ret = net_mgmt(NET_REQUEST_WIFI_REG_DOMAIN, iface, &regd, sizeof(regd));
	if (ret) {
		LOG_WRN("Reg domain failed: %d", ret);
	}

	return ret;
}

static int wifi_enable_ap(struct net_if *iface)
{
	struct wifi_connect_req_params req;
	int ret;

	memset(&req, 0, sizeof(req));
	req.ssid = (const uint8_t *)ap_ssid;
	req.ssid_length = strlen(ap_ssid);
	req.psk = (const uint8_t *)WIFI_AP_PASSWORD;
	req.psk_length = strlen(WIFI_AP_PASSWORD);
	req.channel = ap_channel;
	req.security = WIFI_SECURITY_TYPE_PSK;
	req.mfp = WIFI_MFP_OPTIONAL;
	req.band = (ap_channel <= 13) ? WIFI_FREQ_BAND_2_4_GHZ : WIFI_FREQ_BAND_5_GHZ;

	for (int attempt = 0; attempt <= WIFI_AP_ENABLE_RETRIES; attempt++) {
		k_sem_reset(&ap_enabled_sem);

		ret = net_mgmt(NET_REQUEST_WIFI_AP_ENABLE, iface, &req, sizeof(req));
		if (ret) {
			LOG_ERR("AP enable request failed: %d (attempt %d)", ret, attempt);
			continue;
		}

		ret = k_sem_take(&ap_enabled_sem, K_SECONDS(5));
		if (ret) {
			LOG_WRN("AP enable timeout (attempt %d)", attempt);
			continue;
		}

		if (!ap_started) {
			LOG_ERR("AP enable rejected (attempt %d)", attempt);
			continue;
		}

		return 0;
	}

	return -EIO;
}

static int do_wifi_ap_start(void)
{
	struct net_if *iface;
	int ret;

	if (ap_started) {
		printk("AP already running: %s\n", ap_ssid);
		return 0;
	}

	iface = net_if_get_first_wifi();
	if (!iface) {
		printk("[WiFi] No WiFi interface\n");
		return -ENODEV;
	}

	wifi_set_reg_domain(iface);

	ret = wifi_enable_ap(iface);
	if (ret) {
		ap_started = false;
		return ret;
	}

	/* Configure static IP + DHCP server */
	{
		struct in_addr addr, netmask, gw, pool_start;
		struct net_if_addr *ifaddr;

		net_addr_pton(AF_INET, CONFIG_NET_CONFIG_MY_IPV4_ADDR, &addr);
		net_addr_pton(AF_INET, CONFIG_NET_CONFIG_MY_IPV4_NETMASK, &netmask);
		net_addr_pton(AF_INET, CONFIG_NET_CONFIG_MY_IPV4_GW, &gw);
		ifaddr = net_if_ipv4_addr_add(iface, &addr, NET_ADDR_MANUAL, 0);
		if (!ifaddr && !net_if_ipv4_addr_lookup(&addr, &iface)) {
			LOG_WRN("Failed to set IP address");
		}
		net_if_ipv4_set_netmask_by_addr(iface, &addr, &netmask);
		net_if_ipv4_set_gw(iface, &gw);

		pool_start.s_addr = htonl(ntohl(addr.s_addr) + 1);
		ret = net_dhcpv4_server_start(iface, &pool_start);
		if (ret && ret != -EALREADY) {
			LOG_WRN("DHCP server start failed: %d", ret);
		} else {
			printk("[WiFi] DHCP server started\n");
		}
	}

	printk("[WiFi] AP started: SSID=%s ch=%d (%s) IP=%s\n",
	       ap_ssid, ap_channel,
	       ap_channel <= 13 ? "2.4GHz" : "5GHz",
	       CONFIG_NET_CONFIG_MY_IPV4_ADDR);
	printk("[WiFi] Password: %s\n", WIFI_AP_PASSWORD);
	return 0;
}

static int do_wifi_ap_stop(void)
{
	struct net_if *iface = net_if_get_first_wifi();

	if (!iface || !ap_started) {
		printk("AP not running\n");
		return 0;
	}

	net_dhcpv4_server_stop(iface);
	net_mgmt(NET_REQUEST_WIFI_AP_DISABLE, iface, NULL, 0);
	ap_started = false;
	printk("[WiFi] AP stopped\n");
	return 0;
}

/* Shell commands */

static int cmd_wifi_on(const struct shell *sh, size_t argc, char **argv)
{
	if (argc >= 2) {
		int ch = atoi(argv[1]);
		if (ch < 1 || (ch > 13 && ch < 36) || ch > 165) {
			shell_print(sh, "Invalid channel (2.4G: 1-13, 5G: 36-165)");
			return -EINVAL;
		}
		ap_channel = (uint8_t)ch;
	}
	return do_wifi_ap_start();
}

static int cmd_wifi_off(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	return do_wifi_ap_stop();
}

static int cmd_wifi_status(const struct shell *sh, size_t argc, char **argv)
{
	shell_print(sh, "WiFi AP Status:");

	if (ap_started) {
		shell_print(sh, "  SSID: %s", ap_ssid);
		shell_print(sh, "  Password: %s", WIFI_AP_PASSWORD);
		shell_print(sh, "  Channel: %d (%s)", ap_channel,
			    ap_channel <= 13 ? "2.4GHz" : "5GHz");
		shell_print(sh, "  IP: %s", CONFIG_NET_CONFIG_MY_IPV4_ADDR);
	} else {
		shell_print(sh, "  State: Stopped");
		shell_print(sh, "  Use 'wifi on [channel]' to start AP");
	}

	return 0;
}

static int cmd_wifi_scan(const struct shell *sh, size_t argc, char **argv)
{
	struct net_if *iface = net_if_get_first_wifi();
	static struct net_mgmt_event_callback scan_cb;
	int ret, band = 0;

	if (!iface) {
		shell_error(sh, "No WiFi interface");
		return -ENODEV;
	}

	if (argc >= 2) {
		band = atoi(argv[1]);
		if (band < 0 || band > 2) {
			shell_print(sh, "Invalid band (0=all, 1=2.4G, 2=5G)");
			return -EINVAL;
		}
	}

	scan_result_count = 0;
	memset(scan_results, 0, sizeof(scan_results));
	k_sem_reset(&scan_done_sem);

	net_mgmt_init_event_callback(&scan_cb, scan_result_callback,
				     NET_EVENT_WIFI_SCAN_RESULT |
				     NET_EVENT_WIFI_SCAN_DONE);
	net_mgmt_add_event_callback(&scan_cb);

	struct wifi_scan_params params = {
		.scan_type = WIFI_SCAN_TYPE_ACTIVE,
		.bands = (band == 0) ? ((1 << WIFI_FREQ_BAND_2_4_GHZ) | (1 << WIFI_FREQ_BAND_5_GHZ)) :
			(band == 1) ? (1 << WIFI_FREQ_BAND_2_4_GHZ) : (1 << WIFI_FREQ_BAND_5_GHZ),
		.max_bss_cnt = 10,
	};

	shell_print(sh, "Scanning for networks...");

	ret = net_mgmt(NET_REQUEST_WIFI_SCAN, iface, &params, sizeof(params));
	if (ret) {
		shell_print(sh, "Scan failed: %d", ret);
		net_mgmt_del_event_callback(&scan_cb);
		return ret;
	}

	ret = k_sem_take(&scan_done_sem, K_SECONDS(15));
	if (ret != 0) {
		shell_print(sh, "Scan timeout");
		net_mgmt_del_event_callback(&scan_cb);
		return -ETIMEDOUT;
	}

	net_mgmt_del_event_callback(&scan_cb);

	shell_print(sh, "Found %d networks:", scan_result_count);
	shell_print(sh, "%-4s %-20s %-6s %-4s", "CH", "SSID", "RSSI", "BAND");

	for (int i = 0; i < scan_result_count; i++) {
		struct wifi_scan_result *r = &scan_results[i];
		const char *band_str = (r->band == WIFI_FREQ_BAND_2_4_GHZ) ? "2.4G" : "5G";

		char ssid[21];
		snprintf(ssid, sizeof(ssid), "%.20s", r->ssid);

		shell_print(sh, "%-4d %-20s %-6d %-4s",
			   r->channel, ssid, r->rssi, band_str);
	}

	return 0;
}

/* zperf UDP throughput test */
static K_SEM_DEFINE(zperf_done_sem, 0, 1);
static atomic_t zperf_sessions = ATOMIC_INIT(0);
static volatile bool zperf_error;

static void zperf_cb(enum zperf_status status,
		     struct zperf_results *result,
		     void *user_data)
{
	const struct shell *sh = (const struct shell *)user_data;

	switch (status) {
	case ZPERF_SESSION_STARTED:
		atomic_inc(&zperf_sessions);
		break;
	case ZPERF_SESSION_FINISHED:
		if (result && !zperf_error) {
			uint64_t bytes = (uint64_t)result->nb_packets_sent *
					 result->packet_size;
			uint64_t time_ms = result->client_time_in_us / 1000;
			uint32_t kbps = 0;

			if (result->client_time_in_us > 0) {
				kbps = (uint32_t)(
					((uint64_t)result->nb_packets_sent *
					 result->packet_size * 8ULL * 1000000ULL) /
					(result->client_time_in_us * 1024ULL));
			}
			shell_print(sh, "[iperf] pkts=%u lost=%u bytes=%llu time=%llums",
				    result->nb_packets_sent, result->nb_packets_lost,
				    bytes, time_ms);
			shell_print(sh, "[iperf] Throughput: %u kbps (%u.%03u Mbps)",
				    kbps, kbps / 1000, kbps % 1000);
		}
		if (atomic_dec(&zperf_sessions) <= 1) {
			k_sem_give(&zperf_done_sem);
		}
		break;
	case ZPERF_SESSION_ERROR:
		zperf_error = true;
		if (atomic_dec(&zperf_sessions) <= 1) {
			shell_print(sh, "[iperf] Test failed");
			k_sem_give(&zperf_done_sem);
		}
		break;
	default:
		break;
	}
}

static int cmd_udp_test(const struct shell *sh, size_t argc, char **argv)
{
	struct sockaddr_in addr;
	struct zperf_upload_params params;
	int ret;
	int duration_sec = IPERF_DURATION_SEC;
	uint32_t rate_kbps = 100000;

	if (!ap_started) {
		shell_print(sh, "WiFi AP not started. Use 'wifi on' first.");
		return -ENETDOWN;
	}

	if (argc >= 2) {
		strncpy(iperf_server_ip, argv[1], sizeof(iperf_server_ip) - 1);
	}
	if (argc >= 3) {
		duration_sec = atoi(argv[2]);
		if (duration_sec <= 0 || duration_sec > 3600) {
			shell_print(sh, "Invalid duration (1-3600 seconds)");
			return -EINVAL;
		}
	}
	if (argc >= 4) {
		rate_kbps = atoi(argv[3]);
		if (rate_kbps < 100 || rate_kbps > 1000000) {
			shell_print(sh, "Invalid rate (100-1000000 kbps)");
			return -EINVAL;
		}
	}

	memset(&addr, 0, sizeof(addr));
	addr.sin_family = AF_INET;
	addr.sin_port = htons(IPERF_PORT);
	ret = inet_pton(AF_INET, iperf_server_ip, &addr.sin_addr);
	if (ret != 1) {
		shell_print(sh, "Invalid IP address");
		return -EINVAL;
	}

	memset(&params, 0, sizeof(params));
	params.duration_ms = duration_sec * 1000;
	params.packet_size = IPERF_PACKET_SIZE;
	params.rate_kbps = rate_kbps;
	memcpy(&params.peer_addr, &addr, sizeof(addr));

	shell_print(sh, "UDP throughput test (iperf compatible)");
	shell_print(sh, "Target: %s:%d", iperf_server_ip, IPERF_PORT);
	shell_print(sh, "Duration: %d seconds, Rate: %u kbps", duration_sec, rate_kbps);
	shell_print(sh, "Run on PC: iperf -s -u -p 5001 -i 1");

	zperf_error = false;
	ret = zperf_udp_upload_async(&params, zperf_cb, (void *)sh);
	if (ret) {
		shell_print(sh, "Failed to start test: %d", ret);
		return ret;
	}

	ret = k_sem_take(&zperf_done_sem, K_SECONDS(duration_sec + 30));
	if (ret != 0) {
		shell_print(sh, "Test timeout");
		return -ETIMEDOUT;
	}

	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_wifi,
	SHELL_CMD(on, NULL, "Start WiFi AP [channel] (2.4G:1-13,5G:36-165)", cmd_wifi_on),
	SHELL_CMD(off, NULL, "Stop WiFi AP", cmd_wifi_off),
	SHELL_CMD(scan, NULL, "Scan networks [band: 0=all, 1=2.4G, 2=5G]", cmd_wifi_scan),
	SHELL_CMD(status, NULL, "Show WiFi AP status", cmd_wifi_status),
	SHELL_SUBCMD_SET_END
);

SHELL_CMD_REGISTER(wifi, &sub_wifi, "WiFi AP commands", NULL);

SHELL_CMD_REGISTER(iperf, NULL, "UDP iperf test [server_ip] [duration_sec] [rate_kbps]",
		   cmd_udp_test);

int main(void)
{
#ifdef CLOCK_FEATURE_HFCLK_DIVIDE_PRESENT
	nrfx_clock_divider_set(NRF_CLOCK_DOMAIN_HFCLK, NRF_CLOCK_HFCLK_DIV_1);
#endif

	LOG_INF("WiFi AP + iperf Sample");

	generate_ap_ssid();

	net_mgmt_init_event_callback(&wifi_mgmt_cb, wifi_mgmt_event_handler,
				     NET_EVENT_WIFI_AP_ENABLE_RESULT |
				     NET_EVENT_WIFI_AP_DISABLE_RESULT |
				     NET_EVENT_WIFI_AP_STA_CONNECTED |
				     NET_EVENT_WIFI_AP_STA_DISCONNECTED);
	net_mgmt_add_event_callback(&wifi_mgmt_cb);

	printk("\nWiFi AP + iperf Sample\n");
	printk("SSID: %s  Password: %s\n", ap_ssid, WIFI_AP_PASSWORD);
	printk("Commands: wifi on [ch] | wifi off | wifi scan | wifi status | iperf\n\n");

	return 0;
}
