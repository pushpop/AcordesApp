# ABOUTME: Visualizer pygame window - runs as a detached subprocess on Windows, macOS, and Linux desktop.
# ABOUTME: Hosts multiple visual modes (VU meter, waveform oscilloscope) driven by shared memory.

import sys
import os
import json
import math
import struct
import platform
import pygame
from pathlib import Path
from multiprocessing.shared_memory import SharedMemory


# Visual constants
WINDOW_WIDTH  = 216
WINDOW_HEIGHT = 162
WINDOW_TITLE  = "Acordes Visualizer"
FPS           = 60

# ── VU meter layout ───────────────────────────────────────────────────────────

# Bar layout — two thin bars centered close together
BAR_WIDTH   = 16
BAR_GAP     = 6
BAR_TOP     = 24
BAR_HEIGHT  = 110
BAR_LEFT_X  = WINDOW_WIDTH // 2 - BAR_WIDTH - BAR_GAP // 2
BAR_RIGHT_X = WINDOW_WIDTH // 2 + BAR_GAP // 2

# dB scale: bar fraction maps linearly from DB_MIN to DB_MAX (0 dBFS).
DB_MIN = -48.0
DB_MAX =   0.0
DB_TICKS = [0, -6, -12, -18, -24, -36]

# Linear gain boost applied after dB mapping (does not affect dB labels).
LEVEL_GAIN = 1.15

# Asymmetric smoothing coefficients at 60 FPS.
SMOOTH_ATTACK  = 0.6
SMOOTH_RELEASE = 0.88

# ── Oscilloscope layout ───────────────────────────────────────────────────────

# Waveform display area (reuses BAR_TOP / BAR_HEIGHT for vertical alignment)
SCOPE_LEFT    = 8
SCOPE_RIGHT   = WINDOW_WIDTH - 8
SCOPE_WIDTH   = SCOPE_RIGHT - SCOPE_LEFT
SCOPE_TOP     = BAR_TOP
SCOPE_HEIGHT  = BAR_HEIGHT

# Number of samples read from shm circular buffer and number displayed per frame
WAVEFORM_SAMPLES = 2048   # must match engine_proxy / synth_engine constant
DISPLAY_SAMPLES  = 512    # samples shown across the scope width (~11.6 ms at 44100 Hz)

# Phosphor green — classic oscilloscope colour
SCOPE_COLOR      = (0, 220, 140)
SCOPE_GRID_COLOR = (40, 60, 45)

# ── Shared colours ────────────────────────────────────────────────────────────

BG_COLOR         = (18, 18, 18)
TEXT_COLOR       = (240, 240, 240)
TICK_COLOR       = (100, 100, 100)
BAR_BORDER_COLOR = (80, 80, 80)

# Shared memory layout (set by synth_mode.py):
#   bytes  0-3:  level_l  (f32)
#   bytes  4-7:  level_r  (f32)
#   bytes  8-11: command  (i32)  0=idle, 1=toggle fullscreen, 2=cycle mode
#   bytes 12-15: write_pos (i32) circular waveform buffer head
#   bytes 16+:   WAVEFORM_SAMPLES x f32 waveform data
SHM_SIZE = 16 + WAVEFORM_SAMPLES * 4   # 8208 bytes

# Position persistence file - stored next to this module
_POSITION_FILE = Path(__file__).parent / 'window_position.json'

# Visual mode indices
MODE_VU_METER    = 0
MODE_OSCILLOSCOPE = 1
MODE_COUNT       = 2
MODE_NAMES       = ["VU Meter", "Scope"]


# ── Position persistence ─────────────────────────────────────────────────────

def _load_position():
    """Load last saved window position. Returns (x, y) or (None, None)."""
    try:
        data = json.loads(_POSITION_FILE.read_text())
        return int(data['x']), int(data['y'])
    except Exception:
        return None, None


def _save_position(x: int, y: int):
    """Save current window position to disk."""
    try:
        _POSITION_FILE.write_text(json.dumps({'x': x, 'y': y}))
    except Exception:
        pass


# ── Platform window helpers ───────────────────────────────────────────────────
#
# Three tiers:
#   Windows  - Win32 API via ctypes (always-on-top, drag, restore, screen size)
#   Linux    - wmctrl subprocess calls (always-on-top, drag); requires wmctrl
#              package (available on all major desktop distros via apt/dnf/pacman)
#   macOS    - No always-on-top or drag (would require pyobjc); window works fully
#              but stays at default Z-order and cannot be dragged by title-less frame.

_SYSTEM = platform.system()


# ── Windows / Win32 ──────────────────────────────────────────────────────────

def _get_win32():
    """Return (user32, ctypes) or (None, None) on non-Windows."""
    if _SYSTEM != "Windows":
        return None, None
    try:
        import ctypes
        import ctypes.wintypes
        return ctypes.windll.user32, ctypes
    except Exception:
        return None, None


def _setup_always_on_top_win32(user32, ctypes):
    """
    Locate the window handle via FindWindowW and apply always-on-top.
    Sets WS_EX_TOPMOST extended style (persistent across focus changes).
    Returns hwnd or None.
    """
    if user32 is None:
        return None
    try:
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if not hwnd:
            return None
        GWL_EXSTYLE   = -20
        WS_EX_TOPMOST = 0x00000008
        current = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current | WS_EX_TOPMOST)
        HWND_TOPMOST = ctypes.wintypes.HWND(-1)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0002 | 0x0001)
        return hwnd
    except Exception:
        return None


def _get_window_pos_win32(user32, ctypes, hwnd):
    """Return (x, y) of the window's top-left corner in screen coords."""
    try:
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.left, rect.top
    except Exception:
        return 0, 0


def _set_window_pos_win32(user32, hwnd, x: int, y: int):
    """Move the window to (x, y) without changing size or Z-order."""
    try:
        SWP_NOSIZE   = 0x0001
        SWP_NOZORDER = 0x0004
        user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER)
    except Exception:
        pass


def _get_cursor_screen_pos_win32(user32, ctypes):
    """Return current cursor position in screen coordinates."""
    try:
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return 0, 0


def _restore_if_minimized_win32(user32, ctypes, hwnd):
    """Restore the window if it was minimized (Win32 only)."""
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    except Exception:
        pass


def _get_screen_size_win32(user32, ctypes):
    """Return (width, height) of the primary monitor via Win32."""
    try:
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        info = pygame.display.Info()
        return info.current_w, info.current_h


# ── Linux / wmctrl ───────────────────────────────────────────────────────────

def _get_x11_window_id():
    """Return the X11 window ID from pygame WM info, or None."""
    try:
        wm = pygame.display.get_wm_info()
        return wm.get('window')
    except Exception:
        return None


def _setup_always_on_top_linux(x11_wid):
    """
    Use wmctrl to add the _NET_WM_STATE_ABOVE hint.
    Silently ignored if wmctrl is not installed or not on X11.
    """
    if x11_wid is None:
        return
    try:
        import subprocess as _sp
        _sp.Popen(
            ['wmctrl', '-i', '-r', hex(x11_wid), '-b', 'add,above'],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    except Exception:
        pass


def _move_window_linux(x11_wid, x: int, y: int):
    """
    Move window to (x, y) via wmctrl -e gravity,x,y,w,h.
    -1 means "keep current" for width/height.
    """
    if x11_wid is None:
        return
    try:
        import subprocess as _sp
        _sp.Popen(
            ['wmctrl', '-i', '-r', hex(x11_wid), '-e', f'0,{x},{y},-1,-1'],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    except Exception:
        pass


def _get_window_pos_linux(x11_wid) -> tuple:
    """
    Read window position via xwininfo.
    Returns (x, y) or (0, 0) on failure.
    """
    if x11_wid is None:
        return 0, 0
    try:
        import subprocess as _sp
        out = _sp.check_output(
            ['xwininfo', '-id', str(x11_wid)],
            stderr=_sp.DEVNULL, text=True
        )
        x = y = 0
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('Absolute upper-left X:'):
                x = int(line.split(':')[1].strip())
            elif line.startswith('Absolute upper-left Y:'):
                y = int(line.split(':')[1].strip())
        return x, y
    except Exception:
        return 0, 0


# ── Unified interface (called by render loop) ─────────────────────────────────

def _setup_always_on_top(user32, ctypes):
    """Apply always-on-top for the current platform."""
    if _SYSTEM == "Windows":
        return _setup_always_on_top_win32(user32, ctypes)
    elif _SYSTEM == "Linux":
        wid = _get_x11_window_id()
        _setup_always_on_top_linux(wid)
        return wid   # used as the opaque "hwnd" on Linux
    return None      # macOS: not supported without pyobjc


def _get_window_pos(user32, ctypes, hwnd):
    if _SYSTEM == "Windows":
        return _get_window_pos_win32(user32, ctypes, hwnd)
    elif _SYSTEM == "Linux":
        return _get_window_pos_linux(hwnd)
    return 0, 0


def _set_window_pos(user32, hwnd, x: int, y: int):
    if _SYSTEM == "Windows":
        _set_window_pos_win32(user32, hwnd, x, y)
    elif _SYSTEM == "Linux":
        _move_window_linux(hwnd, x, y)


def _get_cursor_screen_pos(user32, ctypes):
    if _SYSTEM == "Windows":
        return _get_cursor_screen_pos_win32(user32, ctypes)
    # Linux / macOS: pygame mouse position is window-relative; caller adds window origin
    mx, my = pygame.mouse.get_pos()
    return mx, my


def _restore_if_minimized(user32, ctypes, hwnd):
    if _SYSTEM == "Windows":
        _restore_if_minimized_win32(user32, ctypes, hwnd)
    # Linux/macOS: not needed; wmctrl handles focus, macOS no-op


def _get_screen_size(user32, ctypes):
    if _SYSTEM == "Windows":
        return _get_screen_size_win32(user32, ctypes)
    info = pygame.display.Info()
    return info.current_w, info.current_h


# ── VU meter drawing ─────────────────────────────────────────────────────────

def _level_to_bar_fraction(level: float) -> float:
    """Map linear amplitude (0-1) to bar fill fraction via dB scale + gain boost."""
    if level <= 0.0:
        return 0.0
    db = 20.0 * math.log10(max(level, 1e-9))
    fraction = (db - DB_MIN) / (DB_MAX - DB_MIN)
    return max(0.0, min(1.0, fraction * LEVEL_GAIN))


def _level_to_color(fraction: float) -> tuple:
    """Map bar fill fraction 0-1 to yellow → orange → red."""
    fraction = max(0.0, min(1.0, fraction))
    if fraction < 0.5:
        t = fraction / 0.5
        return (255, int(255 - t * 115), 0)
    t = (fraction - 0.5) / 0.5
    return (255, int(140 - t * 140), 0)


def _draw_bar(surface, x, level, label, font):
    """Draw a single vertical VU bar with border, fill, and channel label."""
    fraction = _level_to_bar_fraction(level)
    pygame.draw.rect(surface, BAR_BORDER_COLOR,
                     pygame.Rect(x, BAR_TOP, BAR_WIDTH, BAR_HEIGHT), 1)
    if fraction > 0.0:
        fill_height = int(BAR_HEIGHT * fraction)
        fill_y = BAR_TOP + (BAR_HEIGHT - fill_height)
        pygame.draw.rect(surface, _level_to_color(fraction),
                         pygame.Rect(x + 1, fill_y, BAR_WIDTH - 2, fill_height))
    label_surf = font.render(label, True, TEXT_COLOR)
    surface.blit(label_surf, label_surf.get_rect(
        centerx=x + BAR_WIDTH // 2, top=BAR_TOP + BAR_HEIGHT + 16))


def _draw_db_scale(surface, font_small):
    """Draw dB tick marks and labels to the right of the right bar."""
    scale_x = BAR_RIGHT_X + BAR_WIDTH + 3
    for db in DB_TICKS:
        fraction = (db - DB_MIN) / (DB_MAX - DB_MIN)
        fraction = max(0.0, min(1.0, fraction))
        y = BAR_TOP + int(BAR_HEIGHT * (1.0 - fraction))
        pygame.draw.line(surface, TICK_COLOR, (scale_x, y), (scale_x + 4, y))
        label = "0" if db == 0 else str(db)
        label_surf = font_small.render(label, True, TICK_COLOR)
        surface.blit(label_surf, label_surf.get_rect(left=scale_x + 6, centery=y))


# ── Oscilloscope drawing ──────────────────────────────────────────────────────

def _read_waveform(shm_buf) -> list:
    """Read the waveform circular buffer from shm and return samples in time order."""
    try:
        write_pos = struct.unpack_from('i', shm_buf, 12)[0]
        raw = struct.unpack_from(f'{WAVEFORM_SAMPLES}f', shm_buf, 16)
        # Reorder so index 0 is the oldest sample (write_pos is next-write slot)
        return list(raw[write_pos:]) + list(raw[:write_pos])
    except Exception:
        return [0.0] * WAVEFORM_SAMPLES


def _find_trigger(samples: list) -> int:
    """
    Find a zero-crossing trigger (negative to positive transition).
    Searches the middle quarter of the buffer so there is always room to
    display DISPLAY_SAMPLES samples after the trigger point.
    Returns the index of the trigger, or a fallback index if none found.
    """
    search_start = WAVEFORM_SAMPLES // 4
    search_end   = WAVEFORM_SAMPLES - DISPLAY_SAMPLES - 1
    for i in range(search_start, search_end):
        if samples[i] <= 0.0 and samples[i + 1] > 0.0:
            return i
    # No crossing found: return middle so we still show something
    return search_start


def _draw_oscilloscope(surface, shm_buf, font_small):
    """Draw triggered oscilloscope waveform into the scope area."""
    samples = _read_waveform(shm_buf)
    trigger = _find_trigger(samples)
    window  = samples[trigger:trigger + DISPLAY_SAMPLES]

    if len(window) < 2:
        return

    # Map sample index → screen x, sample value → screen y
    x_scale = SCOPE_WIDTH / (DISPLAY_SAMPLES - 1)
    y_mid   = SCOPE_TOP + SCOPE_HEIGHT / 2
    y_scale = SCOPE_HEIGHT / 2 * 0.9   # 90% of half-height for a little margin

    points = []
    for i, s in enumerate(window):
        px = int(SCOPE_LEFT + i * x_scale)
        py = int(y_mid - s * y_scale)
        points.append((px, py))

    if len(points) >= 2:
        # Draw twice (offset by 1 px) to get a ~2px anti-aliased line
        pygame.draw.aalines(surface, SCOPE_COLOR, False, points)
        points_thick = [(x, y + 1) for x, y in points]
        pygame.draw.aalines(surface, SCOPE_COLOR, False, points_thick)


# ── Main render loop ──────────────────────────────────────────────────────────

def main(shm_name: str):
    """
    Pygame render loop. Reads levels and waveform from shared memory by name.
    Tab cycles between visual modes. 'f' toggles fullscreen. 'v' closes window.
    Supports click-drag to move window (windowed mode). Remembers last position.
    """
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

    try:
        shm = SharedMemory(name=shm_name)
    except Exception as e:
        print(f"Visualizer: cannot open shared memory '{shm_name}': {e}")
        return

    # Set spawn position BEFORE pygame creates the window so there is no
    # white-flash-then-jump. SDL reads this env var at display init time.
    saved_x, saved_y = _load_position()
    if saved_x is not None:
        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{saved_x},{saved_y}"
    else:
        os.environ.pop('SDL_VIDEO_WINDOW_POS', None)

    pygame.init()
    surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.NOFRAME)
    pygame.display.set_caption(WINDOW_TITLE)

    # Paint BG_COLOR immediately so there is no black flash before the first frame
    surface.fill(BG_COLOR)
    pygame.display.flip()

    user32, ctypes = _get_win32()
    hwnd = _setup_always_on_top(user32, ctypes)

    clock       = pygame.time.Clock()
    _font_path  = Path(__file__).parent.parent / 'arm_ui' / 'fonts' / 'Silkscreen.ttf'
    font        = pygame.font.Font(str(_font_path), 8)
    title_font  = pygame.font.Font(str(_font_path), 8)
    scale_font  = pygame.font.Font(str(_font_path), 6)
    running     = True
    dragging    = False
    drag_offset_x = 0
    drag_offset_y = 0
    smooth_l    = 0.0
    smooth_r    = 0.0
    vis_mode    = MODE_VU_METER

    # render_surf is the fixed-size canvas; always drawn here then optionally scaled
    render_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
    fullscreen  = False

    def _toggle_fullscreen():
        nonlocal fullscreen, surface, hwnd, saved_x, saved_y
        fullscreen = not fullscreen
        if fullscreen:
            screen_w, screen_h = _get_screen_size(user32, ctypes)
            surface = pygame.display.set_mode(
                (screen_w, screen_h),
                pygame.FULLSCREEN | pygame.NOFRAME
            )
        else:
            surface = pygame.display.set_mode(
                (WINDOW_WIDTH, WINDOW_HEIGHT),
                pygame.NOFRAME
            )
            pygame.display.set_caption(WINDOW_TITLE)
            if saved_x is not None:
                os.environ['SDL_VIDEO_WINDOW_POS'] = f"{saved_x},{saved_y}"
        hwnd = _setup_always_on_top(user32, ctypes)
        if not fullscreen and hwnd and saved_x is not None:
            _set_window_pos(user32, hwnd, saved_x, saved_y)

    while running:
        if hwnd:
            _restore_if_minimized(user32, ctypes, hwnd)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_v:
                    running = False
                elif event.key == pygame.K_f:
                    _toggle_fullscreen()
                elif event.key == pygame.K_TAB:
                    vis_mode = (vis_mode + 1) % MODE_COUNT

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not fullscreen and hwnd:
                    if _SYSTEM == "Windows" and user32:
                        win_x, win_y = _get_window_pos(user32, ctypes, hwnd)
                        cur_x, cur_y = _get_cursor_screen_pos(user32, ctypes)
                        drag_offset_x = cur_x - win_x
                        drag_offset_y = cur_y - win_y
                    else:
                        # Linux/macOS: record mouse-in-window position as drag anchor
                        drag_offset_x, drag_offset_y = event.pos
                    dragging = True

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging and hwnd:
                    final_x, final_y = _get_window_pos(user32, ctypes, hwnd)
                    _save_position(final_x, final_y)
                    saved_x, saved_y = final_x, final_y
                dragging = False

            elif event.type == pygame.MOUSEMOTION and dragging and hwnd:
                if _SYSTEM == "Windows" and user32:
                    cur_x, cur_y = _get_cursor_screen_pos(user32, ctypes)
                    _set_window_pos(user32, hwnd,
                                    cur_x - drag_offset_x,
                                    cur_y - drag_offset_y)
                else:
                    # Linux: compute target screen position from saved window origin
                    # and the delta between current and anchor mouse position
                    rel_dx = event.pos[0] - drag_offset_x
                    rel_dy = event.pos[1] - drag_offset_y
                    base_x, base_y = _get_window_pos(user32, ctypes, hwnd)
                    _set_window_pos(user32, hwnd,
                                    base_x + rel_dx,
                                    base_y + rel_dy)

        # Read levels and command from shared memory
        try:
            level_l, level_r = struct.unpack_from('ff', shm.buf, 0)
            cmd = struct.unpack_from('i', shm.buf, 8)[0]
        except Exception:
            level_l = level_r = 0.0
            cmd = 0

        # NaN = shutdown sentinel from parent
        if level_l != level_l:
            running = False
            break

        # Commands from Textual keybindings
        if cmd == 1:   # toggle fullscreen
            try:
                struct.pack_into('i', shm.buf, 8, 0)
            except Exception:
                pass
            _toggle_fullscreen()
        elif cmd == 2:  # cycle visual mode
            try:
                struct.pack_into('i', shm.buf, 8, 0)
            except Exception:
                pass
            vis_mode = (vis_mode + 1) % MODE_COUNT

        # Smooth VU levels (used by VU mode; still computed so switching modes is seamless)
        coeff_l = SMOOTH_ATTACK  if level_l > smooth_l else SMOOTH_RELEASE
        coeff_r = SMOOTH_ATTACK  if level_r > smooth_r else SMOOTH_RELEASE
        smooth_l = smooth_l * coeff_l + level_l * (1.0 - coeff_l)
        smooth_r = smooth_r * coeff_r + level_r * (1.0 - coeff_r)

        # Draw to fixed-size render surface
        bg = (0, 0, 0) if fullscreen else BG_COLOR
        render_surf.fill(bg)

        # Mode label (top-centre)
        label_surf = title_font.render(MODE_NAMES[vis_mode], True, TEXT_COLOR)
        render_surf.blit(label_surf, label_surf.get_rect(
            centerx=WINDOW_WIDTH // 2, top=10))

        if vis_mode == MODE_VU_METER:
            _draw_bar(render_surf, BAR_LEFT_X,  smooth_l, "L", font)
            _draw_bar(render_surf, BAR_RIGHT_X, smooth_r, "R", font)
            _draw_db_scale(render_surf, scale_font)

        elif vis_mode == MODE_OSCILLOSCOPE:
            _draw_oscilloscope(render_surf, shm.buf, scale_font)

        # Blit to display, scaling to fill screen in fullscreen mode
        if fullscreen:
            sw, sh = surface.get_size()
            scale  = min(sw / WINDOW_WIDTH, sh / WINDOW_HEIGHT)
            scaled_w = int(WINDOW_WIDTH  * scale)
            scaled_h = int(WINDOW_HEIGHT * scale)
            scaled = pygame.transform.scale(render_surf, (scaled_w, scaled_h))
            surface.fill((0, 0, 0))
            surface.blit(scaled, ((sw - scaled_w) // 2, (sh - scaled_h) // 2))
        else:
            surface.blit(render_surf, (0, 0))

        pygame.display.flip()
        clock.tick(FPS)

    # Save position on any exit path
    if hwnd and not fullscreen:
        final_x, final_y = _get_window_pos(user32, ctypes, hwnd)
        _save_position(final_x, final_y)

    shm.close()
    pygame.quit()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m visualizer.visualizer_window <shm_name>")
        sys.exit(1)
    main(sys.argv[1])
