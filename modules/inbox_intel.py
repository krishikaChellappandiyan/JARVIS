# modules/inbox_intel.py
# MOCK — not wired to a real API
"""
Read-Only Inbox & Messaging Scanner Module for J.A.R.V.I.S..
Scans inbox for urgent messages (flight delays, boss panic texts, "WE NEED TO TALK", critical alerts)
and provides instant J.A.R.V.I.S. TL;DR summaries.
"""

import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any

INBOX_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "inbox_data.json")

URGENT_KEYWORDS = [
    "flight delay", "canceled", "cancelled", "boss", "we need to talk",
    "urgent", "critical", "emergency", "server down", "asap", "deadline", "security alert"
]


class InboxIntelManager:
    def __init__(self, filepath: str = INBOX_FILE):
        self.filepath = filepath
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            initial_inbox = [
                {
                    "id": "msg_101",
                    "sender": "Operations Lead <operations@hellhound.org>",
                    "subject": "Executive Briefing - Q3 Operations",
                    "snippet": "Sir, urgent update: all system telemetry nodes are synchronized and ready for the 4 PM review.",
                    "date": now_str,
                    "unread": True,
                    "urgent": True
                },
                {
                    "id": "msg_102",
                    "sender": "Delta Air Lines <alerts@delta.com>",
                    "subject": "Flight Delay Notification: FL 842 to NYC",
                    "snippet": "Your flight FL 842 has been delayed by 1 hour and 45 minutes due to severe weather.",
                    "date": now_str,
                    "unread": True,
                    "urgent": True
                },
                {
                    "id": "msg_103",
                    "sender": "GitHub Security <no-reply@github.com>",
                    "subject": "Security Alert: Secret token detected in commit",
                    "snippet": "We detected an exposed API token in repository jarvis-core. Immediate revocation recommended.",
                    "date": now_str,
                    "unread": True,
                    "urgent": True
                },
                {
                    "id": "msg_104",
                    "sender": "Coffee Club <newsletter@coffeeroasters.io>",
                    "subject": "Your weekly espresso roast choice is ready",
                    "snippet": "Discover our latest Ethiopian roast blend available now in stores.",
                    "date": now_str,
                    "unread": False,
                    "urgent": False
                }
            ]
            self._save(initial_inbox)

    def _load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, messages: List[Dict[str, Any]]):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=2)
        except Exception as e:
            print(f"[inbox_intel] Error saving inbox: {e}")

    def scan_urgent(self) -> List[Dict[str, Any]]:
        """Scan inbox for urgent or unread messages matching critical keywords."""
        messages = self._load()
        urgent_msgs = []
        for m in messages:
            if m.get("urgent"):
                urgent_msgs.append(m)
                continue
            subj_body = f"{m.get('subject', '')} {m.get('snippet', '')}".lower()
            if any(kw in subj_body for kw in URGENT_KEYWORDS):
                m["urgent"] = True
                urgent_msgs.append(m)
        return urgent_msgs

    def search_inbox(self, query: str) -> List[Dict[str, Any]]:
        messages = self._load()
        q_lower = query.lower()
        results = []
        for m in messages:
            if (q_lower in m.get("subject", "").lower() or
                q_lower in m.get("snippet", "").lower() or
                q_lower in m.get("sender", "").lower()):
                results.append(m)
        return results

    def add_mock_email(self, sender: str, subject: str, snippet: str, urgent: bool = False):
        messages = self._load()
        msg_id = f"msg_{int(time.time())}"
        new_msg = {
            "id": msg_id,
            "sender": sender,
            "subject": subject,
            "snippet": snippet,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "unread": True,
            "urgent": urgent or any(kw in (subject + " " + snippet).lower() for kw in URGENT_KEYWORDS)
        }
        messages.insert(0, new_msg)
        self._save(messages)

    def get_tldr_summary(self) -> str:
        """Generate an articulate J.A.R.V.I.S. briefing of urgent inbox items."""
        urgent = self.scan_urgent()
        if not urgent:
            return "Your inbox is clear of urgent communications at present, Sir."

        lines = [f"Sir, I have flagged {len(urgent)} high-priority item(s) requiring your attention:"]
        for m in urgent[:3]:
            sender_name = m.get("sender", "Unknown").split("<")[0].strip()
            subj = m.get("subject", "")
            snippet = m.get("snippet", "")
            lines.append(f"• From {sender_name}: '{subj}' — {snippet}")

        return "\n".join(lines)
