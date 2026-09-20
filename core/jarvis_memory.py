import os
import json
import time

MEMORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jarvis_memory.json")

class JarvisMemory:
    def __init__(self, filepath=MEMORY_FILE_PATH):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        default_skills = [
            {
                "name": "open_app",
                "description": "Launch desktop applications (browser, terminal, editor, etc.)",
                "trigger": "open app"
            },
            {
                "name": "google_search",
                "description": "Search Google in default browser with structured snippet extraction",
                "trigger": "google search"
            },
            {
                "name": "calendar_intel",
                "description": "Check schedule, reminders, double-bookings, auto-reschedule",
                "trigger": "calendar"
            },
            {
                "name": "inbox_intel",
                "description": "Read-only urgent inbox scan and TL;DR summaries",
                "trigger": "inbox scan"
            },
            {
                "name": "maps_nav",
                "description": "Live navigation, rerouting around traffic, 24hr taco spot search",
                "trigger": "find tacos"
            },
            {
                "name": "cloud_docs",
                "description": "Search Google Drive/Dropbox files and read key points",
                "trigger": "find document"
            },
            {
                "name": "smart_home",
                "description": "Control lights, thermostat, front door lock, arrival macro",
                "trigger": "I'm home"
            },
            {
                "name": "self_upgrade",
                "description": "Inspect own code files, mistake audit, versioned rollback, auto-retrain",
                "trigger": "audit code"
            },
            {
                "name": "jarvis_action_hud",
                "description": "J.A.R.V.I.S. holographic action HUD, multi-card findings grid, breaking news badges, sentiment color coding, and raw JSON schema toggle",
                "trigger": "open panel"
            }
        ]

        data = None
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None

        if not data:
            data = {
                "user_speech_patterns": [
                    "Always address the operator as 'Sir'.",
                    "Maintain understated British elegance, razor wit, and mathematical precision.",
                    "STT acoustic tuning for JARVIS wake recognition."
                ],
                "failures_and_lessons": [
                    "Speech recognition of target identifiers is error-prone; trigger target dialog modal when intent is 'investigate' without clean target."
                ],
                "learned_skills": default_skills,
                "history_log": []
            }
        else:
            # Sync default skills so all 9 executive capabilities are active
            existing = data.setdefault("learned_skills", [])
            existing_names = {s.get("name") for s in existing}
            for ds in default_skills:
                if ds["name"] not in existing_names:
                    existing.append(ds)

        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def load_memory(self):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[JarvisMemory] Error loading memory: {e}")
            return {}

    def log_speech_pattern(self, note: str):
        mem = self.load_memory()
        patterns = mem.setdefault("user_speech_patterns", [])
        if note not in patterns:
            patterns.append(note)
            self._save(mem)

    def log_failure_lesson(self, failure_and_lesson: str):
        mem = self.load_memory()
        lessons = mem.setdefault("failures_and_lessons", [])
        if failure_and_lesson not in lessons:
            lessons.append(failure_and_lesson)
            self._save(mem)

    def register_learned_skill(self, skill_name: str, description: str, trigger: str, code_snippet: str = ""):
        mem = self.load_memory()
        skills = mem.setdefault("learned_skills", [])
        for s in skills:
            if s.get("name") == skill_name:
                s["description"] = description
                s["trigger"] = trigger
                if code_snippet:
                    s["code"] = code_snippet
                self._save(mem)
                return
        skills.append({
            "name": skill_name,
            "description": description,
            "trigger": trigger,
            "code": code_snippet,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save(mem)

    def get_salutation(self) -> str:
        mem = self.load_memory()
        return mem.get("operator_salutation") or "Sir"

    def set_salutation(self, salutation: str) -> str:
        if not salutation:
            return "Sir"
        clean_sal = salutation.strip()
        if clean_sal.lower() in ("ma'am", "maam"):
            clean_sal = "Ma'am"
        elif clean_sal.lower() in ("madam", "madame"):
            clean_sal = "Madam"
        elif clean_sal.lower() in ("lady", "miss"):
            clean_sal = clean_sal.title()
        elif clean_sal.lower() == "sir":
            clean_sal = "Sir"
        else:
            clean_sal = clean_sal.title()

        mem = self.load_memory()
        mem["operator_salutation"] = clean_sal
        patterns = mem.setdefault("user_speech_patterns", [])
        new_patterns = [p for p in patterns if "address the operator as" not in p.lower()]
        new_patterns.insert(0, f"Always address the operator as '{clean_sal}'.")
        mem["user_speech_patterns"] = new_patterns
        self._save(mem)
        return clean_sal

    def get_recent_speech_patterns(self, limit: int = 5) -> list:
        mem = self.load_memory()
        rules = mem.get("custom_rules", [])
        patterns = mem.get("user_speech_patterns", [])
        history = mem.get("history_log", [])
        combined = []
        for r in reversed(rules):
            if r and r not in combined:
                combined.append(f"Custom Rule: {r}")
        for p in reversed(patterns):
            if p and p not in combined:
                combined.append(p)
        for h in reversed(history):
            if isinstance(h, dict) and h.get("entry") and h.get("entry") not in combined:
                combined.append(h["entry"])
        return combined[:limit]

    def store_custom_rule(self, rule_text: str) -> bool:
        """Stores a persistent operator semantic rule or custom phrase definition."""
        if not rule_text or not str(rule_text).strip():
            return False
        clean = str(rule_text).strip()
        mem = self.load_memory()
        rules = mem.setdefault("custom_rules", [])
        if clean not in rules:
            rules.append(clean)
        # Also record in speech patterns for immediate prompt awareness
        patterns = mem.setdefault("user_speech_patterns", [])
        rule_desc = f"Operator rule / phrase definition: {clean}"
        if rule_desc not in patterns:
            patterns.append(rule_desc)
        self._save(mem)

        # Also sync to LessonsStore so semantic RAG / false-positive memory has it
        try:
            from memory.lessons_store import LessonsStore
            LessonsStore().add_lesson(
                trigger=clean[:80],
                lesson=clean,
                platform="operator_rules",
                context="custom_semantic_rule"
            )
        except Exception:
            pass
        return True

    def store_memory(self, category: str, text: str) -> bool:
        if not text:
            return False
        mem = self.load_memory()
        history = mem.setdefault("history_log", [])
        history.append({
            "category": category,
            "entry": text,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save(mem)
        return True

    def get_memory_summary_for_prompt(self):
        mem = self.load_memory()
        sal = self.get_salutation()
        patterns = "\n- ".join(mem.get("user_speech_patterns", [])[-4:])
        rules = "\n- ".join(mem.get("custom_rules", [])[-6:]) if mem.get("custom_rules") else "No custom phrase rules defined yet."
        lessons = "\n- ".join(mem.get("failures_and_lessons", [])[-4:])
        skills = ", ".join([s["name"] for s in mem.get("learned_skills", [])])
        return f"""PERSISTENT MEMORY & LEARNED SKILLS:
- Current Operator Salutation: Always address the operator as '{sal}'.
- Operator Custom Rules & Phrase Meanings:
- {rules}
- User Speech Habits:
- {patterns}
- Learned Lessons & Fixes:
- {lessons}
- Available Learned Skills: {skills} (open_app, google_search, calendar_intel, inbox_intel, maps_nav, cloud_docs, smart_home, self_upgrade, jarvis_action_hud)
- Holographic Panel Capability: Wired and active. When user asks to open the action panel or view search/audit findings, open_jarvis_panel and jarvis_structured_json_feed render dynamic multi-card overlays in the Action HUD."""

    def _save(self, data):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[JarvisMemory] Error saving memory: {e}")


