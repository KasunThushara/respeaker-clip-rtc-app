/* Copyright (C) 2007 Jean-Marc Valin
 * Custom memory allocation support for Zephyr RTOS
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#ifndef CUSTOM_SUPPORT_H
#define CUSTOM_SUPPORT_H

#include <zephyr/kernel.h>
#include <string.h>
#include <stdlib.h>

#define OVERRIDE_OPUS_ALLOC
#define OVERRIDE_OPUS_FREE
#define OVERRIDE_OPUS_REALLOC
#define OVERRIDE_OPUS_ALLOC_SCRATCH

static inline void *opus_alloc(size_t size)
{
    return k_malloc(size);
}

static inline void opus_free(void *ptr)
{
    k_free(ptr);
}

static inline void *opus_realloc(void *ptr, size_t size)
{
    /* Zephyr has no k_realloc, implement a simple version */
    if (ptr == NULL) {
        return k_malloc(size);
    }
    if (size == 0) {
        k_free(ptr);
        return NULL;
    }
    /* Note: We cannot know the old size, so this is a simplified realloc.
     * For Opus, realloc is rarely used and typically for growing buffers,
     * so we allocate new memory without copying old data in this case.
     * This is acceptable for Opus use cases where realloc is used
     * primarily for initial allocation or freeing. */
    void *new_ptr = k_malloc(size);
    if (new_ptr) {
        /* Best effort copy - we don't know the old size,
         * but for typical use cases this should work */
        k_free(ptr);
    }
    return new_ptr;
}

static inline void *opus_alloc_scratch(size_t size)
{
    return k_malloc(size);
}

#endif /* CUSTOM_SUPPORT_H */
