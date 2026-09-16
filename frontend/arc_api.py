"""
ArcReactorAPI — Lightweight JS↔Python bridge for the Arc Reactor floating overlay.

Exposes a minimal subset of JarvisAPI capabilities to the overlay window.
Handles push-to-talk audio processing, screen capture for vision context,
and window position management.
"""

import os
import sys
import time
import json
import base64
import threading
import tempfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ArcReactorAPI:
    """Minimal API exposed to the Arc Reactor overlay HTML via pywebview js_api."""

    def __init__(self, parent_api, overlay):
        """
        Args:
            parent_api: The main JarvisAPI instance (frontend.desktop.JarvisAPI)
            overlay:    The ArcReactorOverlay window manager
        """
        self._parent = parent_api
        self._overlay = overlay
        self._window = None            # Set by overlay manager after window creation
        self._screenshot_path = None   # Most recent screenshot for vision context
        self._is_ready = False

    def set_window(self, window):
        """Bind the pywebview Window reference for evaluate_js calls."""
        self._window = window

    def _emit_js(self, js_code: str):
        """Safely evaluate JavaScript in the overlay window."""
        if self._window:
            try:
                self._window.evaluate_js(js_code)
            except Exception as e:
                print(f"[arc-reactor] JS eval error: {e}")

    # ─── Lifecycle Callbacks (called from JS) ───

    def on_ready(self):
        """Called when the overlay HTML has loaded and is ready."""
        self._is_ready = True
        print("[arc-reactor] Overlay ready and operational")

    def on_collapse(self):
        """Called when the user collapses the overlay via the arrow."""
        print("[arc-reactor] Overlay collapsed — minimal footprint mode")

    def on_expand(self):
        """Called when the user expands the overlay via the arrow."""
        print("[arc-reactor] Overlay expanded — standing by")

    # ─── Push-to-Talk ───

    def push_to_talk_start(self):
        """Begin push-to-talk: capture desktop screenshot for vision context."""
        def _capture():
            try:
                self._screenshot_path = self._parent._capture_desktop_screenshot()
                if self._screenshot_path:
                    print(f"[arc-reactor] Vision context captured: {self._screenshot_path}")
                else:
                    print("[arc-reactor] Vision capture unavailable — voice-only mode")
            except Exception as e:
                print(f"[arc-reactor] Screenshot capture error: {e}")
                self._screenshot_path = None

        threading.Thread(target=_capture, daemon=True).start()

    def push_to_talk_native(self):
        """Fallback: use native arecord/sox microphone when browser getUserMedia fails."""
        def _native_record():
            try:
                self._parent.start_native_mic()
            except Exception as e:
                print(f"[arc-reactor] Native mic fallback error: {e}")
        threading.Thread(target=_native_record, daemon=True).start()

    def push_to_talk_stop(self, audio_b64: str):
        """Process recorded audio: transcode, transcribe, query AI with screen context, respond via TTS."""
        def _process():
            try:
                self._emit_js("window.arcReactor.setState('processing')")

                # 1. Decode webm audio and convert to wav
                wav_path = self._transcode_webm_to_wav(audio_b64)
                if not wav_path:
                    self._emit_js("window.arcReactor.showError('Audio processing failed')")
                    return

                # 2. Transcribe via the parent's STT pipeline
                transcript = self._parent._transcribe_audio_fast(wav_path)
                if not transcript or len(transcript.strip()) < 2:
                    self._emit_js("window.arcReactor.showError('Could not understand audio')")
                    return

                print(f"[arc-reactor] Operator said: \"{transcript}\"")

                # 3. Query AI with optional vision context
                image_path = self._screenshot_path
                self._screenshot_path = None  # consume it

                voice = self._parent._voice
                if voice:
                    response = voice.chat(
                        transcript,
                        image_path=image_path,
                        operator_name="Sir"
                    )
                else:
                    response = f"Voice engine not available, Sir. You said: {transcript}"

                # 4. Show response in bubble
                safe_response = json.dumps(response or "No response generated, Sir.")
                self._emit_js(f"window.arcReactor.showResponse({safe_response})")

                # 5. Speak response via TTS
                if voice and response:
                    try:
                        voice.speak(response)
                    except Exception as tts_err:
                        print(f"[arc-reactor] TTS error: {tts_err}")

                self._emit_js("window.arcReactor.onSpeakingDone()")

            except Exception as e:
                print(f"[arc-reactor] Push-to-talk processing error: {e}")
                safe_err = json.dumps(f"Processing error: {str(e)[:80]}")
                self._emit_js(f"window.arcReactor.showError({safe_err})")

        threading.Thread(target=_process, daemon=True, name="arc-ptt-process").start()

    def _transcode_webm_to_wav(self, audio_b64: str) -> str | None:
        """Convert base64 webm/opus audio to 16kHz mono WAV for STT."""
        try:
            raw = base64.b64decode(audio_b64)
            if len(raw) < 100:
                return None

            webm_path = os.path.join(tempfile.gettempdir(), f"arc_ptt_{int(time.time())}.webm")
            wav_path  = os.path.join(tempfile.gettempdir(), f"arc_ptt_{int(time.time())}.wav")

            with open(webm_path, 'wb') as f:
                f.write(raw)

            # Use ffmpeg to transcode
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", webm_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10
            )

            # Clean up webm
            try:
                os.unlink(webm_path)
            except Exception:
                pass

            if result.returncode == 0 and os.path.exists(wav_path):
                # Normalize audio gain
                try:
                    self._parent.normalize_wav_audio(wav_path)
                except Exception:
                    pass
                return wav_path

            return None

        except Exception as e:
            print(f"[arc-reactor] Audio transcode error: {e}")
            return None

    # ─── Window Management (called from JS drag handler) ───

    def move_window(self, x: int, y: int):
        """Update saved position after edge-snap (from JS)."""
        self._overlay.position = {'x': x, 'y': y}

    def snap_to_edge(self):
        """Called by JS after snapping; currently a no-op on Python side."""
        pass

    # ─── Console Integration ───

    def open_console(self):
        """Focus or show the main God's Eye tactical console window."""
        try:
            main_window = self._parent._window
            if main_window:
                main_window.show()
                main_window.restore()
                # On Linux, try to raise the window
                try:
                    main_window.on_top = True
                    time.sleep(0.1)
                    main_window.on_top = False
                except Exception:
                    pass
                print("[arc-reactor] Main console window focused")
        except Exception as e:
            print(f"[arc-reactor] Could not focus console: {e}")

    # ─── State Queries ───

    def get_state(self) -> dict:
        """Return current overlay state."""
        return {
            'expanded': self._overlay.is_expanded if self._overlay else True,
            'position': self._overlay.position if self._overlay else {'x': 0, 'y': 0},
            'edge': 'right',
            'ready': self._is_ready,
        }
