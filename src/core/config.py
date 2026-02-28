from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    part: str
    ter_mode: str
    sat_mode: str
    load: str
    connectivity_override: str


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    canonical_id: str
    part: str
    ter_mode: str
    sat_mode: str
    load: str
    train_count: int
    connectivity_override: str
    seed: int
    version_string: str
    config_hash: str


def load_manifest(path: str | Path) -> Dict[str, Any]:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    return manifest


def get_run_specs(manifest: Dict[str, Any]) -> List[RunSpec]:
    specs: List[RunSpec] = []
    for run in manifest.get("runs", []):
        specs.append(
            RunSpec(
                run_id=run["id"],
                part=run["part"],
                ter_mode=run["ter_mode"],
                sat_mode=run["sat_mode"],
                load=run["load"],
                connectivity_override=run.get("connectivity_override", "DEFAULT"),
            )
        )
    return specs


def derive_steps(manifest: Dict[str, Any]) -> int:
    dt_ms = manifest["simulation"]["dt_ms"]
    duration_min = manifest["simulation"]["duration_min"]
    return int((duration_min * 60 * 1000) / dt_ms)


def sat_edge_fraction(sat_mode: str) -> Optional[float]:
    if sat_mode.startswith("SAT_GW_EDGE_p"):
        try:
            return float(sat_mode.split("_p", 1)[1])
        except ValueError:
            return None
    return None
