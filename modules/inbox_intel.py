# modules/inbox_intel.py
"""
Inbox & Messaging Intel Scanner Module for J.A.R.V.I.S..
Provides real Maildir & local .eml parsing, optional IMAP checking, priority alert
filtering (server downtime, flight changes, security warnings), native Linux notifications,
and concise J.A.R.V.I.S. executive summaries.
"""

import os
import json
import time
import email
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from email import policy
from email.parser import BytesParser
from typing import List, Dict, Any, Optional

INBOX_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "inbox_data.json")

COMMON_MAIL_PATHS = [
    Path.home() / "Maildir" / "new",
    Path.home() / "Mail" / "inbox",
    Path.home() / ".local" / "share" / "mail",
    Path(__file__).parent.parent / "data" / "inbox"
]

URGENT_KEYWORDS = [
    "flight delay", "canceled", "cancelled", "operations", "we need to talk",
    "urgent", "critical", "emergency", "server down", "asap", "deadline",
    "security alert", "token exposed", "incident", "production", "outage"
]


class InboxIntelManager:
    """
    On-device communications scanner for J.A.R.V.I.S.
    Monitors local mail stores, parses urgent alerts, and dispatches desktop notifications.
    """

    def __init__(self, filepath: str = INBOX_FILE):
        self.filepath = filepath
        self._ensure_storage()
        self._scan_local_maildir()
        self._check_optional_imap()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            initial_inbox = [
                {
                    "id": "msg_101",
                    "sender": "Operations Lead <operations@hellhound.org>",
                    "subject": "Executive Briefing - Q3 Operations",
                    "snippet": "Sir, urgent update: all system telemetry nodes are synchronized and ready for review.",
                    "date": now_str,
                    "unread": True,
                    "urgent": True
                },
                {
                    "id": "msg_102",
                    "sender": "Flight Operations <alerts@delta.com>",
                    "subject": "Flight Delay Notification: FL 842 to NYC",
                    "snippet": "Your scheduled flight FL 842 has been delayed by 1 hour and 45 minutes due to severe weather.",
                    "date": now_str,
                    "unread": True,
                    "urgent": True
                },
                {
                    "id": "msg_103",
                    "sender": "Security Subsystem <security@hellhound.org>",
                    "subject": "Security Alert: Secret token detected in commit",
                    "snippet": "Automated scanner identified an unencrypted key signature in repository jarvis-core. Revocation advised.",
                    "date": now_str,
                    "unread": True,
                    "urgent": True
                },
                {
                    "id": "msg_104",
                    "sender": "Research Engineering <updates@hellhound.org>",
                    "subject": "Neural model weights compiled",
                    "snippet": "Local quantization pipeline finished processing weights with 99.4% precision retention.",
                    "date": now_str,
                    "unread": False,
                    "urgent": False
                }
            ]
            self._save(initial_inbox)

    def _scan_local_maildir(self):
        """Scans local Maildir paths and imports genuine .eml messages."""
        search_dirs = list(COMMON_MAIL_PATHS)
        custom_mail = os.environ.get("JARVIS_MAILDIR_PATH")
        if custom_mail:
            search_dirs.insert(0, Path(custom_mail))

        found_msgs = []
        for sdir in search_dirs:
            if not sdir.exists() or not sdir.is_dir():
                continue
            try:
                for mail_file in list(sdir.glob("*"))[:10]:
                    if mail_file.is_file():
                        parsed = self._parse_eml_file(mail_file)
                        if parsed:
                            found_msgs.append(parsed)
            except Exception:
                continue

        if found_msgs:
            messages = self._load()
            existing_ids = {m.get("id") for m in messages}
            new_msgs = [m for m in found_msgs if m.get("id") not in existing_ids]
            if new_msgs:
                for m in new_msgs:
                    messages.insert(0, m)
                self._save(messages)

    def _parse_eml_file(self, fpath: Path) -> Optional[Dict[str, Any]]:
        """Parses a local RFC 822 email file."""
        try:
            with open(fpath, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)
            sender = msg.get("From", "Unknown Sender")
            subject = msg.get("Subject", "(No Subject)")
            date_header = msg.get("Date", "")
            
            # Extract plain text body preview
            body_preview = ""
            body_part = msg.get_body(preferencelist=('plain', 'html'))
            if body_part:
                body_preview = body_part.get_content()[:250].replace("\n", " ").strip()

            is_urgent = any(kw in f"{subject} {body_preview}".lower() for kw in URGENT_KEYWORDS)

            return {
                "id": f"mail_{fpath.stem}",
                "sender": sender,
                "subject": subject,
                "snippet": body_preview or subject,
                "date": date_header or datetime.now().strftime("%Y-%m-%d %H:%M"),
                "unread": True,
                "urgent": is_urgent,
                "source": "maildir"
            }
        except Exception:
            return None

    def _check_optional_imap(self):
        """Optional IMAP server query if IMAP credentials are configured in environment."""
        imap_server = os.environ.get("IMAP_SERVER")
        imap_user = os.environ.get("IMAP_USER")
        imap_pass = os.environ.get("IMAP_PASSWORD")

        if not (imap_server and imap_user and imap_pass):
            return

        import imaplib
        try:
            client = imaplib.IMAP4_SSL(imap_server, timeout=5)
            client.login(imap_user, imap_pass)
            client.select("INBOX", readonly=True)
            status, response = client.search(None, 'UNSEEN')
            if status == "OK" and response[0]:
                msg_ids = response[0].split()
                messages = self._load()
                existing_ids = {m.get("id") for m in messages}
                for mid in msg_ids[-5:]:
                    res, data = client.fetch(mid, '(RFC822.HEADER)')
                    if res == "OK":
                        raw_header = data[0][1]
                        header_msg = email.message_from_bytes(raw_header)
                        subj = header_msg.get("Subject", "")
                        snd = header_msg.get("From", "")
                        ext_id = f"imap_{mid.decode('utf-8')}"
                        if ext_id not in existing_ids:
                            is_urg = any(kw in subj.lower() for kw in URGENT_KEYWORDS)
                            messages.insert(0, {
                                "id": ext_id,
                                "sender": snd,
                                "subject": subj,
                                "snippet": f"Unread message from {snd}",
                                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "unread": True,
                                "urgent": is_urg,
                                "source": "imap"
                            })
                self._save(messages)
            client.logout()
        except Exception:
            pass

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

    def dispatch_desktop_notification(self, title: str, message: str, urgency: str = "critical"):
        """Dispatches an asynchronous native Linux desktop notification for urgent communications."""
        if shutil.which("notify-send"):
            try:
                subprocess.Popen(
                    ["notify-send", "-a", "J.A.R.V.I.S.", "-u", urgency, "-i", "mail-unread", title, message],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

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

    def receive_incoming_message(self, sender: str, subject: str, snippet: str, urgent: bool = False):
        """Records an incoming message, checks urgency, and dispatches native desktop alert."""
        messages = self._load()
        msg_id = f"msg_{int(time.time())}"
        is_urg = urgent or any(kw in f"{subject} {snippet}".lower() for kw in URGENT_KEYWORDS)
        new_msg = {
            "id": msg_id,
            "sender": sender,
            "subject": subject,
            "snippet": snippet,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "unread": True,
            "urgent": is_urg
        }
        messages.insert(0, new_msg)
        self._save(messages)

        if is_urg:
            self.dispatch_desktop_notification(f"Urgent Message: {sender}", subject)

    add_mock_email = receive_incoming_message  # Backward compatibility alias

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
