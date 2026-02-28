from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd

from src.core.metrics import P2Quantile


def _load_manifest(path: Path) -> Dict:
    return json.loads(path.read_text())


def _kpi_thresholds(manifest: Dict) -> Dict[str, Dict[str, float]]:
    return manifest["kpi_thresholds"]


def _flows_paths(runs_dir: Path, run_id: str) -> Iterable[Path]:
    return runs_dir.glob(f"{run_id}/seed_*/flows.csv")


def _service_compliance_seed(
    flow_path: Path, thresholds: Dict[str, Dict[str, float]]
) -> Dict[str, Dict[int, Dict[str, int]]]:
    counts: Dict[str, Dict[int, Dict[str, int]]] = {}
    for chunk in pd.read_csv(flow_path, chunksize=500000):
        chunk["latency_ms"] = pd.to_numeric(chunk["latency_ms"], errors="coerce")
        chunk["jitter_ms"] = pd.to_numeric(chunk["jitter_ms"], errors="coerce")
        chunk["throughput_mbps"] = pd.to_numeric(chunk["throughput_mbps"], errors="coerce")
        for app_type, thr in thresholds.items():
            app_df = chunk[chunk["app_type"] == app_type]
            if app_df.empty:
                continue
            ok = (
                (app_df["loss_flag"] == 0)
                & (app_df["latency_ms"] <= thr["latency_ms"])
                & (app_df["jitter_ms"] <= thr["jitter_ms"])
                & (app_df["throughput_mbps"] >= thr["throughput_mbps"])
            )
            for train_id, group in app_df.groupby("train_id"):
                counts.setdefault(app_type, {}).setdefault(int(train_id), {"ok": 0, "total": 0})
                counts[app_type][int(train_id)]["ok"] += int(ok.loc[group.index].sum())
                counts[app_type][int(train_id)]["total"] += int(len(group))
    return counts


def _aggregate_service_counts(counts: Dict[str, Dict[int, Dict[str, int]]]) -> Dict[str, float]:
    results: Dict[str, float] = {}
    for app_type, train_map in counts.items():
        per_train = []
        for stats in train_map.values():
            total = stats["total"]
            ok = stats["ok"]
            per_train.append(ok / total if total else 0.0)
        results[app_type] = sum(per_train) / len(per_train) if per_train else 0.0
    return results


def _tail_components_seed(flow_path: Path) -> Dict[str, float]:
    p95_access = P2Quantile(0.95)
    p95_transport = P2Quantile(0.95)
    p95_compute = P2Quantile(0.95)
    p95_detour = P2Quantile(0.95)
    p99_access = P2Quantile(0.99)
    p99_transport = P2Quantile(0.99)
    p99_compute = P2Quantile(0.99)
    p99_detour = P2Quantile(0.99)
    p999_access = P2Quantile(0.999)
    p999_transport = P2Quantile(0.999)
    p999_compute = P2Quantile(0.999)
    p999_detour = P2Quantile(0.999)
    detour_seen = False

    for chunk in pd.read_csv(flow_path, chunksize=500000):
        chunk = chunk[chunk["loss_flag"] == 0]
        if chunk.empty:
            continue
        for col in [
            "access_latency_ms",
            "transport_to_edge_ms",
            "transport_return_ms",
            "compute_latency_ms",
            "detour_latency_ms",
        ]:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

        access = chunk["access_latency_ms"].dropna()
        transport = (chunk["transport_to_edge_ms"] + chunk["transport_return_ms"]).dropna()
        compute = chunk["compute_latency_ms"].dropna()

        for value in access:
            value = float(value)
            p95_access.add(value)
            p99_access.add(value)
            p999_access.add(value)
        for value in transport:
            value = float(value)
            p95_transport.add(value)
            p99_transport.add(value)
            p999_transport.add(value)
        for value in compute:
            value = float(value)
            p95_compute.add(value)
            p99_compute.add(value)
            p999_compute.add(value)

        detour = chunk[chunk["detour_latency_ms"] > 0]["detour_latency_ms"].dropna()
        if not detour.empty:
            detour_seen = True
            for value in detour:
                value = float(value)
                p95_detour.add(value)
                p99_detour.add(value)
                p999_detour.add(value)

    return {
        "p95_access": p95_access.value() or 0.0,
        "p95_transport": p95_transport.value() or 0.0,
        "p95_compute": p95_compute.value() or 0.0,
        "p95_detour": (p95_detour.value() or 0.0) if detour_seen else 0.0,
        "p99_access": p99_access.value() or 0.0,
        "p99_transport": p99_transport.value() or 0.0,
        "p99_compute": p99_compute.value() or 0.0,
        "p99_detour": (p99_detour.value() or 0.0) if detour_seen else 0.0,
        "p999_access": p999_access.value() or 0.0,
        "p999_transport": p999_transport.value() or 0.0,
        "p999_compute": p999_compute.value() or 0.0,
        "p999_detour": (p999_detour.value() or 0.0) if detour_seen else 0.0,
    }


def derive_metrics(manifest_path: Path, runs_dir: Path, tail_configs: List[str]) -> None:
    manifest = _load_manifest(manifest_path)
    thresholds = _kpi_thresholds(manifest)
    aggregated_dir = runs_dir / "_aggregated"
    aggregated_dir.mkdir(parents=True, exist_ok=True)

    service_rows = []
    worst_rows = []
    tail_rows = []

    existing_service = set()
    existing_tail = set()
    service_seed_path = aggregated_dir / "service_compliance_seed.csv"
    tail_seed_path = aggregated_dir / "tail_components_seed.csv"
    tail_seed_mode = "w"
    tail_seed_header = True
    tail_seed_valid = not tail_seed_path.exists()
    if service_seed_path.exists():
        df = pd.read_csv(service_seed_path)
        existing_service = set(zip(df["config_id"], df["seed"]))
    if tail_seed_path.exists():
        df = pd.read_csv(tail_seed_path)
        if {"config_id", "seed", "component", "value"}.issubset(df.columns):
            existing_tail = set(zip(df["config_id"], df["seed"]))
            tail_seed_mode = "a"
            tail_seed_header = False
            tail_seed_valid = True

    for run in manifest["runs"]:
        run_id = run["id"]
        for flow_path in _flows_paths(runs_dir, run_id):
            seed = int(flow_path.parent.name.split("_")[-1])
            if (run_id, seed) not in existing_service:
                counts = _service_compliance_seed(flow_path, thresholds)
                compliance_by_app = _aggregate_service_counts(counts)
                for app_type, compliance in compliance_by_app.items():
                    service_rows.append(
                        {
                            "config_id": run_id,
                            "seed": seed,
                            "app_type": app_type,
                            "compliance": compliance,
                        }
                    )
                if compliance_by_app:
                    worst_rows.append(
                        {
                            "config_id": run_id,
                            "seed": seed,
                            "worst_service_compliance": min(compliance_by_app.values()),
                        }
                    )
                existing_service.add((run_id, seed))
            if run_id in tail_configs and (run_id, seed) not in existing_tail:
                tail = _tail_components_seed(flow_path)
                for component, value in tail.items():
                    tail_rows.append(
                        {
                            "config_id": run_id,
                            "seed": seed,
                            "component": component,
                            "value": value,
                        }
                    )
                existing_tail.add((run_id, seed))

        if service_rows:
            mode = "a" if service_seed_path.exists() else "w"
            header = not service_seed_path.exists()
            pd.DataFrame(service_rows).to_csv(service_seed_path, mode=mode, header=header, index=False)
            service_rows = []

        if worst_rows:
            worst_seed_path = aggregated_dir / "worst_service_seed.csv"
            mode = "a" if worst_seed_path.exists() else "w"
            header = not worst_seed_path.exists()
            pd.DataFrame(worst_rows).to_csv(worst_seed_path, mode=mode, header=header, index=False)
            worst_rows = []

        if tail_rows:
            pd.DataFrame(tail_rows).to_csv(
                tail_seed_path, mode=tail_seed_mode, header=tail_seed_header, index=False
            )
            tail_rows = []
            tail_seed_mode = "a"
            tail_seed_header = False
            tail_seed_valid = True

    service_df = pd.read_csv(service_seed_path) if service_seed_path.exists() else pd.DataFrame()
    if not service_df.empty:
        summary = service_df.groupby(["config_id", "app_type"]).agg(["mean", "std"]).reset_index()
        summary.columns = [
            "config_id" if col[0] == "config_id" else ("app_type" if col[0] == "app_type" else f"{col[0]}_{col[1]}")
            for col in summary.columns
        ]
        counts = service_df.groupby(["config_id", "app_type"])["compliance"].count().reset_index().rename(
            columns={"compliance": "count"}
        )
        summary = summary.merge(counts, on=["config_id", "app_type"], how="left")
        summary["compliance_ci95"] = 1.96 * summary["compliance_std"] / (summary["count"] ** 0.5)
        summary = summary.drop(columns=["count"])
        summary.to_csv(aggregated_dir / "service_compliance_summary.csv", index=False)

    worst_seed_path = aggregated_dir / "worst_service_seed.csv"
    worst_df = pd.read_csv(worst_seed_path) if worst_seed_path.exists() else pd.DataFrame()
    if not worst_df.empty:
        worst_summary = worst_df.groupby("config_id").agg(["mean", "std"]).reset_index()
        worst_summary.columns = [
            "config_id" if col[0] == "config_id" else f"{col[0]}_{col[1]}" for col in worst_summary.columns
        ]
        counts = worst_df.groupby("config_id")["worst_service_compliance"].count().reset_index().rename(
            columns={"worst_service_compliance": "count"}
        )
        worst_summary = worst_summary.merge(counts, on="config_id", how="left")
        worst_summary["worst_service_compliance_ci95"] = (
            1.96 * worst_summary["worst_service_compliance_std"] / (worst_summary["count"] ** 0.5)
        )
        worst_summary = worst_summary.drop(columns=["count"])
        worst_summary.to_csv(aggregated_dir / "worst_service_summary.csv", index=False)

    tail_df = (
        pd.read_csv(tail_seed_path)
        if tail_seed_path.exists() and tail_seed_valid
        else pd.DataFrame()
    )
    if not tail_df.empty:
        tail_summary = tail_df.groupby(["config_id", "component"]).agg(["mean", "std"]).reset_index()
        tail_summary.columns = [
            "config_id" if col[0] == "config_id" else ("component" if col[0] == "component" else f"{col[0]}_{col[1]}")
            for col in tail_summary.columns
        ]
        counts = tail_df.groupby(["config_id", "component"])["value"].count().reset_index().rename(
            columns={"value": "count"}
        )
        tail_summary = tail_summary.merge(counts, on=["config_id", "component"], how="left")
        tail_summary["value_ci95"] = 1.96 * tail_summary["value_std"] / (tail_summary["count"] ** 0.5)
        tail_summary = tail_summary.drop(columns=["count"])
        tail_summary.to_csv(aggregated_dir / "tail_components_summary.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="configs/paper_manifest.json")
    parser.add_argument("--runs", default="runs_paper_v3")
    parser.add_argument("--tail-configs", default="P2-A,P2-B,P2-D,P2-E")
    args = parser.parse_args()

    tail_configs = [item.strip() for item in args.tail_configs.split(",") if item.strip()]
    derive_metrics(Path(args.manifest), Path(args.runs), tail_configs)


if __name__ == "__main__":
    main()
