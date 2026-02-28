from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from src.core.config import RunConfig, RunSpec, get_run_specs, sat_edge_fraction


@dataclass(frozen=True)
class PlannedRun:
    spec: RunSpec
    canonical_id: str


def _validate_run(spec: RunSpec) -> None:
    if spec.sat_mode == "SAT_TRANSPARENT" and spec.ter_mode is None:
        raise ValueError("SAT_TRANSPARENT requires a terrestrial mode")
    if spec.connectivity_override == "LEO_ONLY_STRICT" and spec.ter_mode != "TER_NO_EDGE":
        raise ValueError("LEO_ONLY_STRICT requires TER_NO_EDGE")
    if spec.sat_mode.startswith("SAT_GW_EDGE_p"):
        fraction = sat_edge_fraction(spec.sat_mode)
        if fraction is None or fraction <= 0 or fraction > 1:
            raise ValueError(f"Invalid satellite edge fraction in {spec.sat_mode}")


def plan_runs(manifest: Dict[str, Any]) -> Tuple[List[PlannedRun], Dict[str, str]]:
    specs = get_run_specs(manifest)
    canonical_map: Dict[Tuple[str, str, str, str], str] = {}
    alias_map: Dict[str, str] = {}
    planned: List[PlannedRun] = []
    for spec in specs:
        _validate_run(spec)
        key = (spec.ter_mode, spec.sat_mode, spec.load, spec.connectivity_override)
        if key in canonical_map:
            alias_map[spec.run_id] = canonical_map[key]
            continue
        canonical_map[key] = spec.run_id
        planned.append(PlannedRun(spec=spec, canonical_id=spec.run_id))
    for spec in specs:
        alias_map.setdefault(spec.run_id, spec.run_id)
    return planned, alias_map


def build_run_configs(
    planned: List[PlannedRun],
    manifest: Dict[str, Any],
    config_hash: str,
) -> List[RunConfig]:
    seeds = manifest["seed_list"]
    loads = manifest["loads"]
    run_configs: List[RunConfig] = []
    for plan in planned:
        spec = plan.spec
        train_count = loads[spec.load]
        for seed in seeds:
            run_configs.append(
                RunConfig(
                    run_id=spec.run_id,
                    canonical_id=plan.canonical_id,
                    part=spec.part,
                    ter_mode=spec.ter_mode,
                    sat_mode=spec.sat_mode,
                    load=spec.load,
                    train_count=train_count,
                    connectivity_override=spec.connectivity_override,
                    seed=seed,
                    version_string=manifest["version_string"],
                    config_hash=config_hash,
                )
            )
    return run_configs
