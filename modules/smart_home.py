# modules/smart_home.py
"""
Smart Home & IoT Controls Module for J.A.R.V.I.S..
Integrates Home Assistant REST API, local IoT protocols, and arrival macros
with persistent local state fallback.
"""

import os
import json
import urllib.request
import urllib.parse
import shutil
import subprocess
from typing import Dict, Any, Optional

SMART_HOME_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "smart_home_state.json")


class SmartHomeManager:
    """
    On-device Smart Home & IoT subsystem controller for J.A.R.V.I.S.
    Communicates with Home Assistant if available, with immediate offline fallback to local state.
    """

    def __init__(self, filepath: str = SMART_HOME_FILE):
        self.filepath = filepath
        self.hass_url = os.environ.get("HASS_URL", "").rstrip("/")
        self.hass_token = os.environ.get("HASS_TOKEN", "")
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            initial_state = {
                "lights": {
                    "state": "off",
                    "brightness": 100,
                    "color": "warm_cream"
                },
                "thermostat": {
                    "target_temp": 72,
                    "mode": "heat",
                    "current_temp": 68
                },
                "locks": {
                    "front_door": "locked",
                    "back_door": "locked"
                },
                "arrival_routine": "active"
            }
            self._save(initial_state)

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, state: Dict[str, Any]):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[smart_home] Error saving smart home state: {e}")

    def _call_hass_service(self, domain: str, service: str, payload: Dict[str, Any]) -> bool:
        """Invokes a Home Assistant service via REST API if configured."""
        if not (self.hass_url and self.hass_token):
            return False

        try:
            endpoint = f"{self.hass_url}/api/services/{domain}/{service}"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.hass_token}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status in (200, 201)
        except Exception:
            return False

    def dispatch_desktop_notification(self, title: str, message: str):
        """Dispatches an asynchronous native Linux desktop notification for smart home events."""
        if shutil.which("notify-send"):
            try:
                subprocess.Popen(
                    ["notify-send", "-a", "J.A.R.V.I.S.", "-i", "weather-clear-night", title, message],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def set_light_state(self, on: bool, brightness: int = 100) -> str:
        state = self._load()
        state.setdefault("lights", {})["state"] = "on" if on else "off"
        state["lights"]["brightness"] = brightness
        self._save(state)

        # Dispatch to Home Assistant if online
        service = "turn_on" if on else "turn_off"
        payload = {"brightness_pct": brightness} if on else {}
        self._call_hass_service("light", service, payload)

        status = f"turned {'ON' if on else 'OFF'} (brightness: {brightness}%)"
        return f"Lights {status}, Sir."

    def set_thermostat(self, temp: int) -> str:
        state = self._load()
        state.setdefault("thermostat", {})["target_temp"] = temp
        state["thermostat"]["current_temp"] = temp
        self._save(state)

        # Dispatch to Home Assistant if online
        self._call_hass_service("climate", "set_temperature", {"temperature": temp})

        return f"Thermostat adjusted to {temp}°F, Sir."

    def set_lock_state(self, lock_door: bool) -> str:
        state = self._load()
        lock_val = "locked" if lock_door else "unlocked"
        state.setdefault("locks", {})["front_door"] = lock_val
        self._save(state)

        # Dispatch to Home Assistant if online
        service = "lock" if lock_door else "unlock"
        self._call_hass_service("lock", service, {})

        if lock_door:
            return "Perimeter secured. The front entrance has been locked, Sir."
        else:
            return "Front entrance unlocked, Sir."

    def handle_arrival(self) -> str:
        """Arrival routine triggered by arrival commands."""
        self.set_light_state(on=True, brightness=100)
        self.set_thermostat(72)
        self.set_lock_state(lock_door=False)
        self.dispatch_desktop_notification("Arrival Protocol", "Welcome home, Sir. Systems active.")
        return "Welcome home, Sir. Adjusting environment to arrival protocol: thermostat set to 72°F, illumination enabled, and entrance unlocked."
