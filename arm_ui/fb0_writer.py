# ABOUTME: Direct framebuffer writer for Raspberry Pi /dev/fb0.
# ABOUTME: Scales a 480x320 pygame Surface to fb0 native dimensions and writes raw BGRA bytes.

import os
import sys

import pygame


class Fb0Writer:
    """Writes a pygame Surface directly to /dev/fb0.

    On OStra the bcm2708_fb framebuffer is 790x600 32bpp BGRA.
    fbcp copies fb0 → SPI TFT (480x320) and HDMI (480x320).
    We scale 480x320 → 790x600 here; fbcp scales back to 480x320.
    The double-scaling cancels exactly, giving a pixel-perfect result.

    Graceful degradation: if /dev/fb0 is not writable (SSH session,
    Windows dev machine), write() is a no-op so the rest of the app
    still runs for headless testing.
    """

    _FB0_PATH   = "/dev/fb0"
    _VSIZE_PATH = "/sys/class/graphics/fb0/virtual_size"
    _BPP_PATH   = "/sys/class/graphics/fb0/bits_per_pixel"
    _STRIDE_PATH = "/sys/class/graphics/fb0/stride"

    def __init__(self, src_w: int, src_h: int) -> None:
        self._src_w = src_w
        self._src_h = src_h
        self._fb_w  = src_w   # fallback: no scaling
        self._fb_h  = src_h
        self._stride = 0
        self._bpp    = 32
        self._available = False
        self._fb_file   = None

        self._open()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _open(self) -> None:
        """Try to open /dev/fb0 and read its geometry."""
        try:
            with open(self._VSIZE_PATH) as f:
                self._fb_w, self._fb_h = map(int, f.read().strip().split(","))
            with open(self._BPP_PATH) as f:
                self._bpp = int(f.read().strip())
            with open(self._STRIDE_PATH) as f:
                self._stride = int(f.read().strip())

            self._fb_file = open(self._FB0_PATH, "wb")  # noqa: SIM115
            self._available = True
            print(
                f"[fb0_writer] /dev/fb0 open: {self._fb_w}x{self._fb_h} "
                f"{self._bpp}bpp stride={self._stride}",
                file=sys.stderr,
            )
        except OSError as exc:
            print(
                f"[fb0_writer] /dev/fb0 unavailable ({exc}); "
                "running headless (offscreen only).",
                file=sys.stderr,
            )
            self._available = False

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True if /dev/fb0 is open and writable."""
        return self._available

    def write_surface(self, surface: pygame.Surface) -> None:
        """Scale surface to fb0 dimensions and write to /dev/fb0.

        No-op if /dev/fb0 is not available (SSH / dev machine).
        """
        if not self._available:
            return

        # Scale from 480x320 to fb0 native size (790x600 on OStra)
        if self._fb_w != self._src_w or self._fb_h != self._src_h:
            scaled = pygame.transform.scale(surface, (self._fb_w, self._fb_h))
        else:
            scaled = surface

        # Convert to BGRA bytes matching fb0 pixel format
        raw = pygame.image.tobytes(scaled, "BGRA")

        # Write only as many bytes as the fb0 expects (stride * height)
        total = self._stride * self._fb_h if self._stride else len(raw)
        try:
            self._fb_file.seek(0)
            self._fb_file.write(raw[:total])
            self._fb_file.flush()
        except OSError as exc:
            print(f"[fb0_writer] write error: {exc}", file=sys.stderr)
            self._available = False

    def close(self) -> None:
        """Close the framebuffer file handle."""
        if self._fb_file is not None:
            try:
                self._fb_file.close()
            except OSError:
                pass
            self._fb_file = None
        self._available = False
