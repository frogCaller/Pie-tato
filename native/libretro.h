/* The part of the libretro API (libretro.h, MIT licence: https://github.com/libretro/libretro-common) that rcheevos's
 * rc_libretro.c reads a core's memory with: the memory kinds, and a core's map of its memory. setup.sh builds
 * librcheevos.so with it (the whole header isn't needed for that). */
#ifndef LIBRETRO_H__
#define LIBRETRO_H__

#include <stdint.h>
#include <stddef.h>

#define RETRO_MEMORY_SAVE_RAM    0
#define RETRO_MEMORY_RTC         1
#define RETRO_MEMORY_SYSTEM_RAM  2
#define RETRO_MEMORY_VIDEO_RAM   3

#define RETRO_MEMDESC_CONST      (1 << 0)
#define RETRO_MEMDESC_BIGENDIAN  (1 << 1)
#define RETRO_MEMDESC_SYSTEM_RAM (1 << 2)
#define RETRO_MEMDESC_SAVE_RAM   (1 << 3)
#define RETRO_MEMDESC_VIDEO_RAM  (1 << 4)
#define RETRO_MEMDESC_ALIGN_2    (1 << 16)
#define RETRO_MEMDESC_ALIGN_4    (2 << 16)
#define RETRO_MEMDESC_ALIGN_8    (3 << 16)
#define RETRO_MEMDESC_MINSIZE_2  (1 << 24)
#define RETRO_MEMDESC_MINSIZE_4  (2 << 24)
#define RETRO_MEMDESC_MINSIZE_8  (3 << 24)

struct retro_memory_descriptor
{
   uint64_t flags;
   void *ptr;
   size_t offset;
   size_t start;
   size_t select;
   size_t disconnect;
   size_t len;
   const char *addrspace;
};

struct retro_memory_map
{
   const struct retro_memory_descriptor *descriptors;
   unsigned num_descriptors;
};

#endif
