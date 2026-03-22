from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class SecurityScenarioConfig:
    name: str
    attack_csv_path: Path
    baseline_csv_path: Path
    attack_type: str
    target_segment: str
    slot_ms: int


def load_security_manifest(path: Path) -> Dict[str, SecurityScenarioConfig]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("security_manifest.json must be a JSON object")

    scenarios: Dict[str, SecurityScenarioConfig] = {}
    base_dir = Path.cwd()
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        attack_csv = cfg.get("attack_csv_path") or cfg.get("csv_path")
        if not attack_csv:
            continue
        baseline_csv = cfg.get("baseline_csv_path") or cfg.get("baseline_path")
        if not baseline_csv:
            baseline_csv = "scenarios/example_scenario.csv"
        slot_ms = int(cfg.get("slot_ms", 1000))
        attack_type = str(cfg.get("attack_type") or "generic")
        target_segment = str(cfg.get("target_segment") or cfg.get("target") or "5g")

        attack_csv_path = Path(attack_csv)
        if not attack_csv_path.is_absolute():
            attack_csv_path = base_dir / attack_csv_path
        baseline_csv_path = Path(baseline_csv)
        if not baseline_csv_path.is_absolute():
            baseline_csv_path = base_dir / baseline_csv_path

        scenarios[name] = SecurityScenarioConfig(
            name=name,
            attack_csv_path=attack_csv_path,
            baseline_csv_path=baseline_csv_path,
            attack_type=attack_type,
            target_segment=target_segment,
            slot_ms=slot_ms,
        )

    if not scenarios:
        raise ValueError("No scenarios found in security_manifest.json")
    return scenarios
