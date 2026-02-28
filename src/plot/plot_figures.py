from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List
import typing

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
import numpy as np
import pandas as pd

from src.plot.plot_style import apply_style, palette


def _load_mapping(mapping_path: Path) -> Dict:
    with mapping_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_alias_map(runs_dir: Path) -> Dict[str, str]:
    manifest_path = runs_dir / "_aggregated" / "run_manifest.json"
    if not manifest_path.exists():
        return {}
    with manifest_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data.get("alias_map", {})


def _load_seed_metrics(aggregated_dir: Path) -> pd.DataFrame:
    return pd.read_csv(aggregated_dir / "seed_metrics.csv")


def _load_config_metrics(aggregated_dir: Path) -> pd.DataFrame:
    return pd.read_csv(aggregated_dir / "config_metrics.csv")


def _load_benefit_cost(aggregated_dir: Path) -> pd.DataFrame:
    return pd.read_csv(aggregated_dir / "benefit_cost.csv")


def _load_service_compliance(aggregated_dir: Path) -> pd.DataFrame:
    return pd.read_csv(aggregated_dir / "service_compliance_summary.csv")


def _load_worst_service(aggregated_dir: Path) -> pd.DataFrame:
    return pd.read_csv(aggregated_dir / "worst_service_summary.csv")


def _load_tail_components(aggregated_dir: Path) -> pd.DataFrame:
    return pd.read_csv(aggregated_dir / "tail_components_summary.csv")


def _flow_latencies(runs_dir: Path, run_id: str, app_type: str) -> np.ndarray:
    latencies: List[float] = []
    for flow_path in runs_dir.glob(f"{run_id}/seed_*/flows.csv"):
        df = pd.read_csv(flow_path, usecols=["time", "train_id", "app_type", "latency_ms", "loss_flag"])
        df = df[(df["app_type"] == app_type) & (df["loss_flag"] == 0) & df["latency_ms"].notna()]
        latencies.extend(df["latency_ms"].astype(float).tolist())
    return np.array(latencies, dtype=float)


def _plot_box(
    fig_path: Path,
    title: str,
    metric: str,
    runs: List[str],
    labels: List[str],
    seed_df: pd.DataFrame,
    config_df: pd.DataFrame,
) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)
    data = []
    filtered_labels = []
    filtered_runs = []
    for run, label in zip(runs, labels):
        values = seed_df.loc[seed_df["config_id"] == run, metric].dropna().values
        if values.size == 0:
            continue
        data.append(values)
        filtered_labels.append(label)
        filtered_runs.append(run)
    if not data:
        plt.close(fig)
        return
    ax.boxplot(data, labels=filtered_labels, showfliers=False)

    ci_means = []
    ci_errors = []
    for run in filtered_runs:
        row = config_df.loc[config_df["config_id"] == run]
        if row.empty:
            mean = float("nan")
            ci = float("nan")
        else:
            mean = float(row[f"{metric}_mean"].iloc[0])
            ci = float(row[f"{metric}_ci95"].iloc[0])
        ci_means.append(mean)
        ci_errors.append(ci)
    ax.errorbar(range(1, len(filtered_runs) + 1), ci_means, yerr=ci_errors, fmt="o", color="#1B4965")
    ax.set_title(title)
    ax.set_ylabel(metric)
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def _plot_violin(
    fig_path: Path,
    title: str,
    metric: str,
    runs: List[str],
    labels: List[str],
    seed_df: pd.DataFrame,
    config_df: pd.DataFrame,
) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)
    data = []
    filtered_labels = []
    filtered_runs = []
    for run, label in zip(runs, labels):
        values = seed_df.loc[seed_df["config_id"] == run, metric].dropna().values
        if values.size == 0:
            continue
        data.append(values)
        filtered_labels.append(label)
        filtered_runs.append(run)
    if not data:
        plt.close(fig)
        return
    ax.violinplot(data, showmedians=True)
    ax.set(xticks=list(range(1, len(filtered_runs) + 1)), xticklabels=filtered_labels)
    ci_means = []
    ci_errors = []
    for run in filtered_runs:
        row = config_df.loc[config_df["config_id"] == run]
        if row.empty:
            mean = float("nan")
            ci = float("nan")
        else:
            mean = float(row[f"{metric}_mean"].iloc[0])
            ci = float(row[f"{metric}_ci95"].iloc[0])
        ci_means.append(mean)
        ci_errors.append(ci)
    ax.errorbar(range(1, len(filtered_runs) + 1), ci_means, yerr=ci_errors, fmt="o", color="#1B4965")
    ax.set_title(title)
    ax.set_ylabel(metric)
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def _plot_scatter(fig_path: Path, title: str, benefit_df: pd.DataFrame) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)
    ax.scatter(benefit_df["cost"], benefit_df["benefit"], color="#1B4965")
    for _, row in benefit_df.iterrows():
        ax.annotate(row["config_id"], (row["cost"], row["benefit"]), fontsize=8, xytext=(4, 2), textcoords="offset points")
    ax.set_title(title)
    ax.set_xlabel("Cost proxy")
    ax.set_ylabel("Benefit (Compliance gain)")
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def _plot_cdf(
    fig_path: Path, title: str, runs: List[str], labels: List[str], runs_dir: Path, app_type: str
) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)
    colors = palette()
    for idx, run_id in enumerate(runs):
        latencies = _flow_latencies(runs_dir, run_id, app_type)
        if latencies.size == 0:
            continue
        values = np.sort(latencies)
        cdf = np.linspace(0, 1, len(values))
        label = labels[idx] if idx < len(labels) else run_id
        ax.plot(values, cdf, label=label, color=colors[idx % len(colors)])
    ax.set_title(title)
    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("CDF")
    ax.grid(True)
    ax.legend()
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def _plot_timeseries(
    fig_path: Path,
    title: str,
    runs: List[str],
    labels: List[str],
    runs_dir: Path,
    app_type: str,
    train_id: int,
    bin_ms: int,
) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)
    colors = palette()
    for idx, run_id in enumerate(runs):
        flow_paths = list((runs_dir / run_id).glob("seed_*/flows.csv"))
        if not flow_paths:
            continue
        df = pd.read_csv(flow_paths[0])
        df = df[(df["app_type"] == app_type) & (df["train_id"] == train_id) & (df["loss_flag"] == 0)]
        if df.empty:
            continue
        df["bin"] = (df["time"] // bin_ms) * bin_ms
        binned = df.groupby("bin")["latency_ms"].mean().reset_index()
        label = labels[idx] if idx < len(labels) else run_id
        ax.plot(binned["bin"], binned["latency_ms"], label=label, color=colors[idx % len(colors)])

        event_paths = list((runs_dir / run_id).glob("seed_*/events.csv"))
        if event_paths:
            events = pd.read_csv(event_paths[0])
            for _, event in events.iterrows():
                if event["event_type"] in ("beam_switch", "connectivity_change", "detour"):
                    ax.axvline(int(float(event["time"])), color="#8A5A44", alpha=0.15)
    ax.set_title(title)
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Latency (ms)")
    ax.grid(True)
    ax.legend()
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def _plot_stacked_latency(
    fig_path: Path,
    title: str,
    runs: List[str],
    labels: List[str],
    config_df: pd.DataFrame,
) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)

    components = [
        ("mean_access_latency_mean", "Access"),
        ("mean_transport_to_edge_mean", "Transport"),
        ("mean_compute_latency_mean", "Compute"),
        ("mean_transport_return_mean", "Return"),
        ("mean_detour_latency_mean", "Detour"),
    ]
    x = list(range(len(runs)))
    bottoms = [0.0 for _ in runs]
    colors = palette()
    for idx, (col, label) in enumerate(components):
        values = []
        for run in runs:
            row = config_df.loc[config_df["config_id"] == run]
            if row.empty:
                values.append(0.0)
            else:
                values.append(float(row[col].iloc[0]))
        ax.bar(x, values, bottom=bottoms, label=label, color=colors[idx % len(colors)])
        bottoms = [b + v for b, v in zip(bottoms, values)]

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title(title)
    ax.set_ylabel("Mean latency (ms)")
    ax.legend()
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def _plot_service_compliance(
    fig_path: Path,
    title: str,
    runs: List[str],
    labels: List[str],
    service_df: pd.DataFrame,
) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)

    apps = ["ETCS2", "Voice", "Video"]
    width = 0.2
    x = list(range(len(runs)))
    colors = palette()

    for idx, app in enumerate(apps):
        values = []
        errors = []
        for run in runs:
            row = service_df[(service_df["config_id"] == run) & (service_df["app_type"] == app)]
            if row.empty:
                values.append(0.0)
                errors.append(0.0)
            else:
                values.append(float(row["compliance_mean"].iloc[0]))
                errors.append(float(row["compliance_ci95"].iloc[0]))
        positions = [val + (idx - 1) * width for val in x]
        ax.bar(positions, values, width=width, label=app, color=colors[idx % len(colors)])
        ax.errorbar(positions, values, yerr=errors, fmt="none", ecolor="#333", capsize=2)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title(title)
    ax.set_ylabel("Compliance (mean)")
    ax.legend()
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def _plot_worst_train(
    fig_path: Path,
    title: str,
    runs: List[str],
    labels: List[str],
    config_df: pd.DataFrame,
) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)

    values = []
    errors = []
    for run in runs:
        row = config_df.loc[config_df["config_id"] == run]
        if row.empty:
            values.append(0.0)
            errors.append(0.0)
        else:
            values.append(float(row["compliance_worst_train_mean"].iloc[0]))
            errors.append(float(row["compliance_worst_train_ci95"].iloc[0]))
    ax.bar(labels, values, color=palette()[0])
    ax.errorbar(range(len(labels)), values, yerr=errors, fmt="none", ecolor="#333", capsize=2)
    ax.set_title(title)
    ax.set_ylabel("Worst-train compliance (mean)")
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def _plot_tail_components(
    fig_path: Path,
    title: str,
    runs: List[str],
    labels: List[str],
    tail_df: pd.DataFrame,
    percentile: str,
) -> None:
    apply_style()
    fig, ax = plt.subplots()
    fig = typing.cast(Figure, fig)
    ax = typing.cast(Axes, ax)

    components = [
        (f"{percentile}_access", "Access"),
        (f"{percentile}_transport", "Transport"),
        (f"{percentile}_compute", "Compute"),
        (f"{percentile}_detour", "Detour"),
    ]
    width = 0.18
    x = list(range(len(runs)))
    colors = palette()

    for idx, (comp, label) in enumerate(components):
        values = []
        errors = []
        for run in runs:
            row = tail_df[(tail_df["config_id"] == run) & (tail_df["component"] == comp)]
            if row.empty:
                values.append(0.0)
                errors.append(0.0)
            else:
                values.append(float(row["value_mean"].iloc[0]))
                errors.append(float(row["value_ci95"].iloc[0]))
        positions = [val + (idx - 1.5) * width for val in x]
        ax.bar(positions, values, width=width, label=label, color=colors[idx % len(colors)])
        ax.errorbar(positions, values, yerr=errors, fmt="none", ecolor="#333", capsize=2)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title(title)
    percentile_label = "p99.9" if percentile == "p999" else percentile
    ax.set_ylabel(f"{percentile_label} component latency (ms)")
    ax.legend()
    ax.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(fig_path)
    plt.close(fig)


def generate_figures(mapping_path: Path, runs_dir: Path, output_dir: Path) -> None:
    mapping = _load_mapping(mapping_path)
    alias_map = _load_alias_map(runs_dir)
    aggregated_dir = runs_dir / "_aggregated"
    seed_df = _load_seed_metrics(aggregated_dir)
    config_df = _load_config_metrics(aggregated_dir)
    benefit_df = _load_benefit_cost(aggregated_dir)
    service_df = _load_service_compliance(aggregated_dir) if (aggregated_dir / "service_compliance_summary.csv").exists() else pd.DataFrame()
    tail_df = _load_tail_components(aggregated_dir) if (aggregated_dir / "tail_components_summary.csv").exists() else pd.DataFrame()

    output_dir.mkdir(parents=True, exist_ok=True)
    for fig in mapping.get("figures", []):
        fig_id = fig["id"]
        fig_path = output_dir / f"{fig_id}.png"
        fig_type = fig["type"]
        title = fig.get("title", fig_id)
        runs = [str(alias_map.get(run_id, run_id)) for run_id in fig.get("runs", [])]
        labels = fig.get("runs", [])
        if fig_type == "box":
            _plot_box(fig_path, title, fig["metric"], runs, labels, seed_df, config_df)
        elif fig_type == "violin":
            _plot_violin(fig_path, title, fig["metric"], runs, labels, seed_df, config_df)
        elif fig_type == "scatter":
            _plot_scatter(fig_path, title, benefit_df)
        elif fig_type == "cdf":
            _plot_cdf(fig_path, title, runs, labels, runs_dir, fig["app_type"])
        elif fig_type == "timeseries":
            _plot_timeseries(
                fig_path,
                title,
                runs,
                labels,
                runs_dir,
                fig["app_type"],
                fig["train_id"],
                fig["bin_ms"],
            )
        elif fig_type == "stacked":
            _plot_stacked_latency(fig_path, title, runs, labels, config_df)
        elif fig_type == "service_compliance":
            _plot_service_compliance(fig_path, title, runs, labels, service_df)
        elif fig_type == "worst_train":
            _plot_worst_train(fig_path, title, runs, labels, config_df)
        elif fig_type == "tail_components":
            _plot_tail_components(
                fig_path,
                title,
                runs,
                labels,
                tail_df,
                fig.get("percentile", "p95"),
            )
