from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from src.core.config import load_manifest
from src.core.engine import run_simulation
from src.core.hash import manifest_hash
from src.core.planner import build_run_configs, plan_runs


def _write_run_manifest(
    output_dir: Path,
    manifest_path: Path,
    config_hash: str,
    seed_list: list,
    version_string: str,
    alias_map: dict,
    planned_runs: list,
) -> None:
    manifest_data = {
        "manifest_path": str(manifest_path),
        "config_hash": config_hash,
        "seed_list": seed_list,
        "version_string": version_string,
        "alias_map": alias_map,
        "planned_runs": planned_runs,
    }
    aggregated_dir = output_dir / "_aggregated"
    aggregated_dir.mkdir(parents=True, exist_ok=True)
    with (aggregated_dir / "run_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest_data, handle, indent=2, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default="runs")
    parser.add_argument("--only", default=None)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(manifest_path)
    config_hash = manifest_hash(manifest)
    planned_runs, alias_map = plan_runs(manifest)

    planned_info = []
    for plan in planned_runs:
        spec = plan.spec
        planned_info.append(
            {
                "canonical_id": plan.canonical_id,
                "run_id": spec.run_id,
                "ter_mode": spec.ter_mode,
                "sat_mode": spec.sat_mode,
                "load": spec.load,
                "connectivity_override": spec.connectivity_override,
            }
        )

    _write_run_manifest(
        output_dir,
        manifest_path,
        config_hash,
        manifest["seed_list"],
        manifest["version_string"],
        alias_map,
        planned_info,
    )

    run_configs = build_run_configs(planned_runs, manifest, config_hash)
    if args.only:
        canonical_only = alias_map.get(args.only, args.only)
        run_configs = [rc for rc in run_configs if rc.canonical_id == canonical_only]

    for rc in run_configs:
        run_root = output_dir / rc.canonical_id
        seed_dir = run_root / f"seed_{rc.seed}"
        seed_dir.mkdir(parents=True, exist_ok=True)

        summary_path = seed_dir / "summary.json"
        if summary_path.exists():
            continue

        metadata = {
            "run_id": rc.run_id,
            "canonical_id": rc.canonical_id,
            "seed": rc.seed,
            "config_hash": rc.config_hash,
            "version_string": rc.version_string,
            "manifest_path": str(manifest_path),
        }
        with (seed_dir / "run_metadata.json").open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)

        freeze = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            check=False,
        )
        (seed_dir / "pip_freeze.txt").write_text(freeze.stdout, encoding="utf-8")

        run_simulation(rc, manifest, seed_dir)

    for run_id, canonical_id in alias_map.items():
        if run_id == canonical_id:
            continue
        alias_dir = output_dir / run_id
        alias_dir.mkdir(parents=True, exist_ok=True)
        with (alias_dir / "ALIAS_OF").open("w", encoding="utf-8") as handle:
            handle.write(f"{canonical_id}\n")


if __name__ == "__main__":
    main()
