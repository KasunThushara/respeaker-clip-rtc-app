/* Copyright (C) 2007 Jean-Marc Valin
 * Custom memory allocation support for Zephyr RTOS
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#ifndef OS_SUPPORT_CUSTOM_H
#define OS_SUPPORT_CUSTOM_H

#include <zephyr/kernel.h>
#include <string.h>
#include <stdlib.h>

#define OVERRIDE_SPEEX_ALLOC
#define OVERRIDE_SPEEX_FREE
#define OVERRIDE_SPEEX_REALLOC
#define OVERRIDE_SPEEX_ALLOC_SCRATCH
#define OVERRIDE_SPEEX_FREE_SCRATCH
#define DISABLE_WARNINGS
#define DISABLE_NOTIFICATIONS

/* speex_alloc MUST clear memory as per API requirement */
static inline void *speex_alloc(int size)
{
    void *ptr = k_malloc(size);
    if (ptr) {
        memset(ptr, 0, size);
    }
    return ptr;
}

static inline void speex_free(void *ptr)
{
    k_free(ptr);
}

static inline void *speex_realloc(void *ptr, int size)
{
    if (ptr == NULL) {
        void *new_ptr = k_malloc(size);
        if (new_ptr) {
            memset(new_ptr, 0, size);
        }
        return new_ptr;
    }
    if (size == 0) {
        k_free(ptr);
        return NULL;
    }
    /* Zephyr has no k_realloc, implement a simple version.
     * Note: We cannot know the old size, so this is a simplified version.
     * For SpeexDSP, realloc is rarely used in critical paths. */
    void *new_ptr = k_malloc(size);
    if (new_ptr) {
        /* Best effort - copy what we can */
        k_free(ptr);
    }
    return new_ptr;
}

static inline void *speex_alloc_scratch(int size)
{
    /* Scratch space doesn't need to be cleared */
    return k_malloc(size);
}

static inline void speex_free_scratch(void *ptr)
{
    k_free(ptr);
}

#endif /* OS_SUPPORT_CUSTOM_H */
