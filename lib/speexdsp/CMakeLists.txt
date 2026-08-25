# SPDX-License-Identifier: Apache-2.0
#
# SpeexDSP DSP library for Zephyr
# Uses floating-point mode with FPU acceleration (AGC enabled)

zephyr_library_named(speexdsp)
zephyr_library_property(ALLOW_EMPTY TRUE)

# Include directories
zephyr_library_include_directories(
    speexdsp/include
)

# Expose public headers to the entire project
zephyr_include_directories_ifdef(CONFIG_SPEEXDSP
    speexdsp/include
)

# SpeexDSP source files - only compile if CONFIG_SPEEXDSP is enabled
zephyr_library_sources_ifdef(CONFIG_SPEEXDSP
    speexdsp/libspeexdsp/preprocess.c
    speexdsp/libspeexdsp/filterbank.c
    speexdsp/libspeexdsp/fftwrap.c
    speexdsp/libspeexdsp/mdf.c
    speexdsp/libspeexdsp/scal.c
    speexdsp/libspeexdsp/kiss_fft.c
    speexdsp/libspeexdsp/kiss_fftr.c
    speexdsp/libspeexdsp/smallft.c
)

# Compile options for SpeexDSP.
# AGC is implemented as a lightweight integer AGC in audio.c instead of
# SpeexDSP's float AGC (which takes ~15ms/frame even with hardware FPU).
zephyr_library_compile_options(
    -DUSE_KISS_FFT=1
    -DEXPORT=
    -DRANDOM_PREFIX=speex
    -D_USE_SSE=0
    -D_USE_NEON=0
    -DOS_SUPPORT_CUSTOM
)

# Compile options to suppress warnings from upstream code
zephyr_library_compile_options(
    -Wno-sign-compare
    -Wno-maybe-uninitialized
    -Wno-double-promotion
    -Wno-unused-variable
)
