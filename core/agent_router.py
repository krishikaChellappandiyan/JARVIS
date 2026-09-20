import re
from typing import Tuple, Dict, Any, Optional
from core.task import Task, TaskType, TaskFinding
from core.task_manager import get_task_manager, TaskManager
from core.event_bus import get_event_bus, EventBus

class AgentRouter:
    def __init__(self):
        self.task_manager: TaskManager = get_task_manager()
        self.event_bus: EventBus = get_event_bus()

    def get_salutation(self) -> str:
        try:
            from core.jarvis_memory import JarvisMemory
            return JarvisMemory().get_salutation() or "Sir"
        except Exception:
            return "Sir"

    def route_input(self, text: str) -> Tuple[bool, str, Optional[Task], str]:
        """
        Routes incoming user voice/text query.
        Returns tuple:
            (handled: bool, spoken_ack: str, task: Optional[Task], action_category: str)
        """
        text_strip = text.strip()
        text_lower = text_strip.lower()
        if not text_lower:
            return False, "", None, ""

        sal = self.get_salutation()

        # ── 0A. Salutation / Honorific Directives (Dynamic "Sir" vs "Ma'am" / "Madam") ──
        m_sal = re.search(r'\b(?:call me|address me as|refer to me as|i am a woman call me|my title is)\s+(ma[\'\s]?am|madam|lady|miss|sir|boss|captain|commander)\b', text_lower)
        if not m_sal:
            if any(p in text_lower for p in ["call me madam", "address me as madam"]):
                m_sal_text = "Madam"
            elif any(p in text_lower for p in ["call me ma'am", "call me mam", "address me as ma'am", "im a woman", "i am a woman", "my gender is female", "she/her"]):
                m_sal_text = "Ma'am"
            elif any(p in text_lower for p in ["call me sir", "address me as sir"]):
                m_sal_text = "Sir"
            else:
                m_sal_text = None
        else:
            raw_sal = m_sal.group(1).lower().replace("'", "").strip()
            if raw_sal in ("madam", "madame"):
                m_sal_text = "Madam"
            elif raw_sal in ("maam", "lady", "miss"):
                m_sal_text = "Ma'am"
            elif raw_sal == "sir":
                m_sal_text = "Sir"
            else:
                m_sal_text = raw_sal.title()

        if m_sal_text:
            try:
                from core.jarvis_memory import JarvisMemory
                mem = JarvisMemory()
                mem.set_salutation(m_sal_text)
            except Exception as e:
                print(f"[AgentRouter] Error saving salutation: {e}")
            self.event_bus.emit("set_operator_salutation", {"salutation": m_sal_text})
            ack = f"Understood, {m_sal_text}. My sincere apologies for the oversight—all protocol registers, speech models, and telemetry have been updated."
            return True, ack, None, "set_operator_salutation"

        # ── 0. Check for Mode Switch Commands ─────────────────────
        if any(kw in text_lower for kw in ["osint mode", "war room", "recon mode", "tactical mode", "war mode", "warm mode", "warm room", "engage osint", "engage war"]):
            self.event_bus.emit("set_app_mode", {"mode": "osint"})
            return True, f"Tactical intelligence and target reconnaissance mode engaged, {sal}.", None, "mode_switch_osint"

        if any(kw in text_lower for kw in ["partner mode", "assistant mode", "casual mode", "companion mode", "executive mode"]):
            self.event_bus.emit("set_app_mode", {"mode": "partner"})
            return True, f"Returning to primary executive mode, {sal}. Systems standing by.", None, "mode_switch_partner"

        active_task = self.task_manager.get_active_task()

        # ── 1. Check for Conversational Follow-Up Commands ────────
        target_task = active_task
        if not target_task:
            tasks = self.task_manager.list_tasks()
            if tasks:
                target_task = tasks[-1]

        # A. Minimize command
        if any(w in text_lower for w in ["minimize", "minimize panel", "minimize window", "hide panel", "hide window", "minimize that", "hide that", "put it down", "minimize that window"]):
            if target_task:
                self.task_manager.minimize_task(target_task.task_id)
                return True, "Minimized the panel, Sir.", target_task, "followup_minimize"

        # B. Expand/Maximize command
        if any(w in text_lower for w in ["expand", "maximize", "show panel", "show window", "restore panel", "restore window", "bring it up", "open panel", "restore", "restore surface", "expand surface", "restore task", "maximize window", "bring that up"]):
            if target_task:
                self.task_manager.expand_task(target_task.task_id)
                return True, "Expanded the task surface.", target_task, "followup_expand"

        # C. Close/Dismiss command
        if any(w in text_lower for w in ["close panel", "close window", "close task", "dismiss panel", "dismiss window", "dismiss task", "close that", "dismiss that", "close that window"]):
            if target_task:
                self.task_manager.close_task(target_task.task_id)
                return True, "Closed the task surface.", None, "followup_close"

        # D. Select Item / Open Result ("open the second one", "show result 1")
        m_item = re.search(r'(?:open|show|play|view|select|click)\s+(?:the\s+)?(?:result\s+|video\s+|item\s+|link\s+|number\s+)?(\d+|first|second|third|fourth|fifth)', text_lower)
        if m_item and active_task and active_task.findings:
            raw_idx = m_item.group(1)
            idx_map = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
            idx_num = idx_map.get(raw_idx, int(raw_idx) if raw_idx.isdigit() else 1) - 1
            
            finding = self.task_manager.select_task_item(active_task.task_id, idx_num)
            if finding:
                # Upgrade task to Internal Browser Surface for watching/viewing
                surf_task = self.task_manager.create_task(
                    type_=TaskType.BROWSER_SURF.value,
                    title=f"Browser: {finding.title[:35]}",
                    data={"url": finding.url, "parent_task_id": active_task.task_id, "title": finding.title}
                )
                self.task_manager.add_finding(surf_task.task_id, finding)
                self.task_manager.complete_task(surf_task.task_id, f"Loaded internal surface: {finding.title}")
                return True, f"Opening {finding.title} inside the internal browser surface.", surf_task, "followup_select"

        # ── 2. Check for YouTube Search ────────────────────────────
        if "youtube" in text_lower or "watch" in text_lower or "video search" in text_lower:
            m_yt = re.search(r'(?:search\s+youtube\s+for|youtube\s+search|youtube|find\s+videos?\s+on|watch)\s+(?:for\s+)?(.+)', text_lower)
            query = m_yt.group(1).strip() if m_yt else text_strip
            query = re.sub(r'^(?:do\s+a|can\s+you|please|search|for|about)\s+', '', query, flags=re.IGNORECASE).strip()
            if not query:
                query = text_strip

            task = self.task_manager.create_task(
                type_=TaskType.YOUTUBE_SEARCH.value,
                title=f"YouTube Search: {query}",
                data={"query": query}
            )
            return True, f"Searching YouTube for '{query}', {sal}.", task, "youtube_search"

        # ── 3. Check for Autonomous Terminal / System Command ──────
        # Handles explicit commands, backticks, or direct CLI binary execution (dig, nmap, curl, etc.)
        cmd_candidate = None
        m_cmd_explicit = re.search(r'^(?:run\s+command|execute\s+command|terminal|shell|bash)\s*[:\-]?\s*(.+)$', text_strip, re.IGNORECASE)
        m_backtick = re.search(r'^(?:run|exec|execute)?\s*`([^`]+)`$', text_strip, re.IGNORECASE)
        
        cli_tools = [
            "dig", "nmap", "curl", "subfinder", "nuclei", "httpx", "ping", "whois",
            "traceroute", "df", "free", "ps", "ls", "cat", "python", "python3",
            "bash", "ip", "netstat", "ss", "uptime", "uname", "grep", "which",
            "find", "head", "tail", "wc"
        ]
        tools_regex = r'^(?:run|exec|execute)?\s*(' + '|'.join(cli_tools) + r')\b(.*)$'
        m_tool = re.search(tools_regex, text_strip, re.IGNORECASE)

        if m_backtick:
            cmd_candidate = m_backtick.group(1).strip()
        elif m_cmd_explicit:
            cmd_candidate = m_cmd_explicit.group(1).strip().strip('`')
        elif m_tool and not any(kw in text_lower for kw in ["search", "youtube", "investigate", "target"]):
            tool_name = m_tool.group(1).strip().lower()
            rest = m_tool.group(2).strip()
            cmd_candidate = f"{tool_name} {rest}".strip()

        if cmd_candidate:
            task = self.task_manager.create_task(
                type_=TaskType.TERMINAL_COMMAND.value,
                title=f"Terminal: {cmd_candidate[:30]}",
                data={"command": cmd_candidate}
            )
            return True, f"Executing `{cmd_candidate}` on your system.", task, "terminal_command"

        # ── 4. Check for Explicit Web Search Command ────────────────
        m_explicit_search = re.search(r'^(?:google\s+search|search\s+google|search\s+the\s+web|web\s+search)\s+(?:for\s+|about\s+|on\s+)?(.+)', text_lower)
        if m_explicit_search:
            query = m_explicit_search.group(1).strip()
            query = re.sub(r'^(?:do\s+a|can\s+you|please|for|about)\s+', '', query, flags=re.IGNORECASE).strip()
            if query:
                task = self.task_manager.create_task(
                    type_=TaskType.GOOGLE_SEARCH.value,
                    title=f"Google Search: {query}",
                    data={"query": query}
                )
                return True, f"Searching Google for '{query}'.", task, "google_search"

        # ── 4.5 Check for System & Hardware Diagnostics ───────────
        if any(kw in text_lower for kw in [
            "system diagnostic", "hardware diagnostic", "system status", "hardware status",
            "system telemetry", "hardware stats", "system stats", "diagnostics",
            "how are system resources", "system resources", "cpu load", "battery status",
            "thermal status", "thermals", "resource monitor"
        ]):
            task = self.task_manager.create_task(
                type_=TaskType.SYSTEM_DIAGNOSTIC.value,
                title="System Diagnostic & Telemetry",
                data={"query": text_strip}
            )
            return True, f"Running full hardware and system diagnostics, {sal}.", task, "system_diagnostic"

        # ── 4.6 Check for Situational Briefing ────────────────────
        if any(kw in text_lower for kw in [
            "good morning", "situational briefing", "status report", "morning protocol",
            "executive briefing", "how is the day looking", "how does the day look", "daily briefing"
        ]):
            task = self.task_manager.create_task(
                type_=TaskType.SITUATIONAL_BRIEFING.value,
                title="Executive Situational Briefing",
                data={"query": text_strip}
            )
            return True, f"Compiling executive situational briefing, {sal}.", task, "situational_briefing"

        # ── 4.7 Check for System Agency Controls (Volume, Media, Clipboard, Process) ──
        if any(kw in text_lower for kw in [
            "volume up", "volume down", "mute", "unmute", "set volume", "turn up the volume",
            "turn down the volume", "pause music", "resume music", "play music", "next track",
            "previous track", "stop music", "lock screen", "lock workstation", "lock computer",
            "clipboard", "top process", "highest cpu", "highest memory", "what's eating memory",
            "whats eating memory", "kill process", "terminate process"
        ]):
            action_type = "volume"
            if any(w in text_lower for w in ["pause", "resume", "play music", "track", "stop music"]):
                action_type = "media"
            elif any(w in text_lower for w in ["lock"]):
                action_type = "lock"
            elif any(w in text_lower for w in ["clipboard"]):
                action_type = "clipboard"
            elif any(w in text_lower for w in ["process", "cpu", "memory"]):
                action_type = "process"

            task = self.task_manager.create_task(
                type_=TaskType.SYSTEM_CONTROL.value,
                title=f"System Control: {action_type.title()}",
                data={"action_type": action_type, "command": text_strip}
            )
            return True, f"Executing {action_type} system directive, {sal}.", task, "system_control"

        # ── 4.8 Check for Git Repository Intelligence ─────────────
        if any(kw in text_lower for kw in [
            "git status", "repo status", "git branch", "uncommitted changes",
            "repository status", "git diff", "git log"
        ]):
            task = self.task_manager.create_task(
                type_=TaskType.GIT_INTEL.value,
                title="Git Repository Telemetry",
                data={"query": text_strip}
            )
            return True, f"Auditing repository telemetry and version control status, {sal}.", task, "git_intel"

        # ── 4.9 Check for Desktop Vision & OCR ("Point, Speak, Act") ──
        if any(kw in text_lower for kw in [
            "look at my screen", "see my screen", "check my screen", "read my screen",
            "what's on my screen", "what is on my screen", "what am i looking at",
            "what am i pointing at", "explain this error", "read this window",
            "read this code", "look at this", "ocr this", "extract text from screen",
            "inspect screen", "read pointer", "look at this code", "look at this error"
        ]):
            task = self.task_manager.create_task(
                type_=TaskType.VISION_INSPECT.value,
                title="Desktop Vision & Cursor Inspection",
                data={"query": text_strip}
            )
            return True, f"Deploying Stark Vision Eye and analyzing text under your cursor, {sal}.", task, "vision_inspect"

        # ── 4.10 Check for Ambient Sentinel Telemetry ─────────────
        if any(kw in text_lower for kw in [
            "quiet mode", "enable quiet mode", "disable quiet mode",
            "sentinel status", "guardian status", "check vitals", "vitals check"
        ]):
            task = self.task_manager.create_task(
                type_=TaskType.AMBIENT_CONFIG.value,
                title="Ambient Sentinel Guardian",
                data={"query": text_strip}
            )
            return True, f"Accessing Ambient Sentinel configuration and telemetry, {sal}.", task, "ambient_config"

        # ── 4.11 Check for Engineering Lab Script Authoring ───────
        if any(kw in text_lower for kw in [
            "create script", "write script", "write a python script",
            "create a python script", "engineering script", "write a script"
        ]):
            task = self.task_manager.create_task(
                type_=TaskType.ENGINEERING_SCRIPT.value,
                title="Stark Engineering Lab",
                data={"query": text_strip}
            )
            return True, f"Initializing Stark Engineering Lab sandbox, {sal}.", task, "engineering_script"

        # ── 4.12 Check for Proactive Reminders & Timers ───────────
        if any(kw in text_lower for kw in [
            "set a timer", "set timer", "start a timer", "start timer",
            "countdown", "remind me", "set a reminder", "set reminder",
            "list reminders", "show reminders", "my reminders", "what are my reminders",
            "list timers", "show timers", "my timers", "what are my timers",
            "active timers", "active reminders", "any timers", "any reminders",
            "cancel timer", "cancel reminder", "clear timers", "stop timer"
        ]) or re.search(r'^(?:timer|reminder)\b', text_lower):
            task = self.task_manager.create_task(
                type_=TaskType.REMINDER_TIMER.value,
                title="Proactive Reminder & Timer",
                data={"query": text_strip}
            )
            return True, f"Configuring tactical reminder protocol, {sal}.", task, "reminder_timer"

        # ── 5. Check for System Action (App Launch) ────────────────
        m_app = re.search(r'^(?:open|launch|run|start)\s+(?:application|app|program)?\s*([a-zA-Z0-9_\-\s]+)$', text_lower)
        if m_app:
            app_name = m_app.group(1).strip()
            excluded = ["google", "youtube", "dialog", "target", "investigation", "case", "node", "first", "second", "third", "fourth", "fifth", "1", "2", "3", "4", "5", "panel", "surface", "chip"] + cli_tools
            if app_name not in excluded and not app_name.startswith("the ") and not any(w in app_name for w in ["result", "video", "item", "link", "number", "second", "third", "fourth", "fifth"]):
                task = self.task_manager.create_task(
                    type_=TaskType.SYSTEM_ACTION.value,
                    title=f"System Action: Launch {app_name.upper()}",
                    data={"app_name": app_name}
                )
                return True, f"Launching {app_name} on your system.", task, "system_action"

        # ── 4.8 Check for Memory Storage / Rule Definition ─────────
        store_match = re.search(
            r'\b(?:remember\s+(?:this|that|for\s+me|log)|you\s+can\s+remember|keep\s+in\s+mind|don\'?t\s+forget|note\s+that|learn\s+that|when\s+i\s+say\b|means?\b|meaning\b)',
            text_lower
        )
        if store_match and not any(kw in text_lower for kw in ["do you remember", "what did we", "what did i", "what do you mean", "what does", "recall our", "recall the"]):
            rule_text = text_strip
            rule_text = re.sub(r'^(?:j\.?a\.?r\.?v\.?i\.?s\.?,?\s*|please\s+|hey\s+jarvis,?\s*)', '', rule_text, flags=re.IGNORECASE).strip()
            task = self.task_manager.create_task(
                type_="memory_store",
                title=f"Store Memory: {rule_text[:35]}",
                data={"rule": rule_text}
            )
            return True, f"I have committed that rule to persistent memory, {sal}.", task, "memory_store"

        # ── 5. Check for Memory Recall Query ───────────────────────
        if any(kw in text_lower for kw in [
            "do you remember", "what did we say", "what did we discuss", "what did i say",
            "recall yesterday", "recall previous", "recall memory", "check memory", "search memory",
            "previous conversation"
        ]) or re.search(r'\brecall\s+(?:our|the|what|logs?|conversation)\b', text_lower):
            task = self.task_manager.create_task(
                type_=TaskType.MEMORY_RECALL.value,
                title=f"Memory Recall: {text_strip[:30]}",
                data={"query": text_strip}
            )
            return True, f"Scanning memory logs for related context, {sal}.", task, "memory_recall"

        # ── 6. Check for Investigation Recon ─────────────────────
        is_map_or_media = any(w in text_lower for w in ["camera", "cctv", "map", "route", "street", "traffic", "flight", "satellite", "earth", "globe", "sector", "surveillance feed"])
        if not is_map_or_media and any(kw in text_lower for kw in ["investigate", "scan target", "recon case", "analyze target"]):
            m_target = re.search(r'(?:investigate|scan|recon|analyze)\s+(?:target\s+|domain\s+)?([a-zA-Z0-9\.\-_]+)', text_lower)
            target = m_target.group(1).strip() if m_target else "target"
            task = self.task_manager.create_task(
                type_=TaskType.INVESTIGATION.value,
                title=f"Investigation: {target}",
                data={"target": target}
            )
            return True, f"Initiating investigation pipeline for target '{target}'.", task, "investigation"

        # ── 6.5 Check for Case Cross-Verification ──────────────────
        if any(kw in text_lower for kw in ["cross verify", "cross-verify", "verify case", "correlate case", "cross check case", "cross-check case", "check cross correlation"]):
            task = self.task_manager.create_task(
                type_="cross_verify_case",
                title="Case Cross-Verification",
                data={"query": text_strip}
            )
            return True, f"Cross-verifying active case telemetry against all intelligence records, {sal}.", task, "cross_verify_case"

        # ── 7. Check for Flight Radar / Military Airspace ──────────
        if any(kw in text_lower for kw in [
            "military flight", "military aircraft", "flight radar", "airspace",
            "tracking flight", "flight trace", "radar sweep", "god's view flight",
            "gods view flight", "military radar", "air traffic", "track aircraft", "planes overhead"
        ]):
            task = self.task_manager.create_task(
                type_=TaskType.FLIGHT_INTEL.value,
                title="Tactical Airspace Radar",
                data={"query": text_strip}
            )
            return True, "Locking onto global military airspace and ADS-B radar feeds.", task, "flight_intel"

        # ── 7.5 Check for Area Annotation (AI Ability) ─────────────
        if any(kw in text_lower for kw in [
            "annotate this area", "annotate area", "mark this area", "highlight this area",
            "annotate sector", "draw boundary", "defense zone", "tactical perimeter",
            "no-fly zone", "no fly zone", "exclusion zone", "mark area", "mark a zone",
            "mark zone", "perimeter zone"
        ]) or (("annotate" in text_lower or "mark" in text_lower) and any(z in text_lower for z in ["zone", "perimeter", "sector", "boundary"])):
            m_sec = re.search(r'(?:annotate|mark|highlight)\s+(?:this\s+area|area|sector)\s*(?:as|called|named)?\s*(.*)', text_strip, flags=re.IGNORECASE)
            sec_name = m_sec.group(1).strip() if m_sec else ""
            m_rad = re.search(r'(\d+)\s*(?:km|kilo)', text_lower)
            radius = float(m_rad.group(1)) if m_rad else 30.0
            classification = "NO-FLY ZONE" if ("no fly" in text_lower or "no-fly" in text_lower) else ("DEFENSE ZONE" if "defense" in text_lower else "TACTICAL SECTOR")
            if not sec_name:
                sec_name = classification

            task = self.task_manager.create_task(
                type_="annotate_area",
                title=f"Annotate: {sec_name[:25]}",
                data={"sector_name": sec_name, "radius_km": radius, "classification": classification, "query": text_strip}
            )
            self.event_bus.emit("annotate_area", {
                "sector_name": sec_name,
                "radius_km": radius,
                "classification": classification,
                "use_camera_center": True
            })
            return True, f"Illuminating tactical perimeter and annotating {sec_name} on World Telemetry, {sal}.", task, "annotate_area"

        # ── 8. Check for Live Weather Telemetry ────────────────────
        if any(kw in text_lower for kw in [
            "weather", "temperature", "forecast", "how's the weather", "how is the weather",
            "current weather", "is it raining", "what's the weather"
        ]):
            loc = ""
            m_loc = re.search(r'(?:weather|forecast|temperature)\s+(?:in|for|at)\s+([a-zA-Z\s,]+)', text_lower)
            if m_loc:
                loc = m_loc.group(1).strip()
            if not loc:
                m_in = re.search(r'\bin\s+([a-zA-Z\s]+)$', text_lower)
                if m_in:
                    loc = m_in.group(1).strip()
            loc_clean = re.sub(r'^(?:the|a)\s+', '', loc, flags=re.I).strip()
            loc_clean = re.sub(r'[?!.,]+$', '', loc_clean).strip()
            if not loc_clean:
                return True, f"Which city or region would you like atmospheric telemetry for, {sal}?", None, "clarification"
            task = self.task_manager.create_task(
                type_=TaskType.WEATHER_INTEL.value,
                title=f"Weather Telemetry: {loc_clean.title()}",
                data={"location": loc_clean, "query": text_strip}
            )
            ack = f"Scanning atmospheric telemetry for {loc_clean.title()}, {sal}."
            return True, ack, task, "weather_intel"

        # ── 8B. Check for Live Traffic & GIS Map Telemetry ────────
        if any(kw in text_lower for kw in [
            "traffic", "traffic situation", "traffic condition", "traffic update",
            "traffic in", "road condition", "congestion", "map of", "show map", "gis map", "street traffic"
        ]):
            loc = ""
            m_loc = re.search(r'(?:traffic\s+(?:situation|condition|update|status)?\s+(?:in|for|at|around)?|map\s+(?:of|for|around)|where\s+is)\s+([a-zA-Z\s,]+)', text_lower)
            if m_loc:
                loc = m_loc.group(1).strip()
            if not loc:
                m_in = re.search(r'\bin\s+([a-zA-Z\s]+)$', text_lower)
                if m_in:
                    loc = m_in.group(1).strip()
            loc_clean = re.sub(r'^(?:the|a)\s+', '', loc, flags=re.I).strip()
            # Clean trailing question marks or punctuation
            loc_clean = re.sub(r'[?!.,]+$', '', loc_clean).strip()
            if not loc_clean:
                return True, f"Which city or sector would you like live traffic telemetry for, {sal}?", None, "clarification"
            display_loc = loc_clean.title()
            task = self.task_manager.create_task(
                type_=TaskType.TRAFFIC_INTEL.value,
                title=f"Traffic Telemetry: {display_loc}",
                data={"location": loc_clean, "query": text_strip}
            )
            ack = f"Querying live traffic telemetry and GIS nodes for {display_loc}, {sal}."
            return True, ack, task, "traffic_intel"

        # ── 9. Check for CCTV Surveillance Feeds ──────────────────
        cctv_keywords = [
            "cctv", "traffic cam", "security camera", "public camera", "surveillance camera",
            "cameras in", "cams in", "camera in", "camera at", "cameras at", "access camera",
            "turn on camera", "show camera", "view camera", "feed in", "surveillance in",
            "turn on cctv", "open cctv", "show cctv", "view cctv"
        ]
        if any(kw in text_lower for kw in cctv_keywords) or (("camera" in text_lower or "cctv" in text_lower) and any(p in text_lower for p in [" in ", " at ", " around ", " near ", " for "])):
            city = ""
            m_in = re.search(r'\b(?:in|at|for|around|near)\s+([a-zA-Z\s,\.\-]+)$', text_lower)
            if m_in:
                city = m_in.group(1).strip()
            else:
                m_cctv = re.search(r'(?:cctv|cameras?|cams?|surveillance)\s+(?:in|for|at|around|near)?\s*([a-zA-Z\s,\.\-]+)', text_lower)
                if m_cctv:
                    city = m_cctv.group(1).strip()
            city_clean = re.sub(r'\b(?:cctv|cameras?|cams?|surveillance|traffic|security|public|access|turn|on|open|show|view|the|a)\b', '', city, flags=re.I).strip()
            city_clean = re.sub(r'^(?:in|at|for|around|near)\s+', '', city_clean, flags=re.I).strip()
            city_clean = re.sub(r'[?!.,]+$', '', city_clean).strip()
            if not city_clean:
                return True, f"Which city would you like optical surveillance feeds for, {sal}?", None, "clarification"
            target_city = city_clean.title()

            task = self.task_manager.create_task(
                type_=TaskType.BROWSER_SURF.value,
                title=f"CCTV Surveillance: {target_city}",
                data={"cctv": True, "city": city_clean}
            )
            return True, f"Connecting to live public CCTV surveillance feeds for {target_city}, {sal}.", task, "cctv_intel"

        return False, "", None, ""

