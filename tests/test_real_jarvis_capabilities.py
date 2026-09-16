# tests/test_real_jarvis_capabilities.py
"""
Unit tests validating J.A.R.V.I.S.'s authentic real-system capabilities:
1. Real hardware diagnostics (SystemDiagnosticsEngine via psutil).
2. Real local document/file search (CloudDocumentManager replacing static PDF mocks).
3. Real OSRM driving navigation & geodesic calculation (MapsNavigationEngine).
4. Persona alignment and verbal debrief integrity (Stark voice, Sir addressing, zero slang).
"""

import os
import pytest
from modules.system_diagnostics import SystemDiagnosticsEngine
from modules.cloud_docs import CloudDocumentManager
from modules.maps_nav import MapsNavigationEngine
from modules.calendar_intel import CalendarIntelManager
from modules.smart_home import SmartHomeManager
from core.system_skills import SystemSkillEngine
from narrative.jarvis_voice import JarvisVoice


class TestSystemDiagnostics:
    def setup_method(self):
        self.engine = SystemDiagnosticsEngine()

    def test_hardware_metrics_structure(self):
        metrics = self.engine.get_metrics()
        assert isinstance(metrics, dict)
        assert "cpu_percent" in metrics
        assert "ram_total_gb" in metrics
        assert "disk_total_gb" in metrics
        assert "thermals" in metrics
        assert "battery" in metrics
        assert "top_processes" in metrics
        assert "uptime_hours" in metrics

        # Verify real values from host
        assert metrics["cpu_percent"] >= 0.0
        assert metrics["ram_total_gb"] > 0.0
        assert metrics["ram_percent"] >= 0.0
        assert metrics["disk_total_gb"] > 0.0
        assert isinstance(metrics["top_processes"], list)

    def test_spoken_briefing_persona(self):
        metrics = self.engine.get_metrics()
        briefing = self.engine.format_tactical_debrief(metrics)
        assert isinstance(briefing, str)
        assert len(briefing) > 10
        # Must address operator as Sir
        assert "Sir" in briefing
        # Zero vulgarity or slang
        for taboo in ["dumbass", "dipshit", "buddy", "bruh", "partner"]:
            assert taboo not in briefing.lower()

    def test_hud_payload_generation(self):
        metrics = self.engine.get_metrics()
        payload = self.engine.build_hud_payload(metrics)
        assert isinstance(payload, dict)
        assert payload.get("action_type") == "DIAGNOSTIC"
        assert "findings" in payload
        assert "spoken_tl_dr" in payload


class TestRealDocumentSearch:
    def setup_method(self):
        self.doc_mgr = CloudDocumentManager()

    def test_real_workspace_file_indexing(self):
        # Search for README which exists in the workspace
        res = self.doc_mgr.search_documents("README")
        assert isinstance(res, list)
        assert len(res) > 0

        # Check structure of matched document
        first = res[0]
        assert "filename" in first
        assert "path" in first
        assert "size_kb" in first
        assert "summary" in first
        assert os.path.exists(first["path"])

    def test_code_file_search(self):
        # Search for jarvis
        res = self.doc_mgr.search_documents("jarvis")
        assert len(res) > 0
        filenames = [d["filename"] for d in res]
        assert any("jarvis.py" in f for f in filenames)

    def test_no_synthetic_pdf_mocks(self):
        # The old static mock had Stark_Industries_Q3_Financials.pdf
        res = self.doc_mgr.search_documents("Stark_Industries_Q3_Financials")
        assert len(res) == 0

    def test_read_document_summary_persona(self):
        summary = self.doc_mgr.get_document_summary("README")
        assert isinstance(summary, str)
        assert "Sir" in summary
        assert "README" in summary


class TestRealNavigationEngine:
    def setup_method(self):
        self.nav = MapsNavigationEngine()

    def test_distance_and_route_calculation(self):
        # Chennai to Bengaluru
        route = self.nav.get_route_directions("Bengaluru", origin="Chennai")
        assert route["distance_km"] > 250.0
        assert route["distance_km"] < 450.0
        assert "steps" in route
        assert len(route["steps"]) > 0
        assert "jarvis_prompts" in route

    def test_spoken_directions_persona(self):
        route = self.nav.get_route_directions("Bengaluru", origin="Chennai")
        prompts = " ".join(route["jarvis_prompts"])
        assert "Sir" in prompts
        for taboo in ["dumbass", "dipshit", "bruh", "buddy"]:
            assert taboo not in prompts.lower()

    def test_poi_search(self):
        # Search for hospitals in Chennai
        pois = self.nav.search_nearby_poi("hospital", target_city="Chennai")
        assert isinstance(pois, list)
        # Should return a list with elements (either from Nominatim or local fallback)
        assert len(pois) > 0
        assert "name" in pois[0]


class TestPersonaAndVoiceIntegrity:
    def test_calendar_intel_stark_tone(self):
        cal = CalendarIntelManager()
        reminders = cal.format_jarvis_reminders()
        assert isinstance(reminders, str)
        for taboo in ["dumbass", "dipshit", "bruh", "buddy"]:
            assert taboo not in reminders.lower()

    def test_smart_home_welcome_stark_tone(self):
        home = SmartHomeManager()
        welcome = home.handle_arrival()
        assert "Sir" in welcome
        assert "bastard" not in welcome.lower()

    def test_system_skills_diagnostics_dispatch(self):
        skills = SystemSkillEngine()
        handled, speech, is_search, query, payload = skills.try_execute("system diagnostic")
        assert handled is True
        assert "Sir" in speech
        assert payload.get("action_type") == "DIAGNOSTIC"

    def test_voice_sanitizer_cleans_dean_to_sir(self):
        # Test Dean name replacement
        voice = JarvisVoice()
        cleaned = voice._clean_reasoning("Good morning Dean, all systems are operational.")
        assert "Dean" not in cleaned
        assert "Sir" in cleaned
