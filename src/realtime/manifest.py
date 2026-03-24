from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    csv_path: Path
    slot_ms: int


def load_realtime_manifest(path: Path) -> Dict[str, ScenarioConfig]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("realtime_manifest.json must be a JSON object")

    scenarios: Dict[str, ScenarioConfig] = {}
    base_dir = Path.cwd()
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        csv_path = cfg.get("csv_path")
        if not csv_path:
            continue
        slot_ms = int(cfg.get("slot_ms", 1000))
        csv_path_resolved = Path(csv_path)
        if not csv_path_resolved.is_absolute():
            csv_path_resolved = base_dir / csv_path_resolved

        scenarios[name] = ScenarioConfig(
            name=name,
            csv_path=csv_path_resolved,
            slot_ms=slot_ms,
        )

    scenario_root = Path(os.getenv("SIM_SCENARIO_DIR", "scenarios"))
    if not scenario_root.is_absolute():
        scenario_root = base_dir / scenario_root
    edge_dir = scenario_root / "edge" if (scenario_root / "edge").is_dir() else scenario_root
    if edge_dir.exists():
        for csv_path in sorted(edge_dir.glob("*.csv")):
            name = csv_path.stem
            if name in scenarios:
                continue
            scenarios[name] = ScenarioConfig(
                name=name,
                csv_path=csv_path,
                slot_ms=1000,
            )

    if not scenarios:
        raise ValueError("No scenarios found in realtime_manifest.json")
    return scenarios
