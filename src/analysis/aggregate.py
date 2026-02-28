from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd


def _load_manifest(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _collect_seed_summaries(runs_dir: Path) -> pd.DataFrame:
    records: List[Dict] = []
    for summary_path in runs_dir.glob("*/seed_*/summary.json"):
        with summary_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        records.append(data)
    return pd.DataFrame.from_records(records)


def _aggregate_config_metrics(seed_df: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "compliance_global",
        "compliance_worst_train",
        "p50_e2e_latency",
        "p95_e2e_latency",
        "p99_e2e_latency",
        "p999_e2e_latency",
        "p95_latency_voice",
        "p95_latency_video",
        "mean_compute_utilization",
        "mean_access_latency",
        "mean_transport_to_edge",
        "mean_compute_latency",
        "mean_transport_return",
        "mean_detour_latency",
        "p_spike_mean",
        "spike_count",
        "access_queue_p95",
        "p95_access_latency",
        "p99_access_latency",
        "p999_access_latency",
        "detour_time_fraction",
        "detour_packet_ratio",
        "detour_added_latency_p95",
        "detour_added_latency_p99",
        "detour_link_queue_p95",
        "detour_volume_mb",
        "avg_compute_queue_occupancy",
        "avg_shaping_queue_occupancy",
        "total_compute_time_s",
        "active_edge_nodes",
    ]
    grouped = seed_df.groupby("config_id", as_index=False)
    agg = grouped[metrics].agg(["mean", "std"]).reset_index()

    agg.columns = [
        "config_id" if col[0] == "config_id" else f"{col[0]}_{col[1]}" for col in agg.columns
    ]
    for metric in metrics:
        std_col = f"{metric}_std"
        ci_col = f"{metric}_ci95"
        counts = seed_df.groupby("config_id")[metric].count().reset_index().rename(columns={metric: "count"})
        agg = agg.merge(counts, on="config_id", how="left")
        agg[std_col] = agg[std_col].fillna(0.0)
        agg[ci_col] = 1.96 * agg[std_col] / (agg["count"] ** 0.5)
        agg[ci_col] = agg[ci_col].fillna(0.0)
        agg = agg.drop(columns=["count"])

    if "compliance_global_mean" in agg and "compliance_global_ci95" in agg:
        width_ratio = (2 * agg["compliance_global_ci95"]) / agg["compliance_global_mean"].replace(0, pd.NA)
        agg["unstable_config"] = width_ratio > 0.10
    return agg


def _build_run_info(manifest: Dict) -> Dict[str, Dict]:
    info: Dict[str, Dict] = {}
    for run in manifest.get("runs", []):
        info[run["id"]] = {
            "ter_mode": run["ter_mode"],
            "sat_mode": run["sat_mode"],
            "load": run["load"],
            "connectivity_override": run.get("connectivity_override", "DEFAULT"),
        }
    return info


def _build_benefit_cost(
    manifest: Dict, config_df: pd.DataFrame, run_info: Dict[str, Dict]
) -> pd.DataFrame:
    base_map: Dict[tuple[str, str], str] = {}
    for run_id, info in run_info.items():
        if info["ter_mode"] == "TER_NO_EDGE" and info["sat_mode"] == "SAT_TRANSPARENT":
            key = (info["load"], info["connectivity_override"])
            base_map[key] = run_id

    records: List[Dict] = []
    for _, row in config_df.iterrows():
        config_id = str(row["config_id"])
        info = run_info.get(config_id)
        if info is None:
            continue
        key = (info["load"], info["connectivity_override"])
        baseline_id = base_map.get(key)
        baseline_row = config_df.loc[config_df["config_id"] == baseline_id]
        baseline_value = float(baseline_row["compliance_global_mean"].iloc[0]) if not baseline_row.empty else 0.0
        baseline_util = float(baseline_row["mean_compute_utilization_mean"].iloc[0]) if not baseline_row.empty else 0.0
        benefit = float(row["compliance_global_mean"]) - baseline_value
        util_delta = float(row["mean_compute_utilization_mean"]) - baseline_util

        records.append(
            {
                "config_id": config_id,
                "load": info["load"],
                "connectivity_override": info["connectivity_override"],
                "ter_mode": info["ter_mode"],
                "sat_mode": info["sat_mode"],
                "benefit": benefit,
                "util_mean": float(row["mean_compute_utilization_mean"]),
                "util_delta": util_delta,
                "detour_volume_mb_mean": float(row["detour_volume_mb_mean"]),
            }
        )

    benefit_df = pd.DataFrame.from_records(records)
    benefit_df["detour_norm"] = 0.0
    for group_key, group in benefit_df.groupby(["load", "connectivity_override"]):
        if isinstance(group_key, tuple):
            load, override = group_key
        else:
            load, override = group_key, "DEFAULT"
        max_detour = group["detour_volume_mb_mean"].max()
        if max_detour > 0:
            benefit_df.loc[group.index, "detour_norm"] = group["detour_volume_mb_mean"] / max_detour

    benefit_df["cost"] = 0.5 * benefit_df["util_delta"] + 0.5 * benefit_df["detour_norm"]
    return benefit_df


def analyze_runs(manifest_path: Path, runs_dir: Path) -> None:
    manifest = _load_manifest(manifest_path)
    seed_df = _collect_seed_summaries(runs_dir)
    if seed_df.empty:
        raise RuntimeError("No summaries found under runs/")

    aggregated_dir = runs_dir / "_aggregated"
    aggregated_dir.mkdir(parents=True, exist_ok=True)
    seed_df.to_csv(aggregated_dir / "seed_metrics.csv", index=False)

    config_df = _aggregate_config_metrics(seed_df)
    config_df.to_csv(aggregated_dir / "config_metrics.csv", index=False)

    run_info = _build_run_info(manifest)
    benefit_df = _build_benefit_cost(manifest, config_df, run_info)
    benefit_df.to_csv(aggregated_dir / "benefit_cost.csv", index=False)
