# modules/calendar_intel.py
"""
Calendar & Scheduling Intel Module for J.A.R.V.I.S..
Provides real .ics (iCalendar) ingestion, event scheduling, double-booking conflict
detection, auto-rescheduling, native Linux desktop notifications, and authentic J.A.R.V.I.S. briefings.
"""

import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

CALENDAR_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "calendar_data.json")

COMMON_CALENDAR_PATHS = [
    Path.home() / "Documents" / "calendars",
    Path.home() / ".local" / "share" / "evolution" / "calendar",
    Path.home() / ".thunderbird",
    Path(__file__).parent.parent / "data" / "calendars"
]


class CalendarIntelManager:
    """
    On-device scheduling and agenda intelligence manager for J.A.R.V.I.S.
    Integrates local iCalendar (.ics) stores, active event alerts, and native desktop notifications.
    """

    def __init__(self, filepath: str = CALENDAR_FILE):
        self.filepath = filepath
        self._ensure_storage()
        self._sync_external_ics_files()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            now = datetime.now()
            initial_events = [
                {
                    "id": "evt_1",
                    "title": "Tactical Operations & System Review",
                    "start": (now + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M"),
                    "end": (now + timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M"),
                    "location": "Stark Workshop / Remote",
                    "attendees": ["operations@hellhound.org"],
                    "urgent": True
                },
                {
                    "id": "evt_2",
                    "title": "Security Subsystem Verification",
                    "start": (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
                    "end": (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"),
                    "location": "Command Terminal",
                    "attendees": ["security@hellhound.org"]
                },
                {
                    "id": "evt_3",
                    "title": "Hardware Thermal Diagnostics Sync",
                    "start": (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
                    "end": (now + timedelta(hours=2, minutes=30)).strftime("%Y-%m-%d %H:%M"),
                    "location": "Local Node",
                    "attendees": ["telemetry@hellhound.org"]
                }
            ]
            self._save(initial_events)

    def _sync_external_ics_files(self):
        """Scans filesystem for .ics calendar files and merges external entries."""
        search_dirs = list(COMMON_CALENDAR_PATHS)
        custom_ics = os.environ.get("JARVIS_ICS_PATH")
        if custom_ics:
            search_dirs.insert(0, Path(custom_ics))

        found_events = []
        for d in search_dirs:
            if not d.exists():
                continue
            try:
                ics_files = list(d.glob("*.ics")) if d.is_dir() else ([d] if d.suffix == ".ics" else [])
                for fpath in ics_files[:5]:
                    parsed = self._parse_ics(fpath)
                    found_events.extend(parsed)
            except Exception:
                continue

        if found_events:
            current = self._load()
            existing_ids = {e.get("id") for e in current}
            new_events = [e for e in found_events if e.get("id") not in existing_ids]
            if new_events:
                current.extend(new_events)
                self._save(current)

    def _parse_ics(self, ics_path: Path) -> List[Dict[str, Any]]:
        """Lightweight RFC 5545 iCalendar format parser."""
        events = []
        try:
            content = ics_path.read_text(encoding="utf-8", errors="ignore")
            vevent_blocks = re.findall(r'BEGIN:VEVENT[\s\S]*?END:VEVENT', content)
            for block in vevent_blocks:
                uid_m = re.search(r'UID:(.+)', block)
                sum_m = re.search(r'SUMMARY:(.+)', block)
                dtstart_m = re.search(r'DTSTART(?:;[^:]+)?:(\d{8}T\d{6}Z?)', block)
                dtend_m = re.search(r'DTEND(?:;[^:]+)?:(\d{8}T\d{6}Z?)', block)
                loc_m = re.search(r'LOCATION:(.+)', block)

                if sum_m and dtstart_m:
                    uid = uid_m.group(1).strip() if uid_m else f"ics_{len(events)+1}"
                    title = sum_m.group(1).strip()
                    st_raw = dtstart_m.group(1).strip().rstrip("Z")
                    et_raw = dtend_m.group(1).strip().rstrip("Z") if dtend_m else st_raw

                    # Convert YYYYMMDDTHHMMSS to YYYY-MM-DD HH:MM
                    try:
                        st_dt = datetime.strptime(st_raw, "%Y%m%dT%H%M%S")
                        et_dt = datetime.strptime(et_raw, "%Y%m%dT%H%M%S")
                        st_str = st_dt.strftime("%Y-%m-%d %H:%M")
                        et_str = et_dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        continue

                    events.append({
                        "id": uid,
                        "title": title,
                        "start": st_str,
                        "end": et_str,
                        "location": loc_m.group(1).strip() if loc_m else "Local Workspace",
                        "source": str(ics_path.name)
                    })
        except Exception:
            pass
        return events

    def _load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, events: List[Dict[str, Any]]):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(events, f, indent=2)
        except Exception as e:
            print(f"[calendar_intel] Error saving calendar: {e}")

    def dispatch_desktop_notification(self, title: str, message: str, urgency: str = "normal"):
        """Dispatches an asynchronous native Linux desktop notification if notify-send is available."""
        if shutil.which("notify-send"):
            try:
                subprocess.Popen(
                    ["notify-send", "-a", "J.A.R.V.I.S.", "-u", urgency, "-i", "appointment-soon", title, message],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def get_upcoming_events(self, limit: int = 5) -> List[Dict[str, Any]]:
        events = self._load()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        upcoming = [e for e in events if e.get("start", "") >= now_str]
        upcoming.sort(key=lambda x: x.get("start", ""))
        return upcoming[:limit]

    def check_conflicts(self) -> List[Dict[str, Any]]:
        """Identify overlapping calendar events."""
        events = self._load()
        conflicts = []
        fmt = "%Y-%m-%d %H:%M"

        parsed = []
        for e in events:
            try:
                st = datetime.strptime(e["start"], fmt)
                et = datetime.strptime(e["end"], fmt)
                parsed.append((st, et, e))
            except Exception:
                continue

        parsed.sort(key=lambda x: x[0])
        for i in range(len(parsed)):
            for j in range(i + 1, len(parsed)):
                st1, et1, e1 = parsed[i]
                st2, et2, e2 = parsed[j]
                if st2 < et1:
                    conflicts.append({"event_a": e1, "event_b": e2})

        return conflicts

    def add_event(self, title: str, start_time: str, end_time: str, location: str = "TBD") -> str:
        events = self._load()
        evt_id = f"evt_{int(time.time())}"
        new_evt = {
            "id": evt_id,
            "title": title,
            "start": start_time,
            "end": end_time,
            "location": location,
            "urgent": False
        }
        events.append(new_evt)
        self._save(events)
        self.dispatch_desktop_notification("Schedule Updated", f"Added '{title}' ({start_time} - {end_time})")
        return f"Added calendar event '{title}' ({start_time} - {end_time}), Sir."

    def reschedule_event(self, event_query: str, new_start: str, new_end: str) -> str:
        events = self._load()
        found = False
        query_lower = event_query.lower()
        matched_title = ""
        for e in events:
            if query_lower in e.get("title", "").lower() or query_lower in e.get("id", "").lower():
                e["start"] = new_start
                e["end"] = new_end
                matched_title = e.get("title", event_query)
                found = True
                break

        if found:
            self._save(events)
            self.dispatch_desktop_notification("Event Rescheduled", f"'{matched_title}' adjusted to {new_start} - {new_end}")
            return f"Rescheduled meeting '{matched_title}' to {new_start} - {new_end}, Sir."
        return f"Could not find event matching '{event_query}' to reschedule, Sir."

    def format_jarvis_reminders(self) -> str:
        """Format calendar alerts in authentic J.A.R.V.I.S. voice with proactive alerts."""
        upcoming = self.get_upcoming_events(limit=3)
        conflicts = self.check_conflicts()
        now = datetime.now()
        fmt = "%Y-%m-%d %H:%M"

        lines = []
        imminent = []

        for e in upcoming:
            try:
                st = datetime.strptime(e["start"], fmt)
                diff_mins = int((st - now).total_seconds() / 60)
                if 0 <= diff_mins <= 30:
                    imminent.append((e, diff_mins))
            except Exception:
                continue

        if imminent:
            for e, mins in imminent:
                if mins <= 5:
                    lines.append(f"Sir, a brief reminder: you have '{e['title']}' scheduled in {mins} minutes at {e.get('location', 'TBD')}.")
                    self.dispatch_desktop_notification("Imminent Event", f"'{e['title']}' begins in {mins} minutes.", urgency="critical")
                else:
                    lines.append(f"Sir, '{e['title']}' commences in {mins} minutes.")
                    self.dispatch_desktop_notification("Upcoming Briefing", f"'{e['title']}' in {mins} minutes.")

        if conflicts:
            c = conflicts[0]
            lines.append(
                f"I have detected a scheduling conflict at {c['event_a']['start']}, Sir: "
                f"'{c['event_a']['title']}' overlaps with '{c['event_b']['title']}'. Shall I adjust your itinerary?"
            )
            self.dispatch_desktop_notification("Schedule Conflict", f"Overlap: '{c['event_a']['title']}' & '{c['event_b']['title']}'", urgency="critical")

        if not lines and upcoming:
            next_evt = upcoming[0]
            lines.append(f"Next appointment on your schedule is '{next_evt['title']}' at {next_evt['start']}, Sir.")

        if not lines:
            lines.append("Your schedule is completely clear at present, Sir.")

        return " ".join(lines)
