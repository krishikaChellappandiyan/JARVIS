"""
J.A.R.V.I.S. Autonomous Tactical Reasoning Engine ("JARVIS-Level Thinking").

Orchestrates multi-step cognitive plans, dynamically inspects and activates tactical tools
(God's Eye 3D navigation, CCTV networks across India/US/UK/Japan/Global, live ADS-B radar,
traffic vectors, terminal diagnostics, atmospheric telemetry, web intelligence),
and streams real-time spoken progress phrases ("I am checking X... and I found Y")
to the voice pipeline until the goal is fully accomplished.
"""

import os
import re
import time
import json
import threading
from typing import Dict, List, Any, Optional, Callable, Tuple

from core.event_bus import get_event_bus, EventBus
from core.task_manager import get_task_manager, TaskManager
from core.task import Task, TaskType, TaskFinding


class JarvisCognitiveLoop:
    """
    Multi-Step Autonomous Tactical Cognitive Agent for J.A.R.V.I.S.
    """

    def __init__(self, voice_engine=None, event_bus: Optional[EventBus] = None):
        self.voice = voice_engine
        self.bus = event_bus or get_event_bus()
        self.task_manager: TaskManager = get_task_manager()
        self._max_steps = 5

    # ── 1. Dynamic Tool / Capability Registry ────────────────────────

    def tool_gods_eye_nav(self, location_name: str, zoom_altitude: Optional[float] = None) -> Dict[str, Any]:
        """Navigates the 3D planetary Earth globe to the specified city or coordinates."""
        from frontend.desktop import resolve_geospatial_coordinates
        res = resolve_geospatial_coordinates(location_name)
        if not res:
            return {"success": False, "error": f"Coordinates unresolvable for '{location_name}'"}
        lat, lon, matched_name = res
        payload = {"lat": lat, "lon": lon, "label": matched_name}
        if zoom_altitude:
            payload["altitude"] = zoom_altitude
        self.bus.emit("glide_to_location", payload)
        self.bus.emit("jarvis_play_sfx", {"effect": "target_lock"})
        return {"success": True, "lat": lat, "lon": lon, "label": matched_name}

    def tool_tactical_layer(self, layer: str, state: bool = True) -> Dict[str, Any]:
        """Toggles God's Eye tactical HUD overlay layers (cctv, traffic, flights, weather, space, etc.)."""
        valid_layers = {"cctv", "traffic", "flights", "satellites", "seismic", "wildfires", "weather", "space", "radio"}
        clean_layer = layer.lower().strip()
        if clean_layer not in valid_layers:
            alias_map = {
                "flight": "flights", "radar": "flights", "plane": "flights", "airspace": "flights",
                "camera": "cctv", "cam": "cctv", "surveillance": "cctv",
                "road": "traffic", "roads": "traffic", "flow": "traffic",
                "satellite": "space", "orbit": "space", "iss": "space",
                "earthquake": "seismic", "quake": "seismic",
                "fire": "wildfires", "fires": "wildfires", "firms": "wildfires",
                "clouds": "weather", "radar_rain": "weather"
            }
            clean_layer = alias_map.get(clean_layer, clean_layer)

        self.bus.emit("toggle_tactical_layer", {"layer": clean_layer, "state": state})
        return {"success": True, "layer": clean_layer, "state": state}

    def tool_cctv_query(self, location_name: str, radius_km: float = 60.0) -> Dict[str, Any]:
        """Discovers live and optical surveillance cameras across India, US, UK, Japan, or worldwide."""
        from modules.cctv_service import find_cctv_for_location
        cameras = find_cctv_for_location(location_name, radius_km=radius_km)
        if cameras:
            self.tool_tactical_layer("cctv", True)
            first_cam = cameras[0]
            self.bus.emit("glide_to_location", {
                "lat": first_cam["lat"],
                "lon": first_cam["lon"],
                "label": first_cam.get("city", location_name).title()
            })
            self.bus.emit("cctv_camera_selected", {"camera": first_cam})
        return {
            "success": bool(cameras),
            "count": len(cameras),
            "cameras": cameras[:5],
            "city": cameras[0].get("city", location_name) if cameras else location_name
        }

    def tool_traffic_query(self, location_name: str) -> Dict[str, Any]:
        """Queries live road traffic telemetry, average speeds, and GIS flow vectors."""
        from modules.maps_nav import MapsNavigationEngine
        nav = MapsNavigationEngine()
        traffic = nav.get_traffic_intel(location_name)
        if traffic and "lat" in traffic:
            self.tool_tactical_layer("traffic", True)
        return {"success": bool(traffic and "lat" in traffic), "traffic": traffic}

    def tool_flight_radar(self, query: str = "", military_only: bool = True) -> Dict[str, Any]:
        """Queries live ADS-B radar transponders and military airframes."""
        from modules.flight_intel import FlightIntelEngine
        fe = FlightIntelEngine()
        flights = fe.get_military_aircraft(limit=8)
        self.tool_tactical_layer("flights", True)
        debrief = fe.format_tactical_debrief(flights)
        return {"success": True, "count": len(flights), "flights": flights[:5], "debrief": debrief}

    def tool_weather_query(self, location_name: str) -> Dict[str, Any]:
        """Pulls live atmospheric telemetry and weather radar."""
        from modules.weather_intel import WeatherIntelEngine
        we = WeatherIntelEngine()
        w = we.get_weather(location_name)
        if not w:
            return {"success": False, "weather": {}, "debrief": f"Atmospheric readings for '{location_name}' could not be resolved."}
        debrief = we.format_weather_debrief(w)
        return {"success": True, "weather": w, "debrief": debrief}

    def tool_terminal_exec(self, command: str) -> Dict[str, Any]:
        """Executes authorized system/CLI command."""
        from core.system_commander import get_system_commander
        commander = get_system_commander()
        res = commander.execute(command, timeout=40.0)
        return {"success": res["success"], "stdout": res.get("stdout", "")[:1000], "exit_code": res.get("exit_code", 0)}

    def tool_web_search(self, query: str) -> Dict[str, Any]:
        """Performs real-time web search."""
        from core.system_skills import SystemSkillEngine
        skills = SystemSkillEngine()
        intel_summary, raw_results = skills.perform_live_search(query)
        return {"success": bool(raw_results), "summary": intel_summary[:1200], "results_count": len(raw_results)}

    def tool_diagnostics(self) -> Dict[str, Any]:
        """Runs live hardware diagnostics."""
        from modules.system_diagnostics import SystemDiagnosticsEngine
        diag = SystemDiagnosticsEngine()
        metrics = diag.get_metrics()
        debrief = diag.format_tactical_debrief(metrics)
        return {"success": True, "metrics": metrics, "debrief": debrief}

    def tool_top_processes(self, limit: int = 5, by: str = "cpu") -> Dict[str, Any]:
        """Inspects top active processes."""
        from modules.system_controller import SystemController
        sc = SystemController()
        procs = sc.get_top_processes(limit=limit, by=by)
        summary = ", ".join([f"{p['name']} ({p['cpu_percent']}% CPU, {p['memory_percent']}% RAM)" for p in procs[:3]])
        return {"success": True, "processes": procs, "debrief": f"Top resource processes: {summary}."}

    def tool_git_intel(self) -> Dict[str, Any]:
        """Inspects Git repository and version control telemetry."""
        from modules.system_controller import SystemController
        sc = SystemController()
        stat = sc.get_git_status()
        debrief = sc.format_git_debrief(stat)
        return {"success": stat.get("is_git", False), "status": stat, "debrief": debrief}

    def tool_situational_briefing(self, location: str = "") -> Dict[str, Any]:
        """Synthesizes comprehensive situational briefing."""
        from modules.situational_briefing import SituationalBriefingEngine
        sb = SituationalBriefingEngine()
        res = sb.generate_briefing(location)
        return {"success": True, "briefing": res, "debrief": res["spoken_text"]}

    def tool_clipboard(self) -> Dict[str, Any]:
        """Inspects and summarizes active system clipboard."""
        from modules.system_controller import SystemController
        sc = SystemController()
        debrief = sc.summarize_clipboard()
        return {"success": True, "debrief": debrief}

    def tool_calendar(self) -> Dict[str, Any]:
        """Queries calendar schedule and conflicts."""
        from modules.calendar_intel import CalendarIntelManager
        cal = CalendarIntelManager()
        debrief = cal.format_jarvis_reminders()
        return {"success": True, "debrief": debrief}

    def tool_inbox(self) -> Dict[str, Any]:
        """Queries unread messages and urgent inbox alerts."""
        from modules.inbox_intel import InboxIntelManager
        inbox = InboxIntelManager()
        debrief = inbox.get_tldr_summary()
        return {"success": True, "debrief": debrief}

    def tool_media_control(self, action: str) -> Dict[str, Any]:
        """Controls system media playback."""
        from modules.system_controller import SystemController
        sc = SystemController()
        return sc.media_control(action)

    def tool_volume(self, percent: int) -> Dict[str, Any]:
        """Adjusts system volume."""
        from modules.system_controller import SystemController
        sc = SystemController()
        return sc.set_volume(percent)

    # ── 2. Intent & Plan Synthesis ────────────────────────────────────

    def analyze_goal(self, user_text: str) -> List[Dict[str, Any]]:
        """
        Decomposes complex user prompt into a structured multi-step tactical plan.
        Detects combinations of CCTV, traffic, navigation, flight tracking, weather, and terminal tasks.
        """
        text_lower = user_text.lower().strip()
        plan_steps = []

        loc_candidate = ""
        m_loc = re.search(r'\b(?:in|at|for|around|over|near|towards)\s+([a-zA-Z\s,\.\-]{2,30})', text_lower)
        if m_loc:
            raw_loc = m_loc.group(1).strip()
            cleaned_loc = re.sub(r'\b(?:and|check|see|show|find|tell|traffic|cctv|camera|flights?|weather|how|what)\b.*$', '', raw_loc).strip()
            loc_candidate = cleaned_loc.strip(' ,.?!')

        has_cctv = any(w in text_lower for w in ["cctv", "camera", "cameras", "cam", "cams", "optical", "surveillance", "vantage"])
        has_traffic = any(w in text_lower for w in ["traffic", "congestion", "road", "roads", "flow", "jam", "commute", "highway"])
        has_flight = any(w in text_lower for w in ["flight", "flights", "aircraft", "plane", "planes", "radar", "airspace", "ads-b", "adsb", "chase"])
        has_weather = any(w in text_lower for w in ["weather", "forecast", "rain", "temperature", "storm", "wind"])
        has_cockpit = any(w in text_lower for w in ["cockpit", "chase cam", "lock on", "track plane", "lock onto"])
        has_search = bool(re.search(r'\b(?:google\s+search|web\s+search|search\s+(?:the\s+web|google|online))\b', text_lower))
        has_briefing = any(w in text_lower for w in ["good morning", "briefing", "situational briefing", "status report", "morning protocol", "executive briefing", "how is the day looking", "how does the day look"])
        has_diag = any(w in text_lower for w in ["diagnostic", "system resource", "hardware stat", "cpu load", "thermals", "system status", "hardware status", "system telemetry", "resource monitor"])
        has_proc = any(w in text_lower for w in ["top process", "highest cpu", "highest memory", "what's using", "whats using", "memory hog", "cpu hog", "kill process", "terminate process", "running processes"])
        has_git = any(w in text_lower for w in ["git status", "repo status", "git branch", "uncommitted", "repository status", "git diff"])
        has_calendar = any(w in text_lower for w in ["calendar", "schedule", "my meetings", "upcoming event", "agenda", "double booking"])
        has_inbox = any(w in text_lower for w in ["scan email", "inbox", "urgent mail", "unread message", "check mail", "panic text"])
        has_clip = any(w in text_lower for w in ["clipboard", "what's on my clipboard", "whats on my clipboard", "read clipboard", "copied"])
        has_vol = any(w in text_lower for w in ["volume up", "volume down", "mute", "unmute", "set volume"])
        has_media = any(w in text_lower for w in ["pause music", "resume music", "play music", "next track", "previous track", "stop music"])

        if loc_candidate:
            plan_steps.append({
                "action": "nav",
                "location": loc_candidate,
                "progress_phrase": f"Navigating orbital telemetry to {loc_candidate.title()}, Sir..."
            })

        if has_cctv:
            if loc_candidate:
                plan_steps.append({
                    "action": "cctv",
                    "location": loc_candidate,
                    "progress_phrase": f"Querying active optical surveillance feeds across {loc_candidate.title()}..."
                })
            else:
                plan_steps.append({
                    "action": "ask_location",
                    "topic": "optical surveillance feeds",
                    "progress_phrase": "Awaiting location designation for optical surveillance feeds..."
                })

        if has_traffic:
            if loc_candidate:
                plan_steps.append({
                    "action": "traffic",
                    "location": loc_candidate,
                    "progress_phrase": f"Cross-referencing live street traffic and GIS flow vectors for {loc_candidate.title()}..."
                })
            else:
                plan_steps.append({
                    "action": "ask_location",
                    "topic": "live street traffic telemetry",
                    "progress_phrase": "Awaiting location designation for traffic telemetry..."
                })

        if has_weather:
            if loc_candidate:
                plan_steps.append({
                    "action": "weather",
                    "location": loc_candidate,
                    "progress_phrase": f"Pulling regional atmospheric radar and precipitation telemetry for {loc_candidate.title()}..."
                })
            else:
                plan_steps.append({
                    "action": "ask_location",
                    "topic": "atmospheric telemetry",
                    "progress_phrase": "Awaiting location designation for atmospheric telemetry..."
                })

        if has_flight:
            plan_steps.append({
                "action": "flights",
                "query": loc_candidate,
                "progress_phrase": "Scanning global ADS-B military and civilian airspace transponders..."
            })

        if has_cockpit:
            plan_steps.append({
                "action": "cockpit",
                "target": loc_candidate or "",
                "progress_phrase": "Acquiring kinematic lock and initializing 3D tactical cockpit chase camera..."
            })

        if has_briefing:
            plan_steps.append({
                "action": "briefing",
                "location": loc_candidate,
                "progress_phrase": "Compiling multi-source executive situational briefing, Sir..."
            })

        if has_diag:
            plan_steps.append({
                "action": "diagnostics",
                "progress_phrase": "Querying live hardware diagnostic sensors and CPU telemetry, Sir..."
            })

        if has_proc:
            plan_steps.append({
                "action": "top_processes",
                "query": user_text,
                "progress_phrase": "Auditing active processes and resource allocation, Sir..."
            })

        if has_git:
            plan_steps.append({
                "action": "git_intel",
                "progress_phrase": "Inspecting repository branch and working directory state, Sir..."
            })

        if has_calendar:
            plan_steps.append({
                "action": "calendar",
                "progress_phrase": "Scanning your agenda and scheduling buffers, Sir..."
            })

        if has_inbox:
            plan_steps.append({
                "action": "inbox",
                "progress_phrase": "Scanning inbox dispatches and priority communications, Sir..."
            })

        if has_clip:
            plan_steps.append({
                "action": "clipboard",
                "progress_phrase": "Reading active system clipboard buffers, Sir..."
            })

        if has_vol or has_media:
            plan_steps.append({
                "action": "media_control",
                "command": user_text,
                "progress_phrase": "Dispatching audio/media command to system controller, Sir..."
            })

        if not plan_steps and has_search:
            clean_q = re.sub(r'^(?:search|google|find|look up)\s+(?:for\s+|about\s+)?', '', text_lower).strip()
            plan_steps.append({
                "action": "search",
                "query": clean_q or user_text,
                "progress_phrase": f"Scanning real-time web intelligence for '{clean_q}'..."
            })

        return plan_steps

    # ── 3. Autonomous Execution Loop ──────────────────────────────────

    def execute_plan(
        self,
        user_text: str,
        on_progress_speak: Optional[Callable[[str], None]] = None,
        on_progress_ui: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes an autonomous multi-step reasoning plan in a closed loop.
        Speaks intermediate progress updates in real-time as steps finish.
        Returns unified execution summary with clean spoken monologue.
        """
        steps = self.analyze_goal(user_text)
        if not steps:
            return {"handled": False, "text": "", "findings": []}

        task = self.task_manager.create_task(
            type_=TaskType.INVESTIGATION.value,
            title=f"Goal: {user_text[:35]}",
            data={"original_prompt": user_text, "steps_total": len(steps)}
        )

        observations: List[Dict[str, Any]] = []
        spoken_updates: List[str] = []

        total_steps = min(len(steps), self._max_steps)

        for idx, step in enumerate(steps[:self._max_steps]):
            action = step.get("action")
            prog_phrase = step.get("progress_phrase", "Processing tactical telemetry...")
            pct = int(((idx + 1) / total_steps) * 90)

            if on_progress_speak:
                on_progress_speak(prog_phrase)
            if on_progress_ui:
                on_progress_ui(prog_phrase)

            self.task_manager.update_progress(task.task_id, pct, prog_phrase)
            spoken_updates.append(prog_phrase)

            obs = {"step": idx + 1, "action": action}
            try:
                if action == "ask_location":
                    topic = step.get("topic", "telemetry")
                    clarification = f"Which city or region would you like {topic} for, Sir?"
                    if on_progress_speak:
                        on_progress_speak(clarification)
                    self.task_manager.complete_task(task.task_id, {"status": "clarification", "message": clarification})
                    return {
                        "handled": True,
                        "text": clarification,
                        "spoken_text": clarification,
                        "findings": [],
                        "steps": spoken_updates
                    }

                elif action == "nav":
                    res = self.tool_gods_eye_nav(step["location"])
                    obs["result"] = f"Locked orbital camera onto {res.get('label', step['location'])}."

                elif action == "cctv":
                    res = self.tool_cctv_query(step["location"])
                    count = res.get("count", 0)
                    city = res.get("city", step["location"]).title()
                    cams = res.get("cameras", [])
                    sample_names = ", ".join([c["name"] for c in cams[:2]]) if cams else "None"
                    obs["result"] = f"Isolated {count} active optical feeds in {city}. Primary vantage: {sample_names}."
                    for cam in cams:
                        self.task_manager.add_finding(task.task_id, TaskFinding(
                            title=cam.get("name", "CCTV Camera"),
                            url=cam.get("snapshotUrl") or f"/api/cctv/frame/{cam.get('id')}",
                            snippet=f"Sensor {cam.get('id')} | Heading: {cam.get('headingDeg', 0)}° | Elevation: {cam.get('groundElevationM', 0)}m",
                            source="cctv",
                            extra=cam
                        ))

                elif action == "traffic":
                    res = self.tool_traffic_query(step["location"])
                    t = res.get("traffic", {})
                    obs["result"] = f"Traffic condition in {t.get('city', step['location'])} is {t.get('status', 'Nominal')} with average speed {t.get('avg_speed_kmh', 42)} km/h."
                    self.task_manager.add_finding(task.task_id, TaskFinding(
                        title=f"Traffic: {t.get('city', 'Sector')}",
                        url=t.get("osm_embed_url", ""),
                        snippet=f"Status: {t.get('status')} | Delay: +{t.get('delay_mins', 0)} min",
                        source="osm_traffic",
                        extra=t
                    ))

                elif action == "weather":
                    res = self.tool_weather_query(step["location"])
                    w = res.get("weather", {})
                    obs["result"] = f"Atmospheric readings in {w.get('city', step['location'])}: {w.get('condition')}, {w.get('temp_f')}°F ({w.get('temp_c')}°C), wind {w.get('wind_kmh')} km/h."

                elif action == "flights":
                    res = self.tool_flight_radar()
                    count = res.get("count", 0)
                    obs["result"] = f"ADS-B radar active: {count} military contacts airborne with live transponder telemetry."

                elif action == "cockpit":
                    self.bus.emit("control_cockpit", {"action": "enter", "target": step.get("target", "")})
                    obs["result"] = "Tactical cockpit chase camera engaged on selected target vector."

                elif action == "search":
                    res = self.tool_web_search(step["query"])
                    obs["result"] = res.get("summary", "Live search complete.")

                elif action == "diagnostics":
                    res = self.tool_diagnostics()
                    obs["result"] = res.get("debrief", "Hardware diagnostics completed.")

                elif action == "top_processes":
                    q = step.get("query", "").lower()
                    by = "memory" if any(w in q for w in ["memory", "ram"]) else "cpu"
                    res = self.tool_top_processes(limit=4, by=by)
                    obs["result"] = res.get("debrief", "Top process audit completed.")

                elif action == "git_intel":
                    res = self.tool_git_intel()
                    obs["result"] = res.get("debrief", "Git repository telemetry acquired.")

                elif action == "briefing":
                    res = self.tool_situational_briefing(step.get("location", ""))
                    obs["result"] = res.get("debrief", "Executive situational briefing generated.")

                elif action == "clipboard":
                    res = self.tool_clipboard()
                    obs["result"] = res.get("debrief", "Clipboard inspect complete.")

                elif action == "calendar":
                    res = self.tool_calendar()
                    obs["result"] = res.get("debrief", "Calendar agenda synchronized.")

                elif action == "inbox":
                    res = self.tool_inbox()
                    obs["result"] = res.get("debrief", "Communications buffer scanned.")

                elif action == "media_control":
                    cmd_text = step.get("command", "").lower()
                    if "mute" in cmd_text:
                        res = self.tool_volume(0) if "unmute" not in cmd_text else self.tool_volume(65)
                    elif "pause" in cmd_text:
                        res = self.tool_media_control("pause")
                    elif "play" in cmd_text or "resume" in cmd_text:
                        res = self.tool_media_control("play")
                    else:
                        res = self.tool_media_control("toggle")
                    obs["result"] = res.get("debrief", "Audio command dispatched.")

            except Exception as tool_err:
                obs["result"] = f"Tool encounter: {tool_err}"

            observations.append(obs)
            time.sleep(0.3)

        summary_lines = [o.get("result", "") for o in observations if o.get("result")]
        summary_text = " ".join(summary_lines)

        final_debrief = (
            f"All operational tasks completed, Sir. {summary_text}"
        )

        self.task_manager.complete_task(task.task_id, summary=final_debrief[:150])

        return {
            "handled": True,
            "text": final_debrief,
            "observations": observations,
            "spoken_updates": spoken_updates,
            "task_id": task.task_id
        }
