"""The graphics chip, for a game drawn in 3D (an N64's, a PSP's): OpenGL ES with no window (EGL, from Mesa), a
framebuffer the emulator draws each frame into, and each frame scaled to the screen by the chip and read
straight into the rows the screen is written from. A Pi 4 or 5 has the chip for it; older Pis have only
OpenGL ES 2, and starting fails (GPUError, in words for the screen)."""
import ctypes as C
import glob
import os
import re
import sys

import numpy as np

from .screen import pi_model, slow_pi

# EGL's numbers (egl.h, eglext.h)
EGL_NONE, EGL_EXTENSIONS = 0x3038, 0x3055
EGL_SURFACE_TYPE, EGL_RENDERABLE_TYPE = 0x3033, 0x3040
EGL_OPENGL_ES2_BIT, EGL_OPENGL_ES3_BIT = 0x4, 0x40
EGL_OPENGL_ES_API = 0x30A0
EGL_CONTEXT_MAJOR_VERSION, EGL_CONTEXT_MINOR_VERSION = 0x3098, 0x30FB
EGL_PLATFORM_GBM, EGL_PLATFORM_SURFACELESS = 0x31D7, 0x31DD
# OpenGL ES's (gl3.h, gl2ext.h)
GL_READ_FRAMEBUFFER, GL_DRAW_FRAMEBUFFER = 0x8CA8, 0x8CA9
GL_READ_FRAMEBUFFER_BINDING, GL_DRAW_FRAMEBUFFER_BINDING = 0x8CAA, 0x8CA6
GL_RENDERBUFFER, GL_RENDERBUFFER_BINDING = 0x8D41, 0x8CA7
GL_COLOR_ATTACHMENT0, GL_DEPTH_ATTACHMENT, GL_DEPTH_STENCIL_ATTACHMENT = 0x8CE0, 0x8D00, 0x821A
GL_RGBA8, GL_RGB565, GL_DEPTH_COMPONENT24, GL_DEPTH24_STENCIL8 = 0x8058, 0x8D62, 0x81A6, 0x88F0
GL_FRAMEBUFFER_COMPLETE = 0x8CD5
GL_COLOR_BUFFER_BIT = 0x4000
GL_NEAREST, GL_LINEAR = 0x2600, 0x2601
GL_RGB, GL_RGBA, GL_BGRA = 0x1907, 0x1908, 0x80E1
GL_UNSIGNED_BYTE, GL_UNSIGNED_SHORT_5_6_5 = 0x1401, 0x8363
GL_PACK_ROW_LENGTH, GL_PACK_ALIGNMENT = 0x0D02, 0x0D05
GL_PIXEL_PACK_BUFFER, GL_PIXEL_PACK_BUFFER_BINDING = 0x88EB, 0x88ED
GL_SCISSOR_TEST = 0x0C11
GL_READ_TYPE, GL_READ_FORMAT = 0x8B9A, 0x8B9B          # (GL_IMPLEMENTATION_COLOR_READ_...)
GL_RENDERER, GL_VERSION, GL_EXTENSIONS = 0x1F01, 0x1F02, 0x1F03
# libretro's (libretro.h)
CONTEXT_GLES2, CONTEXT_GLES3, CONTEXT_GLES_VERSION = 2, 4, 5
ON_GPU = C.c_void_p(-1).value      # RETRO_HW_FRAME_BUFFER_VALID: the frame is in the chip's framebuffer
NO_3D = "N64 and PSP games need a Raspberry Pi 4 or 5"


class HWRender(C.Structure):
    """retro_hw_render_callback: the OpenGL an emulator wants, and its ways in to ours."""
    _fields_ = [("context_type", C.c_int), ("context_reset", C.c_void_p),
                ("get_current_framebuffer", C.c_void_p), ("get_proc_address", C.c_void_p),
                ("depth", C.c_bool), ("stencil", C.c_bool), ("bottom_left_origin", C.c_bool),
                ("version_major", C.c_uint), ("version_minor", C.c_uint), ("cache_context", C.c_bool),
                ("context_destroy", C.c_void_p), ("debug_context", C.c_bool)]


FRAMEBUFFER_CB = C.CFUNCTYPE(C.c_size_t)
PROC_CB = C.CFUNCTYPE(C.c_void_p, C.c_char_p)
CORE_CB = C.CFUNCTYPE(None)        # (the emulator's context_reset and context_destroy)


class GPUError(Exception):
    """Why there's no 3D, in words for the screen."""


def why_no_3d():
    """Why there's no OpenGL ES 3, in words for the screen: an older Pi, or a Pi 4 or 5 with its 3D off."""
    model = pi_model()
    if "Raspberry Pi" not in model:
        return "There's no OpenGL ES 3 here for 3D games"
    if slow_pi():
        return NO_3D
    return "Turn on 3D in config.txt: dtoverlay=vc4-kms-v3d"


def wanted_version(hw):
    """(major, minor) of OpenGL ES an emulator asks for, or None: a kind this can't give it."""
    if hw.context_type == CONTEXT_GLES3:
        return 3, 0
    if hw.context_type == CONTEXT_GLES_VERSION:
        return int(hw.version_major), int(hw.version_minor)
    if hw.context_type == CONTEXT_GLES2:
        return 2, 0
    return None


class GPU:
    """An OpenGL ES context of the graphics chip's, with no window. The emulator draws into
    framebuffer(); read() scales each frame into the screen's rows."""

    def __init__(self, version=(3, 0)):
        try:
            self.egl = C.CDLL("libEGL.so.1")
            self.gl = C.CDLL("libGLESv2.so.2")
        except OSError as ex:
            raise GPUError(why_no_3d()) from ex
        self.dpy = self.ctx = self.gbm_dev = None
        self.gbm_fd = -1
        self.fbo = 0                                   # the emulator's framebuffer
        self.made = []                                 # (framebuffers, renderbuffers) made, to delete
        self.out = None                                # ((w, h, kind), framebuffer): a frame at the screen's size
        self.read_as = {}                              # kind -> (format, type) the chip reads it in, or None
        self.told = set()
        self.fns()
        self.framebuffer_cb = FRAMEBUFFER_CB(lambda: self.fbo)
        self.proc_cb = PROC_CB(self.proc)
        try:
            self.start(version)
        except GPUError:
            self.close()
            raise

    def fns(self):
        E, G = self.egl, self.gl
        vp, i, u = C.c_void_p, C.c_int, C.c_uint
        for lib, name, res, args in (
                (E, "eglGetProcAddress", vp, [C.c_char_p]), (E, "eglQueryString", C.c_char_p, [vp, i]),
                (E, "eglGetPlatformDisplay", vp, [u, vp, vp]), (E, "eglGetDisplay", vp, [vp]),
                (E, "eglInitialize", u, [vp, vp, vp]), (E, "eglTerminate", u, [vp]),
                (E, "eglBindAPI", u, [u]), (E, "eglGetError", i, []),
                (E, "eglChooseConfig", u, [vp, C.POINTER(i), C.POINTER(vp), i, C.POINTER(i)]),
                (E, "eglCreateContext", vp, [vp, vp, vp, C.POINTER(i)]),
                (E, "eglDestroyContext", u, [vp, vp]), (E, "eglMakeCurrent", u, [vp, vp, vp, vp]),
                (E, "eglReleaseThread", u, []),
                (G, "glGetString", C.c_char_p, [u]), (G, "glGetIntegerv", None, [u, C.POINTER(i)]),
                (G, "glGetError", u, []), (G, "glIsEnabled", C.c_ubyte, [u]),
                (G, "glEnable", None, [u]), (G, "glDisable", None, [u]),
                (G, "glGenFramebuffers", None, [i, C.POINTER(u)]),
                (G, "glDeleteFramebuffers", None, [i, C.POINTER(u)]),
                (G, "glBindFramebuffer", None, [u, u]), (G, "glCheckFramebufferStatus", u, [u]),
                (G, "glFramebufferRenderbuffer", None, [u, u, u, u]),
                (G, "glGenRenderbuffers", None, [i, C.POINTER(u)]),
                (G, "glDeleteRenderbuffers", None, [i, C.POINTER(u)]),
                (G, "glBindRenderbuffer", None, [u, u]), (G, "glRenderbufferStorage", None, [u, u, i, i]),
                (G, "glBlitFramebuffer", None, [i, i, i, i, i, i, i, i, u, u]),
                (G, "glReadPixels", None, [i, i, i, i, u, u, vp]), (G, "glPixelStorei", None, [u, i]),
                (G, "glBindBuffer", None, [u, u]), (G, "glFinish", None, [])):
            f = getattr(lib, name)
            f.restype, f.argtypes = res, args
            setattr(self, name, f)

    # -- the context ------------------------------------------------------------------
    def display(self):
        """A display with no screen: Mesa's surfaceless one (the chip's own render node), or by GBM."""
        client = (self.eglQueryString(None, EGL_EXTENSIONS) or b"").decode(errors="replace").split()
        if "EGL_MESA_platform_surfaceless" in client:
            dpy = self.eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS, None, None)
            if dpy and self.eglInitialize(dpy, None, None):
                return dpy
        if "EGL_KHR_platform_gbm" in client or "EGL_MESA_platform_gbm" in client:
            try:
                gbm = C.CDLL("libgbm.so.1")
                gbm.gbm_create_device.restype, gbm.gbm_create_device.argtypes = C.c_void_p, [C.c_int]
                gbm.gbm_device_destroy.argtypes = [C.c_void_p]
            except (OSError, AttributeError):
                gbm = None
            for node in sorted(glob.glob("/dev/dri/renderD*")) if gbm else []:
                try:
                    fd = os.open(node, os.O_RDWR | os.O_CLOEXEC)
                except OSError:
                    continue
                dev = gbm.gbm_create_device(fd)
                dpy = self.eglGetPlatformDisplay(EGL_PLATFORM_GBM, dev, None) if dev else None
                if dpy and self.eglInitialize(dpy, None, None):
                    self.gbm, self.gbm_dev, self.gbm_fd = gbm, dev, fd
                    return dpy
                if dev:
                    gbm.gbm_device_destroy(dev)
                os.close(fd)
        dpy = self.eglGetDisplay(None)
        if dpy and self.eglInitialize(dpy, None, None):
            return dpy
        raise GPUError(why_no_3d())

    def start(self, version):
        major, minor = version
        self.dpy = self.display()
        if not self.eglBindAPI(EGL_OPENGL_ES_API):
            raise GPUError(why_no_3d())
        exts = (self.eglQueryString(self.dpy, EGL_EXTENSIONS) or b"").decode(errors="replace").split()
        config = None                                  # (none needed, with no window to match)
        if "EGL_KHR_no_config_context" not in exts and "EGL_MESA_configless_context" not in exts:
            want = (C.c_int * 5)(EGL_SURFACE_TYPE, 0, EGL_RENDERABLE_TYPE,
                                 EGL_OPENGL_ES3_BIT if major >= 3 else EGL_OPENGL_ES2_BIT, EGL_NONE)
            found, n = C.c_void_p(), C.c_int(0)
            if not self.eglChooseConfig(self.dpy, want, C.byref(found), 1, C.byref(n)) or n.value < 1:
                raise GPUError(why_no_3d())
            config = found.value
        attrs = (C.c_int * 5)(EGL_CONTEXT_MAJOR_VERSION, major, EGL_CONTEXT_MINOR_VERSION, minor, EGL_NONE)
        self.ctx = self.eglCreateContext(self.dpy, config, None, attrs)
        if not self.ctx or not self.eglMakeCurrent(self.dpy, None, None, self.ctx):
            raise GPUError(why_no_3d())
        text = (self.glGetString(GL_VERSION) or b"").decode(errors="replace")
        m = re.search(r"OpenGL ES (\d+)\.(\d+)", text)
        if not m or (int(m.group(1)), int(m.group(2))) < (major, minor):
            raise GPUError(why_no_3d())
        self.version = text
        self.renderer = (self.glGetString(GL_RENDERER) or b"").decode(errors="replace")
        self.exts = set((self.glGetString(GL_EXTENSIONS) or b"").decode(errors="replace").split())
        print(f"game: 3D on {self.renderer} ({self.version})", file=sys.stderr, flush=True)

    def proc(self, name):
        """An OpenGL function's address, for the emulator."""
        try:
            addr = self.eglGetProcAddress(name)
            if not addr:
                addr = C.cast(getattr(self.gl, name.decode()), C.c_void_p).value
            return addr
        except (AttributeError, UnicodeDecodeError, ValueError):
            return None

    def hand_over(self, hw):
        """Our ways in, written into the emulator's retro_hw_render_callback."""
        hw.get_current_framebuffer = C.cast(self.framebuffer_cb, C.c_void_p).value
        hw.get_proc_address = C.cast(self.proc_cb, C.c_void_p).value

    # -- framebuffers -------------------------------------------------------------------
    def get(self, what):
        v = C.c_int(0)
        self.glGetIntegerv(what, C.byref(v))
        return v.value

    def make(self, w, h, color, depth=None):
        """A framebuffer of renderbuffers (a color one, a depth one if asked), the bindings left as they were."""
        was_rb = self.get(GL_RENDERBUFFER_BINDING)
        was_read, was_draw = self.get(GL_READ_FRAMEBUFFER_BINDING), self.get(GL_DRAW_FRAMEBUFFER_BINDING)
        fb = C.c_uint(0)
        self.glGenFramebuffers(1, C.byref(fb))
        self.glBindFramebuffer(GL_DRAW_FRAMEBUFFER, fb.value)
        rbs = []
        for fmt, at in ((color, GL_COLOR_ATTACHMENT0),
                        (depth, GL_DEPTH_STENCIL_ATTACHMENT if depth == GL_DEPTH24_STENCIL8 else GL_DEPTH_ATTACHMENT)):
            if not fmt:
                continue
            rb = C.c_uint(0)
            self.glGenRenderbuffers(1, C.byref(rb))
            self.glBindRenderbuffer(GL_RENDERBUFFER, rb.value)
            self.glRenderbufferStorage(GL_RENDERBUFFER, fmt, int(w), int(h))
            self.glFramebufferRenderbuffer(GL_DRAW_FRAMEBUFFER, at, GL_RENDERBUFFER, rb.value)
            rbs.append(rb.value)
        ok = self.glCheckFramebufferStatus(GL_DRAW_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE
        self.glBindRenderbuffer(GL_RENDERBUFFER, was_rb)
        self.glBindFramebuffer(GL_READ_FRAMEBUFFER, was_read)
        self.glBindFramebuffer(GL_DRAW_FRAMEBUFFER, was_draw)
        self.made.append((fb.value, rbs))
        if not ok:
            self.drop(fb.value)
            raise GPUError("The graphics chip couldn't make a framebuffer")
        return fb.value

    def drop(self, fb):
        for i, (f, rbs) in enumerate(self.made):
            if f == fb:
                del self.made[i]
                self.glDeleteFramebuffers(1, C.byref(C.c_uint(f)))
                for rb in rbs:
                    self.glDeleteRenderbuffers(1, C.byref(C.c_uint(rb)))
                return

    def framebuffer(self, w, h, depth=True, stencil=False):
        """The emulator's framebuffer, as big as its biggest picture: each frame is drawn in it."""
        self.fbo = self.make(w, h, GL_RGBA8,
                             GL_DEPTH24_STENCIL8 if stencil else GL_DEPTH_COMPONENT24 if depth else None)
        return self.fbo

    # -- frames onto the screen -------------------------------------------------------------
    def read(self, view, kind, row_px, w, h, flipped=True, smooth=True):
        """The frame (w x h, at the framebuffer's bottom left) scaled by the chip to fill view: a slice of
        the screen's rows, each row_px pixels long. Read straight in, in the screen's own pixels (kind:
        'rgb565' or 'xrgb8888') when the chip can; otherwise returned, red, green, blue and alpha bytes."""
        dh, dw = view.shape
        key = (dw, dh, kind)
        self.glGetError()                              # (anything the emulator left: not ours)
        if self.out is None or self.out[0] != key:
            if self.out is not None:
                self.drop(self.out[1])
                self.out = None
            self.out = (key, self.make(dw, dh, GL_RGB565 if kind == "rgb565" else GL_RGBA8))
        out = self.out[1]
        scissor = self.glIsEnabled(GL_SCISSOR_TEST)
        pbo = self.get(GL_PIXEL_PACK_BUFFER_BINDING)
        was_read, was_draw = self.get(GL_READ_FRAMEBUFFER_BINDING), self.get(GL_DRAW_FRAMEBUFFER_BINDING)
        row, align = self.get(GL_PACK_ROW_LENGTH), self.get(GL_PACK_ALIGNMENT)
        if scissor:
            self.glDisable(GL_SCISSOR_TEST)            # (it'd cut the copy short)
        if pbo:
            self.glBindBuffer(GL_PIXEL_PACK_BUFFER, 0)  # (or the pixels would go into the emulator's buffer)
        self.glBindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo)
        self.glBindFramebuffer(GL_DRAW_FRAMEBUFFER, out)
        top, bottom = (dh, 0) if flipped else (0, dh)  # (the screen's top row first)
        self.glBlitFramebuffer(0, 0, w, h, 0, top, dw, bottom, GL_COLOR_BUFFER_BIT,
                               GL_LINEAR if smooth else GL_NEAREST)
        self.glBindFramebuffer(GL_READ_FRAMEBUFFER, out)
        native = self.native(kind)
        got = None
        if native:
            self.glPixelStorei(GL_PACK_ROW_LENGTH, row_px)
            self.glPixelStorei(GL_PACK_ALIGNMENT, view.itemsize)
            self.glReadPixels(0, 0, dw, dh, native[0], native[1], C.c_void_p(view.ctypes.data))
        else:
            got = np.empty((dh, dw, 4), dtype=np.uint8)
            self.glPixelStorei(GL_PACK_ROW_LENGTH, 0)
            self.glPixelStorei(GL_PACK_ALIGNMENT, 4)
            self.glReadPixels(0, 0, dw, dh, GL_RGBA, GL_UNSIGNED_BYTE, C.c_void_p(got.ctypes.data))
        err = self.glGetError()
        self.glPixelStorei(GL_PACK_ROW_LENGTH, row)
        self.glPixelStorei(GL_PACK_ALIGNMENT, align)
        self.glBindFramebuffer(GL_READ_FRAMEBUFFER, was_read)
        self.glBindFramebuffer(GL_DRAW_FRAMEBUFFER, was_draw)
        if pbo:
            self.glBindBuffer(GL_PIXEL_PACK_BUFFER, pbo)
        if scissor:
            self.glEnable(GL_SCISSOR_TEST)
        if err:
            if native:                                 # (that way didn't work here: the plain way from now on)
                self.read_as[kind] = None
            self.say(f"reading a frame: OpenGL error {err:#x}")
        return got

    def native(self, kind):
        """(format, type) the chip reads a frame in that's the screen's own pixels, or None."""
        if kind not in self.read_as:
            how = None
            if kind == "xrgb8888" and "GL_EXT_read_format_bgra" in self.exts:
                how = (GL_BGRA, GL_UNSIGNED_BYTE)      # (bytes B, G, R, A: 0xAARRGGBB, as the screen has it)
            elif kind == "rgb565" and self.out is not None:
                was = self.get(GL_READ_FRAMEBUFFER_BINDING)
                self.glBindFramebuffer(GL_READ_FRAMEBUFFER, self.out[1])
                if (self.get(GL_READ_FORMAT), self.get(GL_READ_TYPE)) == (GL_RGB, GL_UNSIGNED_SHORT_5_6_5):
                    how = (GL_RGB, GL_UNSIGNED_SHORT_5_6_5)
                self.glBindFramebuffer(GL_READ_FRAMEBUFFER, was)
            self.read_as[kind] = how
        return self.read_as[kind]

    def say(self, what):
        if what not in self.told:
            self.told.add(what)
            print(f"game: {what}", file=sys.stderr, flush=True)

    def close(self):
        """Everything let go: framebuffers, the context, the display."""
        if self.dpy and self.ctx:
            try:
                for fb, _ in list(self.made):
                    self.drop(fb)
            except OSError:
                pass
            self.eglMakeCurrent(self.dpy, None, None, None)
            self.eglDestroyContext(self.dpy, self.ctx)
        self.ctx = None
        if self.dpy:
            self.eglTerminate(self.dpy)
            self.dpy = None
        self.eglReleaseThread()
        if self.gbm_dev:
            self.gbm.gbm_device_destroy(self.gbm_dev)
            self.gbm_dev = None
        if self.gbm_fd >= 0:
            os.close(self.gbm_fd)
            self.gbm_fd = -1
