# SPDX-License-Identifier: Apache-2.0
#
# reSpeaker Clip 1200-baud USB CDC -> mcuboot DFU trigger.

zephyr_library_named(clip_usb_dfu)

# Shared hook (always, when CLIP_USB_DFU=y): 1200-baud -> bootmode_set ->
# deferred reboot. Used by apps with their own CDC and by the default CDC below.
zephyr_library_sources(clip_usb_dfu.c)

# Optional default CDC ACM (auto-init + enable via SYS_INIT) for apps without
# their own USB stack (samples).
zephyr_library_sources_ifdef(CONFIG_CLIP_USB_DFU_DEFAULT_CDC
	clip_usb_cdc_default.c
)

# Expose clip_usb_dfu.h to this library and to the application.
zephyr_library_include_directories(.)
zephyr_include_directories(.)
