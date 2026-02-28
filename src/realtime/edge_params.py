from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class EdgeConfig:
    config_id: str
    ter: str
    sat: str
    video_filter: bool
    sat_edge_fraction: Optional[float] = None
    sat_detour_ms: Optional[float] = None


@dataclass(frozen=True)
class EdgeParams:
    window_s: int
    ewma_lambda: float
    bnom_5g_ms: float
    bnom_sat_ms: float
    edge_configs: List[EdgeConfig]
    alpha: Dict[str, Dict[str, float]]
    compute_mu: float
    compute_sigma: float
    compute_min_ms: float
    compute_max_ms: float
    k_loc: Dict[str, float]
    beta_video_filter: float
    beta_video_filter_by_config: Dict[str, float]
    beta_video_filter_by_level: Dict[str, float]
    sat_edge_fraction_by_level: Dict[str, float]
    sat_detour_ms_by_level: Dict[str, float]
    kpi_thresholds: Dict[str, Dict[str, float]]
    output_root: Path
    source_path: Path


def _load_kpi_thresholds(path: Path) -> Dict[str, Dict[str, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["kpi_thresholds"]


def load_edge_params(path: Path) -> EdgeParams:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("realtime_edge_params.json must be a JSON object")

    window_s = int(data.get("window_s", 120))
    ewma_lambda = float(data.get("ewma_lambda", 0.2))
    bnom_5g_ms = float(data.get("bnom_5g_ms", 25.0))
    bnom_sat_ms = float(data.get("bnom_sat_ms", 55.0))
    beta_video_filter = float(data.get("beta_video_filter", 0.35))
    beta_by_config_raw = data.get("beta_video_filter_by_config", {})
    beta_video_filter_by_config = {
        str(key): float(value) for key, value in beta_by_config_raw.items()
    }
    beta_by_level_raw = data.get("beta_video_filter_by_level", {})
    beta_video_filter_by_level = {
        str(key): float(value) for key, value in beta_by_level_raw.items()
    }
    sat_edge_fraction_by_level = {
        str(key): float(value)
        for key, value in data.get("sat_edge_fraction_by_level", {}).items()
    }
    sat_detour_ms_by_level = {
        str(key): float(value)
        for key, value in data.get("sat_detour_ms_by_level", {}).items()
    }

    edge_configs = []
    for cfg in data.get("edge_configs", []):
        edge_configs.append(
            EdgeConfig(
                config_id=str(cfg["config_id"]),
                ter=str(cfg["ter"]),
                sat=str(cfg["sat"]),
                video_filter=bool(cfg.get("video_filter", False)),
                sat_edge_fraction=(
                    float(cfg["sat_edge_fraction"]) if "sat_edge_fraction" in cfg else None
                ),
                sat_detour_ms=(
                    float(cfg["sat_detour_ms"]) if "sat_detour_ms" in cfg else None
                ),
            )
        )
    if not edge_configs:
        raise ValueError("edge_configs must not be empty")

    alpha = data.get("alpha", {})
    if not alpha:
        raise ValueError("alpha map is required")

    compute_mu = data.get("compute_cloud_lognorm_mu")
    if compute_mu is None:
        median = float(data.get("compute_cloud_median_ms", 3.5))
        compute_mu = math.log(max(1e-6, median))
    compute_sigma = float(data.get("compute_cloud_lognorm_sigma", 0.3))
    compute_min_ms = float(data.get("compute_cloud_min_ms", 1.0))
    compute_max_ms = float(data.get("compute_cloud_max_ms", 10.0))

    k_loc = data.get("k_loc", {})
    if not k_loc:
        k_loc = {
            "cloud": 1.0,
            "ter_national": 1.0,
            "ter_regional": 1.1,
            "ter_bs": 1.2,
            "sat_gw": 1.3,
            "sat_onboard": 1.6,
        }

    kpi_manifest = Path(data.get("kpi_manifest", "configs/paper_manifest.json"))
    if not kpi_manifest.is_absolute():
        kpi_manifest = Path.cwd() / kpi_manifest
    kpi_thresholds = _load_kpi_thresholds(kpi_manifest)

    output_root = Path(data.get("output_root", "runs/realtime_replay"))
    if not output_root.is_absolute():
        output_root = Path.cwd() / output_root

    return EdgeParams(
        window_s=window_s,
        ewma_lambda=ewma_lambda,
        bnom_5g_ms=bnom_5g_ms,
        bnom_sat_ms=bnom_sat_ms,
        edge_configs=edge_configs,
        alpha=alpha,
        compute_mu=float(compute_mu),
        compute_sigma=compute_sigma,
        compute_min_ms=compute_min_ms,
        compute_max_ms=compute_max_ms,
        k_loc=k_loc,
        beta_video_filter=beta_video_filter,
        beta_video_filter_by_config=beta_video_filter_by_config,
        beta_video_filter_by_level=beta_video_filter_by_level,
        sat_edge_fraction_by_level=sat_edge_fraction_by_level,
        sat_detour_ms_by_level=sat_detour_ms_by_level,
        kpi_thresholds=kpi_thresholds,
        output_root=output_root,
        source_path=path,
    )
