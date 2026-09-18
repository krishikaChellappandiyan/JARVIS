# modules/reminder_service.py
"""
Proactive Natural-Language Reminder & Countdown Timer Engine for J.A.R.V.I.S.
Allows the operator to set timers and reminders via voice or text:
  - "remind me in 10 minutes to check the server"
  - "set a timer for 5 minutes"
  - "timer 45 seconds"
  - "remind me at 4:30 pm to call the team"
  - "list my active reminders"
  - "cancel timer"

Triggers persistent desktop notifications (notify-send), EventBus alerts,
and spoken audio alerts ("Sir, your reminder for 'check the server' is due.").
"""

import os
import re
import json
import time
import uuid
import shutil
import subprocess
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Callable

REMINDERS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "reminders.json"
)


class ReminderService:
    """
    Background timer and proactive reminder service for J.A.R.V.I.S.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = ReminderService()
            return cls._instance

    def __init__(self, storage_path: str = REMINDERS_FILE, voice_notifier: Optional[Callable[[str], None]] = None):
        self.storage_path = storage_path
        self.voice_notifier = voice_notifier
        self.reminders: List[Dict[str, Any]] = []
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._ensure_storage()
        self._load()
        self.start()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.reminders = json.load(f)
            except Exception:
                self.reminders = []
        else:
            self.reminders = []

    def _save(self):
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.reminders, f, indent=2)
        except Exception:
            pass

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        self._running = False

    def _monitor_loop(self):
        """Background checker waking every second to fire matured timers."""
        while self._running:
            now = time.time()
            matured = []
            with self._lock:
                for rem in self.reminders:
                    if rem.get("status") == "active" and now >= rem.get("target_epoch", 0):
                        rem["status"] = "triggered"
                        rem["triggered_at"] = now
                        matured.append(dict(rem))
                if matured:
                    self._save()

            for rem in matured:
                self._dispatch_alert(rem)

            time.sleep(1.0)

    def _dispatch_alert(self, rem: Dict[str, Any]):
        """Trigger desktop notification, sound chime, voice alert, and event bus broadcast."""
        label = rem.get("label", "Timer")
        is_timer = rem.get("is_timer", False)
        if is_timer:
            title = "J.A.R.V.I.S. Timer Expired"
            msg = f"Sir, your timer for '{label}' has reached zero."
        else:
            title = "J.A.R.V.I.S. Reminder"
            msg = f"Sir, reminder: {label}."

        # 1. Native Linux Desktop Notification
        if shutil.which("notify-send"):
            try:
                subprocess.Popen([
                    "notify-send",
                    "-u", "critical",
                    "-i", "alarm",
                    title,
                    msg
                ])
            except Exception:
                pass

        # 2. Audible notification (system bell or sound)
        try:
            print(f"\a\n[J.A.R.V.I.S. ALERT] 🔔 {title.upper()}: {msg}\n")
        except Exception:
            pass

        # 3. Spoken voice alert if notifier is configured
        if self.voice_notifier and callable(self.voice_notifier):
            try:
                self.voice_notifier(msg)
            except Exception as e:
                print(f"[reminder_service] Voice notify error: {e}")

        # 4. Broadcast via EventBus if available
        try:
            from core.event_bus import get_event_bus
            bus = get_event_bus()
            bus.emit("jarvis_reminder_alert", {
                "reminder": rem,
                "title": title,
                "spoken_text": msg
            })
        except Exception:
            pass

    # ── Natural Language Parsing ───────────────────────────────

    @staticmethod
    def parse_time_and_label(text: str) -> Tuple[Optional[float], Optional[str], bool]:
        """
        Parses relative or absolute time offsets from user speech or text.
        Returns (target_epoch, label, is_timer).
        """
        text_lower = text.lower().strip()
        now = time.time()
        dt_now = datetime.now()

        # Check if it's explicitly a timer or reminder
        is_timer = "timer" in text_lower

        # 1. Check relative duration ("in 5 minutes", "in 30 seconds", "for 10 minutes")
        total_seconds = 0
        found_duration = False

        # Match hours
        m_hrs = re.search(r'(\d+)\s*(?:hours?|hrs?)\b', text_lower)
        if m_hrs:
            total_seconds += int(m_hrs.group(1)) * 3600
            found_duration = True

        # Match minutes
        m_mins = re.search(r'(\d+)\s*(?:minutes?|mins?|m)\b', text_lower)
        if m_mins:
            total_seconds += int(m_mins.group(1)) * 60
            found_duration = True

        # Match seconds
        m_secs = re.search(r'(\d+)\s*(?:seconds?|secs?|s)\b', text_lower)
        if m_secs:
            total_seconds += int(m_secs.group(1))
            found_duration = True

        if found_duration and total_seconds > 0:
            target_epoch = now + total_seconds

            # Extract label: strip timer/reminder prefixes and duration clauses
            label = text_lower
            label = re.sub(r'^(?:jarvis\s+)?(?:please\s+)?(?:set\s+(?:a\s+)?)?(?:timer|reminder)\s+(?:for\s+)?', '', label).strip()
            label = re.sub(r'^remind\s+me\s+(?:to\s+)?', '', label).strip()
            label = re.sub(r'\bin\s+\d+\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|and|\s)*', '', label).strip()
            label = re.sub(r'\bfor\s+\d+\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|and|\s)*', '', label).strip()
            label = re.sub(r'^\d+\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|and|\s)*', '', label).strip()
            label = re.sub(r'^(?:to\s+)?', '', label).strip()
            label = re.sub(r'^(?:for\s+)?', '', label).strip()

            if not label:
                label = f"{total_seconds // 60}m timer" if total_seconds >= 60 else f"{total_seconds}s timer"

            return target_epoch, label.capitalize(), is_timer

        # 2. Check absolute time ("at 4:30 pm", "at 18:00", "at 9 am")
        m_abs = re.search(r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', text_lower)
        if m_abs:
            hour = int(m_abs.group(1))
            minute = int(m_abs.group(2)) if m_abs.group(2) else 0
            meridiem = m_abs.group(3)

            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0

            target_dt = dt_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_dt <= dt_now:
                target_dt += timedelta(days=1)

            target_epoch = target_dt.timestamp()

            label = text_lower
            label = re.sub(r'^(?:jarvis\s+)?(?:please\s+)?(?:remind\s+me\s+(?:to\s+)?)?', '', label).strip()
            label = re.sub(r'\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*', '', label).strip()
            label = re.sub(r'^(?:to\s+)?', '', label).strip()

            if not label:
                label = f"Appointment at {hour:02d}:{minute:02d}"

            return target_epoch, label.capitalize(), False

        return None, None, False

    # ── CRUD Operations ────────────────────────────────────────

    def add_timer(self, seconds: int, label: str = "Timer") -> Dict[str, Any]:
        """Create a countdown timer."""
        now = time.time()
        rem_id = f"tmr_{uuid.uuid4().hex[:6]}"
        item = {
            "id": rem_id,
            "label": label,
            "created_at": now,
            "target_epoch": now + max(1, seconds),
            "duration_sec": max(1, seconds),
            "status": "active",
            "is_timer": True
        }
        with self._lock:
            self.reminders.append(item)
            self._save()
        return item

    def add_reminder(self, target_epoch: float, label: str) -> Dict[str, Any]:
        """Create a scheduled reminder."""
        now = time.time()
        rem_id = f"rem_{uuid.uuid4().hex[:6]}"
        item = {
            "id": rem_id,
            "label": label,
            "created_at": now,
            "target_epoch": target_epoch,
            "duration_sec": max(1, int(target_epoch - now)),
            "status": "active",
            "is_timer": False
        }
        with self._lock:
            self.reminders.append(item)
            self._save()
        return item

    def get_active(self) -> List[Dict[str, Any]]:
        """Return list of all currently ticking timers and reminders."""
        now = time.time()
        active = []
        with self._lock:
            for r in self.reminders:
                if r.get("status") == "active":
                    rem_copy = dict(r)
                    rem_copy["remaining_sec"] = max(0, int(r.get("target_epoch", 0) - now))
                    active.append(rem_copy)
        active.sort(key=lambda x: x.get("target_epoch", 0))
        return active

    def cancel(self, reminder_id: Optional[str] = None) -> bool:
        """Cancel a reminder by ID, or cancel the latest active timer if ID is None."""
        with self._lock:
            if reminder_id:
                for r in self.reminders:
                    if r.get("id") == reminder_id and r.get("status") == "active":
                        r["status"] = "cancelled"
                        self._save()
                        return True
            else:
                active = [r for r in self.reminders if r.get("status") == "active"]
                if active:
                    active[-1]["status"] = "cancelled"
                    self._save()
                    return True
        return False

    def clear_all(self):
        """Cancel all active timers."""
        with self._lock:
            for r in self.reminders:
                if r.get("status") == "active":
                    r["status"] = "cancelled"
            self._save()
