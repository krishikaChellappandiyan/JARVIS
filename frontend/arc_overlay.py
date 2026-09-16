"""
ArcReactorOverlay — Manages the frameless, transparent, always-on-top
floating Arc Reactor overlay window via pywebview.

Creates a second pywebview window in the same process as the main
J.A.R.V.I.S. tactical console, sharing the same JarvisAPI backend.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARC_HTML_PATH = ROOT / "arc_reactor.html"

# Overlay window dimensions (small footprint for the reactor + response bubble)
OVERLAY_WIDTH  = 440
OVERLAY_HEIGHT = 300


class ArcReactorOverlay:
    """Manages the frameless, transparent, always-on-top Arc Reactor floating window."""

    def __init__(self, jarvis_api):
        """
        Args:
            jarvis_api: The main JarvisAPI instance from frontend.desktop
        """
        self.api = jarvis_api
        self.window = None
        self.arc_api = None
        self.is_expanded = True
        self.position = {'x': None, 'y': None}
        self._on_top_enforced = False

    def create_window(self, webview_module):
        """
        Create the overlay window. Must be called BEFORE webview.start().

        Args:
            webview_module: The imported webview module (to call webview.create_window)

        Returns:
            The created pywebview Window, or None if creation fails.
        """
        from frontend.arc_api import ArcReactorAPI

        self.arc_api = ArcReactorAPI(self.api, self)

        try:
            # Get screen dimensions for initial positioning
            screen_w, screen_h = self._get_screen_size()
            # Position at right edge, vertically centered
            init_x = max(0, screen_w - OVERLAY_WIDTH - 10)
            init_y = max(0, (screen_h // 2) - (OVERLAY_HEIGHT // 2))

            self.window = webview_module.create_window(
                title="J.A.R.V.I.S. Arc Reactor",
                url=str(ARC_HTML_PATH),
                js_api=self.arc_api,
                width=OVERLAY_WIDTH,
                height=OVERLAY_HEIGHT,
                x=init_x,
                y=init_y,
                resizable=False,
                frameless=True,
                transparent=True,
                on_top=True,
                easy_drag=False,       # We handle drag ourselves in JS
                shadow=False,
                focus=False,           # Don't steal focus from user's active app
                min_size=(100, 100),
                background_color='#00000000',
            )

            if self.window:
                self.arc_api.set_window(self.window)
                self.position = {'x': init_x, 'y': init_y}
                print(f"[arc-reactor] Overlay window created at ({init_x}, {init_y})")

                # Register close handler — don't exit the whole app if overlay closes
                def _on_overlay_closed():
                    print("[arc-reactor] Overlay window closed")
                    self.window = None
                self.window.events.closed += _on_overlay_closed

            return self.window

        except Exception as e:
            print(f"[arc-reactor] Failed to create overlay window: {e}")
            return None

    def ensure_on_top(self):
        """
        Fallback: enforce always-on-top using wmctrl or xdotool on Linux.
        Called after webview.start() if the native on_top doesn't stick.
        """
        if self._on_top_enforced:
            return

        for tool, cmd in [
            ("wmctrl", ["wmctrl", "-r", "J.A.R.V.I.S. Arc Reactor", "-b", "add,above"]),
            ("xdotool", ["xdotool", "search", "--name", "J.A.R.V.I.S. Arc Reactor", "set_window", "--override-redirect", "1"]),
        ]:
            try:
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                if result.returncode == 0:
                    self._on_top_enforced = True
                    print(f"[arc-reactor] Always-on-top enforced via {tool}")
                    return
            except Exception:
                continue

    def collapse(self):
        """Programmatically collapse the overlay (from Python side)."""
        self.is_expanded = False
        if self.window and self.arc_api and self.arc_api._is_ready:
            self.arc_api._emit_js("window.arcReactor.collapse()")

    def expand(self):
        """Programmatically expand the overlay (from Python side)."""
        self.is_expanded = True
        if self.window and self.arc_api and self.arc_api._is_ready:
            self.arc_api._emit_js("window.arcReactor.expand()")

    def _get_screen_size(self) -> tuple:
        """Get primary screen resolution. Returns (width, height)."""
        # Try xdpyinfo
        try:
            out = subprocess.check_output(
                ["xdpyinfo"], stderr=subprocess.DEVNULL, timeout=2
            ).decode()
            for line in out.splitlines():
                if "dimensions:" in line:
                    parts = line.split()
                    idx = parts.index("dimensions:") + 1 if "dimensions:" in parts else -1
                    if idx > 0:
                        dims = parts[idx].split('x')
                        return int(dims[0]), int(dims[1])
        except Exception:
            pass

        # Try xrandr
        try:
            out = subprocess.check_output(
                ["xrandr", "--current"], stderr=subprocess.DEVNULL, timeout=2
            ).decode()
            for line in out.splitlines():
                if " connected" in line and "x" in line:
                    import re
                    m = re.search(r'(\d{3,5})x(\d{3,5})', line)
                    if m:
                        return int(m.group(1)), int(m.group(2))
        except Exception:
            pass

        # Fallback
        return 1920, 1080
