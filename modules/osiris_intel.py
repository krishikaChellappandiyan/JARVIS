# modules/osiris_intel.py
"""
OSIRIS Intelligence Platform Engine for J.A.R.V.I.S.
Connects J.A.R.V.I.S. directly to the OSIRIS Global Intelligence Platform (https://osirisai.live).

Capabilities:
- 28,400+ Georeferenced CCTV Cameras (YouTube Live, HLS, MJPEG)
- Real-Time Aviation: Commercial, Military Flights, Private Jets & GPS Jamming Sectors
- 18,800+ Orbital Satellites with TLE Telemetry & Pass Predictions
- Active Warzones, Frontline Geometry & Live Conflict Incident Reporting
- Turn-by-Turn Valhalla/OSRM Street Navigation
- OSINT Cyber RECON (DNS, WHOIS, SSL Certs, IP/ASN, Shodan, CVEs, Sanctions)
- Real-Time Environmental & Space Weather Telemetry
"""

import os
import json
import math
import time
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("JarvisOsiris")

DEFAULT_OSIRIS_URL = "https://osirisai.live"
CACHE_DIR = Path.home() / ".jarvis" / "osiris_cache"

# TTL in seconds for specific endpoints
DEFAULT_TTLS = {
    "stats": 10,
    "flights": 15,
    "satellites": 30,
    "conflicts": 60,
    "cctv": 600,         # 10 minutes (static 28k camera network)
    "directions": 300,
    "osint": 300,
    "maritime": 60,
    "news": 120,
    "space_weather": 180,
    "infrastructure": 600,
}


class OsirisIntelClient:
    """Singleton client managing connectivity to OSIRIS Global Intelligence."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(OsirisIntelClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, base_url: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return
        self.base_url = (base_url or os.environ.get("OSIRIS_API_URL") or DEFAULT_OSIRIS_URL).rstrip("/")
        self._cache_mem: Dict[str, Tuple[float, Any]] = {}
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._initialized = True

    # -------------------------------------------------------------------------
    # Caching & HTTP Transport
    # -------------------------------------------------------------------------

    def _get_cache(self, key: str, ttl: float) -> Optional[Any]:
        """Check in-memory and disk cache for fresh response."""
        now = time.time()
        # 1. Memory check
        if key in self._cache_mem:
            exp, data = self._cache_mem[key]
            if now < exp:
                return data

        # 2. Disk check
        disk_path = CACHE_DIR / f"{key}.json"
        if disk_path.exists():
            try:
                with open(disk_path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                    if now < entry.get("expires_at", 0):
                        self._cache_mem[key] = (entry["expires_at"], entry["data"])
                        return entry["data"]
            except Exception as e:
                logger.debug(f"[OSIRIS] Cache read failed for {key}: {e}")

        return None

    def _set_cache(self, key: str, data: Any, ttl: float):
        """Save response to in-memory and disk cache."""
        exp = time.time() + ttl
        self._cache_mem[key] = (exp, data)
        disk_path = CACHE_DIR / f"{key}.json"
        try:
            with open(disk_path, "w", encoding="utf-8") as f:
                json.dump({"expires_at": exp, "data": data}, f)
        except Exception as e:
            logger.debug(f"[OSIRIS] Cache write failed for {key}: {e}")

    def _fetch_endpoint(self, path: str, params: Optional[Dict[str, Any]] = None, ttl: float = 30) -> Optional[Any]:
        """Perform HTTP GET against an OSIRIS endpoint with caching and error protection."""
        url = f"{self.base_url}{path}"
        if params:
            query_str = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query_str:
                url = f"{url}?{query_str}"

        safe_key = urllib.parse.quote(f"{path}_{json.dumps(params or {}, sort_keys=True)}", safe="")[:120]
        cached = self._get_cache(safe_key, ttl)
        if cached is not None:
            return cached

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) JARVIS-Tactical/2.0",
                "Accept": "application/json, text/plain, */*"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=7.0) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                self._set_cache(safe_key, data, ttl)
                return data
        except Exception as e:
            logger.warning(f"[OSIRIS] Request failed for {url}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Core Telemetry & Intelligence Endpoints
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Retrieve live aggregate counters across all OSIRIS streams."""
        res = self._fetch_endpoint("/api/stats", ttl=DEFAULT_TTLS["stats"])
        if res and "stats" in res:
            return res["stats"]
        return {"flights": 0, "sats": 0, "cctv": 0, "weather": 0, "nuclear": 0, "incidents": 0}

    def get_cctv_cameras(
        self,
        city: Optional[str] = None,
        country: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        radius_km: Optional[float] = None,
        query: Optional[str] = None,
        limit: int = 40
    ) -> List[Dict[str, Any]]:
        """
        Query OSIRIS worldwide CCTV registry (28,400+ cameras).
        Supports geographic distance filtering and keyword filtering.
        """
        res = self._fetch_endpoint("/api/cctv", ttl=DEFAULT_TTLS["cctv"])
        if not res or "cameras" not in res:
            return []

        cameras: List[Dict[str, Any]] = res.get("cameras", [])
        filtered = []

        q_lower = (query or "").lower().strip()
        city_lower = (city or "").lower().strip()
        country_lower = (country or "").lower().strip()

        for cam in cameras:
            c_name = cam.get("name", "").lower()
            c_city = cam.get("city", "").lower()
            c_country = cam.get("country", "").lower()
            c_lat = cam.get("lat")
            c_lng = cam.get("lng")

            # City filter
            if city_lower and city_lower not in c_city and city_lower not in c_name:
                continue

            # Country filter
            if country_lower and country_lower not in c_country:
                continue

            # Keyword filter
            if q_lower and (q_lower not in c_name and q_lower not in c_city and q_lower not in c_country):
                continue

            # Radial distance filter
            if lat is not None and lon is not None and radius_km is not None and c_lat is not None and c_lng is not None:
                dist = self.haversine_distance(lat, lon, c_lat, c_lng)
                if dist > radius_km:
                    continue
                cam["distance_km"] = round(dist, 1)

            filtered.append(cam)

        # Sort by distance if coordinate biased
        if lat is not None and lon is not None:
            filtered.sort(key=lambda x: x.get("distance_km", 999999))

        return filtered[:limit]

    def get_flights(self, military_only: bool = False, bounds: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Ingest real-time global flights, separating military and commercial tracks.
        """
        res = self._fetch_endpoint("/api/flights", ttl=DEFAULT_TTLS["flights"])
        if not res:
            return {"total": 0, "military": [], "commercial": [], "private": [], "gps_jamming": []}

        mil = res.get("military_flights", [])
        com = res.get("commercial_flights", [])
        priv = res.get("private_flights", [])
        jam = res.get("gps_jamming", [])

        if military_only:
            return {
                "total": len(mil),
                "military": mil,
                "commercial": [],
                "private": [],
                "gps_jamming": jam
            }

        return {
            "total": res.get("total", len(mil) + len(com) + len(priv)),
            "military": mil,
            "commercial": com,
            "private": priv,
            "gps_jamming": jam
        }

    def get_satellites(self, query: Optional[str] = None, category: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve tracked satellites (18,800+ orbital objects) with real-time TLE positions.
        """
        res = self._fetch_endpoint("/api/satellites", ttl=DEFAULT_TTLS["satellites"])
        if not res or "satellites" not in res:
            return []

        sats: List[Dict[str, Any]] = res.get("satellites", [])
        filtered = []

        q_lower = (query or "").lower().strip()
        cat_lower = (category or "").lower().strip()

        for sat in sats:
            s_name = sat.get("name", "").lower()
            s_cat = sat.get("category", "").lower()
            s_mission = sat.get("mission", "").lower()

            if q_lower and (q_lower not in s_name and q_lower not in s_mission):
                continue

            if cat_lower and cat_lower not in s_cat:
                continue

            filtered.append(sat)
            if len(filtered) >= limit:
                break

        return filtered

    def get_conflicts(self) -> Dict[str, Any]:
        """
        Retrieve active warzones, live frontlines, and conflict events.
        """
        res = self._fetch_endpoint("/api/conflicts", ttl=DEFAULT_TTLS["conflicts"])
        if not res:
            return {"totalZones": 0, "activeWarzones": 0, "zones": [], "liveEvents": []}

        return {
            "totalZones": res.get("totalZones", 0),
            "activeWarzones": res.get("activeWarzones", 0),
            "zones": res.get("zones", []),
            "liveEvents": res.get("liveEvents", [])
        }

    def get_frontlines(self) -> Dict[str, Any]:
        """Retrieve frontline polygon geometry for active theatres."""
        res = self._fetch_endpoint("/api/frontlines", ttl=DEFAULT_TTLS["conflicts"])
        return res or {"frontlines": {}}

    def get_turn_by_turn_route(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        mode: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """
        Query OSIRIS Valhalla/OSRM turn-by-turn routing engine for true road geometry.
        """
        params = {
            "from": f"{from_lat},{from_lon}",
            "to": f"{to_lat},{to_lon}",
            "mode": mode
        }
        res = self._fetch_endpoint("/api/directions", params=params, ttl=DEFAULT_TTLS["directions"])
        if not res:
            return None

        return res

    def get_cyber_recon(self, target: str, lookup_type: str = "all") -> Dict[str, Any]:
        """
        Perform fast OSINT reconnaissance via OSIRIS RECON toolkit endpoints.
        """
        results: Dict[str, Any] = {"target": target, "timestamp": time.time()}

        # 1. IP / Domain Intelligence
        is_ip = target.replace(".", "").isdigit()
        if is_ip:
            ip_res = self._fetch_endpoint(f"/api/osint/ip", params={"ip": target}, ttl=DEFAULT_TTLS["osint"])
            if ip_res:
                results["ip_info"] = ip_res
        else:
            dns_res = self._fetch_endpoint(f"/api/osint/dns", params={"domain": target}, ttl=DEFAULT_TTLS["osint"])
            if dns_res:
                results["dns"] = dns_res

            certs_res = self._fetch_endpoint(f"/api/osint/certs", params={"domain": target}, ttl=DEFAULT_TTLS["osint"])
            if certs_res:
                results["certificates"] = certs_res

            whois_res = self._fetch_endpoint(f"/api/osint/whois", params={"domain": target}, ttl=DEFAULT_TTLS["osint"])
            if whois_res:
                results["whois"] = whois_res

        # 2. Shodan Vulnerabilities
        shodan_res = self._fetch_endpoint(f"/api/osint/shodan", params={"host": target}, ttl=DEFAULT_TTLS["osint"])
        if shodan_res:
            results["shodan"] = shodan_res

        # 3. Sanctions check
        sanctions_res = self._fetch_endpoint(f"/api/osint/sanctions", params={"query": target}, ttl=DEFAULT_TTLS["osint"])
        if sanctions_res:
            results["sanctions"] = sanctions_res

        return results

    def get_live_news(self) -> List[Dict[str, Any]]:
        """Retrieve 24/7 global SIGINT broadcast streams."""
        res = self._fetch_endpoint("/api/live-news", ttl=DEFAULT_TTLS["news"])
        if res and "feeds" in res:
            return res["feeds"]
        return []

    def get_space_weather(self) -> Dict[str, Any]:
        """Retrieve solar flare activity and geomagnetic conditions from NOAA SWPC."""
        res = self._fetch_endpoint("/api/space-weather", ttl=DEFAULT_TTLS["space_weather"])
        return res or {}

    def get_maritime(self) -> Dict[str, Any]:
        """Retrieve maritime ports, strategic chokepoints, and vessel traffic."""
        res = self._fetch_endpoint("/api/maritime", ttl=DEFAULT_TTLS["maritime"])
        return res or {"ports": [], "chokepoints": [], "ships": []}

    def get_infrastructure(self) -> List[Dict[str, Any]]:
        """Retrieve critical infrastructure: nuclear facilities and power plants."""
        res = self._fetch_endpoint("/api/infrastructure", ttl=DEFAULT_TTLS["infrastructure"])
        if res and isinstance(res, list):
            return res
        return []

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great circle distance in kilometers between two coordinates."""
        R = 6371.0  # Earth radius in kilometers
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c


# Global Singleton Accessor
_osiris_client: Optional[OsirisIntelClient] = None

def get_osiris_client() -> OsirisIntelClient:
    global _osiris_client
    if _osiris_client is None:
        _osiris_client = OsirisIntelClient()
    return _osiris_client
