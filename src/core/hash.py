from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def manifest_hash(manifest: Dict[str, Any]) -> str:
    payload = {
        "manifest_version": manifest.get("manifest_version"),
        "version_string": manifest.get("version_string"),
        "seed_list": manifest.get("seed_list"),
        "allocation_policy": manifest.get("allocation_policy"),
        "detour_policy": manifest.get("detour_policy"),
        "access_policy": manifest.get("access_policy"),
        "corridor": {
            "segment_lengths_km": manifest.get("corridor", {}).get("segment_lengths_km"),
            "segment_type_weights": manifest.get("corridor", {}).get("segment_type_weights"),
            "tunnel_mode": manifest.get("corridor", {}).get("tunnel_mode"),
        },
        "traffic": manifest.get("traffic"),
        "network_profiles": manifest.get("network_profiles"),
        "topology": manifest.get("topology"),
        "compute_profiles": manifest.get("compute_profiles"),
        "kpi_thresholds": manifest.get("kpi_thresholds"),
        "simulation": manifest.get("simulation"),
        "beam_switch": manifest.get("beam_switch"),
        "connectivity": manifest.get("connectivity"),
        "runs": manifest.get("runs"),
        "loads": manifest.get("loads"),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
