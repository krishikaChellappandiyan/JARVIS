"""
J.A.R.V.I.S. Desktop Operating System Controller & Agency Engine ("System Agency").

Provides real-system OS skills:
1. Audio & Media Controls (Volume adjustment, mute toggle, playback control via ALSA/Pulse/media keys).
2. Clipboard Intelligence (Read, write, and summarize active system clipboard).
3. Process Management & Safe Termination (Top CPU/RAM processes, target process termination with safety guards).
4. Workstation Session Controls (Lock workstation, brightness management).
5. Git Repository & Project Telemetry (Branch inspection, uncommitted changes, status debrief).
"""

import os
import re
import sys
import shutil
import psutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


class SystemController:
    """
    On-device operating system agency manager for J.A.R.V.I.S.
    """

    PROTECTED_PROCESSES = {
        "systemd", "init", "kthreadd", "Xorg", "Xwayland", "xfwm4", "xfce4-session",
        "gnome-shell", "dbus-daemon", "pulseaudio", "pipewire", "bash", "sh", "login"
    }

    def __init__(self, default_repo_path: Optional[str] = None):
        self.repo_path = default_repo_path or str(Path(__file__).parent.parent.resolve())
        self._software_volume = 70
        self._software_muted = False
        self._software_clipboard = ""

    # ── 1. Audio & Media Agency ───────────────────────────────────────

    def get_volume(self) -> Dict[str, Any]:
        """
        Query current system audio volume and mute status.
        Tries amixer, then pactl, falling back to tracked state.
        """
        # Try amixer
        if shutil.which("amixer"):
            try:
                proc = subprocess.run(
                    ["amixer", "sget", "Master"],
                    capture_output=True, text=True, timeout=1.5
                )
                if proc.returncode == 0 and proc.stdout:
                    m_vol = re.search(r'\[(\d+)%\]', proc.stdout)
                    m_mute = re.search(r'\[(on|off)\]', proc.stdout)
                    if m_vol:
                        vol = int(m_vol.group(1))
                        muted = (m_mute.group(1) == "off") if m_mute else False
                        self._software_volume = vol
                        self._software_muted = muted
                        return {"volume": vol, "muted": muted, "backend": "amixer"}
            except Exception:
                pass

        # Try pactl
        if shutil.which("pactl"):
            try:
                proc = subprocess.run(
                    ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                    capture_output=True, text=True, timeout=1.5
                )
                if proc.returncode == 0 and proc.stdout:
                    m_vol = re.search(r'(\d+)%', proc.stdout)
                    if m_vol:
                        vol = int(m_vol.group(1))
                        self._software_volume = vol
                        return {"volume": vol, "muted": self._software_muted, "backend": "pactl"}
            except Exception:
                pass

        return {"volume": self._software_volume, "muted": self._software_muted, "backend": "software"}

    def set_volume(self, percent: int) -> Dict[str, Any]:
        """
        Adjust system audio volume (0-100%).
        """
        target = max(0, min(100, int(percent)))
        self._software_volume = target
        backend_used = "software"
        success = True

        if shutil.which("amixer"):
            try:
                subprocess.run(
                    ["amixer", "sset", "Master", f"{target}%"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0
                )
                backend_used = "amixer"
            except Exception:
                pass

        if backend_used == "software" and shutil.which("pactl"):
            try:
                subprocess.run(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{target}%"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0
                )
                backend_used = "pactl"
            except Exception:
                pass

        debrief = f"Audio output adjusted to {target}%, Sir."
        return {"success": success, "volume": target, "backend": backend_used, "debrief": debrief}

    def adjust_volume(self, delta: int) -> Dict[str, Any]:
        """
        Increase or decrease volume by a delta (e.g. +10 or -10).
        """
        curr = self.get_volume().get("volume", self._software_volume)
        return self.set_volume(curr + delta)

    def mute(self, mute_state: bool = True) -> Dict[str, Any]:
        """
        Toggle or set mute state.
        """
        self._software_muted = mute_state
        state_str = "mute" if mute_state else "unmute"
        backend = "software"

        if shutil.which("amixer"):
            try:
                subprocess.run(
                    ["amixer", "sset", "Master", state_str],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0
                )
                backend = "amixer"
            except Exception:
                pass

        if backend == "software" and shutil.which("pactl"):
            try:
                val = "1" if mute_state else "0"
                subprocess.run(
                    ["pactl", "set-sink-mute", "@DEFAULT_SINK@", val],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0
                )
                backend = "pactl"
            except Exception:
                pass

        debrief = "Audio muted, Sir." if mute_state else "Audio unmuted, Sir."
        return {"success": True, "muted": mute_state, "backend": backend, "debrief": debrief}

    def media_control(self, action: str) -> Dict[str, Any]:
        """
        Control system media playback (play, pause, play_pause, next, prev, stop).
        """
        act = action.lower().strip()
        alias_map = {
            "play": "play", "pause": "pause", "resume": "play", "stop": "stop",
            "next": "next", "previous": "previous", "prev": "previous",
            "toggle": "play-pause", "play_pause": "play-pause"
        }
        playerctl_act = alias_map.get(act, "play-pause")
        executed = False
        backend = "none"

        if shutil.which("playerctl"):
            try:
                subprocess.run(["playerctl", playerctl_act], timeout=1.5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                executed = True
                backend = "playerctl"
            except Exception:
                pass

        if not executed and shutil.which("xdotool"):
            key_map = {
                "play": "XF86AudioPlay", "pause": "XF86AudioPause", "play-pause": "XF86AudioPlay",
                "next": "XF86AudioNext", "previous": "XF86AudioPrev", "stop": "XF86AudioStop"
            }
            key = key_map.get(playerctl_act, "XF86AudioPlay")
            try:
                subprocess.run(["xdotool", "key", key], timeout=1.5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                executed = True
                backend = "xdotool"
            except Exception:
                pass

        debrief = f"Media command '{act}' dispatched to desktop playback controller, Sir."
        return {"success": executed, "action": act, "backend": backend, "debrief": debrief}

    # ── 2. Clipboard Agency ───────────────────────────────────────────

    def get_clipboard_text(self) -> str:
        """
        Read text from system clipboard.
        """
        if shutil.which("xclip"):
            try:
                proc = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, text=True, timeout=1.5
                )
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout
            except Exception:
                pass

        if shutil.which("xsel"):
            try:
                proc = subprocess.run(
                    ["xsel", "--clipboard", "--output"],
                    capture_output=True, text=True, timeout=1.5
                )
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout
            except Exception:
                pass

        if shutil.which("wl-paste"):
            try:
                proc = subprocess.run(
                    ["wl-paste"],
                    capture_output=True, text=True, timeout=1.5
                )
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout
            except Exception:
                pass

        return self._software_clipboard

    def set_clipboard_text(self, text: str) -> bool:
        """
        Write text to system clipboard.
        """
        self._software_clipboard = text
        success = False

        if shutil.which("xclip"):
            try:
                proc = subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text, text=True, timeout=1.5,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if proc.returncode == 0:
                    success = True
            except Exception:
                pass

        if not success and shutil.which("wl-copy"):
            try:
                proc = subprocess.run(
                    ["wl-copy"],
                    input=text, text=True, timeout=1.5,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if proc.returncode == 0:
                    success = True
            except Exception:
                pass

        return success or bool(self._software_clipboard)

    def summarize_clipboard(self) -> str:
        """
        Inspect and format an articulate Stark briefing of active clipboard contents.
        """
        content = self.get_clipboard_text().strip()
        if not content:
            return "Your clipboard is currently empty, Sir."

        char_count = len(content)
        lines = content.splitlines()
        line_count = len(lines)

        # Detect category
        if re.match(r'^https?://[^\s]+$', content):
            cat = "URL link"
            preview = content
        elif content.startswith("{") and content.endswith("}"):
            cat = "JSON structured payload"
            preview = content[:120].replace("\n", " ")
        elif re.search(r'(?:def\s+\w+|class\s+\w+|import\s+\w+|function\s+\w+|<div|const\s+\w+)', content):
            cat = "source code snippet"
            preview = lines[0][:80]
        else:
            cat = "text snippet"
            preview = lines[0][:80]

        debrief = (
            f"Clipboard contains a {cat} ({line_count} line{'s' if line_count != 1 else ''}, "
            f"{char_count} characters). Primary content reads: \"{preview}\", Sir."
        )
        return debrief

    # ── 3. Process Management & Safe Termination ──────────────────────

    def get_top_processes(self, limit: int = 5, by: str = "cpu") -> List[Dict[str, Any]]:
        """
        Return the top active processes sorted by CPU or memory usage.
        """
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                info = p.info
                if info['name']:
                    procs.append({
                        "pid": info['pid'],
                        "name": info['name'],
                        "cpu_percent": round(info['cpu_percent'] or 0.0, 1),
                        "memory_percent": round(info['memory_percent'] or 0.0, 1),
                        "status": info.get('status', 'running')
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        sort_key = "cpu_percent" if by.lower() == "cpu" else "memory_percent"
        procs.sort(key=lambda x: x[sort_key], reverse=True)
        return procs[:limit]

    def kill_process(self, target: str) -> Dict[str, Any]:
        """
        Safely terminate a rogue or requested process by PID or application name.
        Enforces strict safety barriers against critical OS processes.
        """
        target_clean = target.strip()
        if not target_clean:
            return {"success": False, "debrief": "No target process designated for termination, Sir."}

        # Check PID vs Name
        is_pid = target_clean.isdigit()
        target_pid = int(target_clean) if is_pid else None

        # Guard against terminating self or PID 0/1
        current_pid = os.getpid()
        if target_pid in (0, 1, current_pid):
            return {
                "success": False,
                "debrief": f"Termination request denied, Sir. PID {target_pid} is a protected core process."
            }

        # Guard against protected names
        if not is_pid and target_clean.lower() in self.PROTECTED_PROCESSES:
            return {
                "success": False,
                "debrief": f"Termination request refused, Sir. '{target_clean}' is a critical operating system component."
            }

        terminated = []
        errors = []

        for p in psutil.process_iter(['pid', 'name']):
            try:
                matches = False
                if is_pid and p.info['pid'] == target_pid:
                    matches = True
                elif not is_pid and target_clean.lower() in (p.info['name'] or '').lower():
                    matches = True

                if matches:
                    pname = p.info['name']
                    pid = p.info['pid']
                    if pname.lower() in self.PROTECTED_PROCESSES or pid == current_pid:
                        continue
                    p.terminate()
                    terminated.append(f"{pname} (PID {pid})")
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                errors.append(str(e))

        if terminated:
            debrief = f"Terminated {len(terminated)} process instances: {', '.join(terminated[:3])}, Sir."
            return {"success": True, "terminated": terminated, "debrief": debrief}
        else:
            debrief = f"No running processes matching '{target_clean}' could be safely terminated, Sir."
            return {"success": False, "terminated": [], "debrief": debrief}

    # ── 4. Workstation Session Controls ───────────────────────────────

    def lock_workstation(self) -> Dict[str, Any]:
        """
        Lock the active desktop session.
        """
        lock_cmds = [
            ["xflock4"],
            ["xdg-screensaver", "lock"],
            ["gnome-screensaver-command", "-l"],
            ["loginctl", "lock-session"]
        ]
        executed = False
        backend = "none"

        for cmd in lock_cmds:
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    executed = True
                    backend = cmd[0]
                    break
                except Exception:
                    continue

        debrief = "Workstation display session locked, Sir." if executed else "Could not invoke desktop lock binary, Sir."
        return {"success": executed, "backend": backend, "debrief": debrief}

    def set_brightness(self, percent: int) -> Dict[str, Any]:
        """
        Adjust monitor backlight brightness.
        """
        pct = max(5, min(100, int(percent)))
        executed = False
        backend = "none"

        if shutil.which("brightnessctl"):
            try:
                subprocess.run(
                    ["brightnessctl", "set", f"{pct}%"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0
                )
                executed = True
                backend = "brightnessctl"
            except Exception:
                pass

        debrief = f"Display backlight adjusted to {pct}%, Sir."
        return {"success": executed, "brightness": pct, "backend": backend, "debrief": debrief}

    # ── 5. Git Repository & Project Telemetry ─────────────────────────

    def get_git_status(self, repo_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Inspect current Git repository branch and working directory state.
        """
        target_dir = repo_path or self.repo_path
        if not os.path.exists(target_dir):
            return {"is_git": False, "error": "Target directory does not exist."}

        try:
            # 1. Branch and tracking info
            b_proc = subprocess.run(
                ["git", "status", "--porcelain=v1", "-b"],
                cwd=target_dir, capture_output=True, text=True, timeout=3.0
            )
            if b_proc.returncode != 0:
                return {"is_git": False, "error": "Directory is not a git repository."}

            lines = b_proc.stdout.strip().splitlines()
            branch = "unknown"
            ahead = 0
            behind = 0
            if lines and lines[0].startswith("##"):
                header = lines[0][3:].strip()
                m_branch = re.match(r'^([^.\s]+)', header)
                if m_branch:
                    branch = m_branch.group(1)
                m_ahead = re.search(r'ahead\s+(\d+)', header)
                m_behind = re.search(r'behind\s+(\d+)', header)
                if m_ahead:
                    ahead = int(m_ahead.group(1))
                if m_behind:
                    behind = int(m_behind.group(1))

            modified_files = []
            untracked_files = []
            staged_files = []

            for line in lines[1:]:
                if len(line) < 3:
                    continue
                code = line[:2]
                filename = line[3:].strip()
                if code == "??":
                    untracked_files.append(filename)
                elif code[0] in ("M", "A", "D", "R"):
                    staged_files.append(filename)
                elif code[1] in ("M", "D"):
                    modified_files.append(filename)

            is_clean = not (modified_files or untracked_files or staged_files)

            return {
                "is_git": True,
                "branch": branch,
                "ahead": ahead,
                "behind": behind,
                "modified": modified_files,
                "untracked": untracked_files,
                "staged": staged_files,
                "is_clean": is_clean,
                "repo_path": target_dir
            }
        except Exception as e:
            return {"is_git": False, "error": str(e)}

    def format_git_debrief(self, status: Dict[str, Any]) -> str:
        """
        Format an articulate J.A.R.V.I.S. debrief of Git repository status.
        """
        if not status.get("is_git"):
            return "No active Git version control repository detected in the designated workspace, Sir."

        branch = status.get("branch", "main")
        is_clean = status.get("is_clean", True)
        modified = status.get("modified", [])
        untracked = status.get("untracked", [])
        staged = status.get("staged", [])

        if is_clean:
            return f"Repository working directory on branch '{branch}' is completely clean, Sir. All changes committed."

        details = []
        if modified:
            details.append(f"{len(modified)} modified file{'s' if len(modified) != 1 else ''} ({', '.join(modified[:2])})")
        if staged:
            details.append(f"{len(staged)} staged file{'s' if len(staged) != 1 else ''}")
        if untracked:
            details.append(f"{len(untracked)} untracked item{'s' if len(untracked) != 1 else ''}")

        debrief = (
            f"Repository branch '{branch}' currently has active modifications, Sir: "
            f"{'; '.join(details)}. Ready for your review."
        )
        return debrief
