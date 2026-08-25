#
# Copyright (c) 2024 Seeed Studio
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nrf_wifi_radio_test)

set(RT_SRC ${ZEPHYR_NRF_MODULE_DIR}/samples/wifi/radio_test/multi_domain)
set(NRF_WIFI_DIR ${ZEPHYR_NRF_WIFI_MODULE_DIR})

target_include_directories(app PRIVATE
  ${RT_SRC}/inc
  ${NRF_WIFI_DIR}/hw_if/hal/inc
  ${NRF_WIFI_DIR}/fw_if/umac_if/inc
  ${NRF_WIFI_DIR}/fw_if/umac_if/inc/fw
  ${NRF_WIFI_DIR}/fw_if/umac_if/inc/fw/stats
  ${NRF_WIFI_DIR}/fw_if/umac_if/inc/fw/stats/radio_test
  ${NRF_WIFI_DIR}/utils/inc
  ${NRF_WIFI_DIR}/os_if/inc
  ${NRF_WIFI_DIR}/bus_if/bus/qspi/inc
  ${NRF_WIFI_DIR}/bus_if/bal/inc
  ${ZEPHYR_BASE}/drivers/wifi/nrf_wifi/inc
  ${ZEPHYR_BASE}/subsys/net/ip
)

target_sources(app PRIVATE
  ${RT_SRC}/src/nrf_wifi_radio_test_main.c
  ${RT_SRC}/src/nrf_wifi_radio_test_shell.c
  ${RT_SRC}/src/nrf_wifi_radio_ficr_shell.c
  ${RT_SRC}/src/ficr_prog.c
)

target_link_libraries(app PRIVATE nrf-wifi-osal)
