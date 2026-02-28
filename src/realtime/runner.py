from __future__ import annotations

import csv
import json
import math
import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from src.realtime.edge_params import EdgeConfig, EdgeParams


@dataclass(frozen=True)
class ScenarioRow:
    time_ms: int
    time_iso: str
    gps_lat: float
    gps_lon: float
    speed_mps: float
    metrics_5g: Dict[str, Optional[float]]
    metrics_sat: Dict[str, Optional[float]]


def _format_time_ms(time_ms: int) -> str:
    dt = datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_time_ms(value: str) -> int:
    raw = str(value).strip()
    if not raw:
        raise ValueError("time is required in scenario CSV")
    if raw.isdigit():
        num = int(raw)
        return num if num > 10_000_000_000 else num * 1000
    try:
        num = float(raw)
        return int(num if num > 10_000_000_000 else num * 1000)
    except ValueError:
        pass
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load_scenario(csv_path: Path) -> List[ScenarioRow]:
    rows: List[ScenarioRow] = []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"time", "gps_lat", "gps_lon", "speed_mps"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("Scenario CSV missing required columns")
        for record in reader:
            time_ms = _parse_time_ms(record.get("time", ""))
            gps_lat = float(record.get("gps_lat", 0.0))
            gps_lon = float(record.get("gps_lon", 0.0))
            speed_mps = float(record.get("speed_mps", 0.0))
            metrics_5g = {
                "e2e_ms": _parse_float(record.get("e2e_latency_5g_ms")),
                "ul_mbps": _parse_float(record.get("ul_mbps_5g")),
                "dl_mbps": _parse_float(record.get("dl_mbps_5g")),
                "bler": _parse_float(record.get("bler_5g")),
                "jitter_ms": _parse_float(record.get("jitter_5g_ms")),
                "loss": _parse_float(record.get("loss_5g")),
            }
            metrics_sat = {
                "e2e_ms": _parse_float(record.get("e2e_latency_sat_ms")),
                "ul_mbps": _parse_float(record.get("ul_mbps_sat")),
                "dl_mbps": _parse_float(record.get("dl_mbps_sat")),
                "bler": _parse_float(record.get("bler_sat")),
                "jitter_ms": _parse_float(record.get("jitter_sat_ms")),
                "loss": _parse_float(record.get("loss_sat")),
            }
            rows.append(
                ScenarioRow(
                    time_ms=time_ms,
                    time_iso=_format_time_ms(time_ms),
                    gps_lat=gps_lat,
                    gps_lon=gps_lon,
                    speed_mps=speed_mps,
                    metrics_5g=metrics_5g,
                    metrics_sat=metrics_sat,
                )
            )
    rows.sort(key=lambda row: row.time_ms)
    return rows


def _trim_window(window: Deque[Tuple[int, float]], now_ms: int, window_ms: int) -> None:
    while window and now_ms - window[0][0] > window_ms:
        window.popleft()


def _quantile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    values_sorted = sorted(values)
    idx = int(math.ceil(q * len(values_sorted))) - 1
    idx = max(0, min(idx, len(values_sorted) - 1))
    return values_sorted[idx]


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


class RealtimeRunner:
    def __init__(
        self,
        scenario_name: str,
        slot_ms: int,
        rows: List[ScenarioRow],
        csv_path: Path,
        edge_params: EdgeParams,
    ) -> None:
        self.scenario_name = scenario_name
        self.slot_ms = slot_ms
        self.rows = rows
        self.csv_path = csv_path
        self.edge_params = edge_params
        self.state = "stopped"
        self.last_error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_slot: Optional[Dict] = None
        self.run_dir: Optional[Path] = None
        self.scenario_start_ms = self.rows[0].time_ms if self.rows else 0
        self.baseline_config_id = self._resolve_baseline_config()
        self.edge_configs_sorted = sorted(self.edge_params.edge_configs, key=lambda cfg: cfg.config_id)

        self._baseline: Dict[str, Optional[float]] = {"5g": None, "sat": None}
        self._baseline_windows: Dict[str, Deque[Tuple[int, float]]] = {
            "5g": deque(),
            "sat": deque(),
        }
        self._availability_windows: Dict[str, Deque[Tuple[int, float]]] = {
            "5g": deque(),
            "sat": deque(),
        }
        self._lat_windows: Dict[str, Dict[str, Deque[Tuple[int, float]]]] = {}
        self._compliance_windows: Dict[str, Dict[str, Dict[str, Deque[Tuple[int, float]]]]] = {}
        self._summary_latency: Dict[str, Dict[str, Dict[str, List[float]]]] = {}
        self._summary_compliance: Dict[str, Dict[str, Dict[str, List[float]]]] = {}
        self._summary_compliance_mean: Dict[str, Dict[str, List[float]]] = {}
        self._summary_compliance_min: Dict[str, Dict[str, List[float]]] = {}
        self._summary_latency_gain: Dict[str, Dict[str, List[float]]] = {}
        self._summary_latency_gain_pct: Dict[str, Dict[str, List[float]]] = {}
        self._summary_video_saved: Dict[str, Dict[str, List[float]]] = {}
        self._summary_video_saved_pct: Dict[str, Dict[str, List[float]]] = {}
        self._summary_video_saved_total: Dict[str, List[float]] = {}

        for cfg in self.edge_configs_sorted:
            self._lat_windows[cfg.config_id] = {"5g": deque(), "sat": deque()}
            self._compliance_windows[cfg.config_id] = {
                "5g": {"ETCS2": deque(), "Voice": deque(), "Video": deque()},
                "sat": {"ETCS2": deque(), "Voice": deque(), "Video": deque()},
            }
            self._summary_latency[cfg.config_id] = {
                "5g": {"p50": [], "p95": [], "p99": []},
                "sat": {"p50": [], "p95": [], "p99": []},
            }
            self._summary_compliance[cfg.config_id] = {
                "5g": {"ETCS2": [], "Voice": [], "Video": []},
                "sat": {"ETCS2": [], "Voice": [], "Video": []},
            }
            self._summary_compliance_mean[cfg.config_id] = {"5g": [], "sat": []}
            self._summary_compliance_min[cfg.config_id] = {"5g": [], "sat": []}
            self._summary_latency_gain[cfg.config_id] = {"5g": [], "sat": []}
            self._summary_latency_gain_pct[cfg.config_id] = {"5g": [], "sat": []}
            self._summary_video_saved[cfg.config_id] = {"5g": [], "sat": []}
            self._summary_video_saved_pct[cfg.config_id] = {"5g": [], "sat": []}
            self._summary_video_saved_total[cfg.config_id] = []

    def _resolve_baseline_config(self) -> str:
        for cfg in self.edge_params.edge_configs:
            if cfg.ter == "TER_NO_EDGE" and cfg.sat == "SAT_TRANSPARENT":
                return cfg.config_id
        return self.edge_params.edge_configs[0].config_id

    def _edge_fraction(self, cfg: EdgeConfig, tech: str) -> float:
        if tech != "sat":
            return 1.0
        if cfg.sat_edge_fraction is not None:
            return min(1.0, max(0.0, cfg.sat_edge_fraction))
        if cfg.sat in self.edge_params.sat_edge_fraction_by_level:
            value = self.edge_params.sat_edge_fraction_by_level[cfg.sat]
            return min(1.0, max(0.0, value))
        if cfg.sat == "SAT_TRANSPARENT":
            return 0.0
        return 1.0

    def _detour_base_ms(self, cfg: EdgeConfig) -> float:
        if cfg.sat_detour_ms is not None:
            return max(0.0, cfg.sat_detour_ms)
        if cfg.sat in self.edge_params.sat_detour_ms_by_level:
            return max(0.0, self.edge_params.sat_detour_ms_by_level[cfg.sat])
        return 0.0

    def _window_fill_ratio(self, count: int, window_ms: int) -> float:
        expected = max(1, int(round(window_ms / self.slot_ms)))
        return min(1.0, count / expected)

    def start(self, start_time: Optional[datetime]) -> str:
        if self.state == "running":
            raise RuntimeError("Scenario already running")
        if not self.rows:
            raise RuntimeError("Scenario has no rows")
        self._stop_event.clear()
        self.last_error = None
        self.state = "running"
        self._thread = threading.Thread(target=self._run_loop, args=(start_time,), daemon=True)
        self._thread.start()
        start_dt = start_time or datetime.now(timezone.utc)
        return start_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def stop(self) -> None:
        if self.state != "running":
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self.state = "stopped"

    def latest_slot(self) -> Optional[Dict]:
        with self._lock:
            return self._latest_slot

    def _run_loop(self, start_time: Optional[datetime]) -> None:
        try:
            if start_time is not None:
                now = datetime.now(timezone.utc)
                delay = (start_time - now).total_seconds()
                if delay > 0:
                    time.sleep(delay)

            start_dt = start_time or datetime.now(timezone.utc)
            run_stamp = start_dt.strftime("%Y%m%dT%H%M%SZ")
            run_dir = self.edge_params.output_root / self.scenario_name / run_stamp
            run_dir.mkdir(parents=True, exist_ok=True)
            self.run_dir = run_dir

            self._write_config_used(run_dir, start_dt)

            output_path = run_dir / "slot_metrics.jsonl"
            with output_path.open("a", encoding="utf-8") as handle:
                t_rt0_ms = int(time.time() * 1000)
                t_csv0_ms = self.rows[0].time_ms
                next_tick_ms = t_rt0_ms
                idx = 0
                window_ms = self.edge_params.window_s * 1000

                while not self._stop_event.is_set():
                    now_ms = int(time.time() * 1000)
                    if now_ms < next_tick_ms:
                        time.sleep((next_tick_ms - now_ms) / 1000.0)
                        continue

                    now_ms = int(time.time() * 1000)
                    scenario_ms = t_csv0_ms + (now_ms - t_rt0_ms)
                    while idx < len(self.rows) and self.rows[idx].time_ms < scenario_ms:
                        idx += 1
                    if idx >= len(self.rows):
                        break

                    row = self.rows[idx]
                    slot = self._build_slot(row, now_ms, window_ms)
                    handle.write(json.dumps(slot) + "\n")
                    handle.flush()
                    with self._lock:
                        self._latest_slot = slot

                    next_tick_ms += self.slot_ms

            self._write_summary(run_dir)

        except Exception as exc:  # pragma: no cover
            self.last_error = str(exc)
            self.state = "failed"
            return

        self.state = "stopped"

    def _write_config_used(self, run_dir: Path, start_dt: datetime) -> None:
        config_used = {
            "scenario_name": self.scenario_name,
            "csv_path": str(self.csv_path),
            "slot_ms": self.slot_ms,
            "edge_params_path": str(self.edge_params.source_path),
            "start_timestamp": start_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "baseline_config_id": self.baseline_config_id,
            "edge_configs": [
                {
                    "config_id": cfg.config_id,
                    "ter": cfg.ter,
                    "sat": cfg.sat,
                    "video_filter": cfg.video_filter,
                    "sat_edge_fraction": cfg.sat_edge_fraction,
                    "sat_detour_ms": cfg.sat_detour_ms,
                }
                for cfg in self.edge_configs_sorted
            ],
            "alpha": self.edge_params.alpha,
            "k_loc": self.edge_params.k_loc,
            "beta_video_filter": self.edge_params.beta_video_filter,
            "beta_video_filter_by_config": self.edge_params.beta_video_filter_by_config,
            "beta_video_filter_by_level": self.edge_params.beta_video_filter_by_level,
            "sat_edge_fraction_by_level": self.edge_params.sat_edge_fraction_by_level,
            "sat_detour_ms_by_level": self.edge_params.sat_detour_ms_by_level,
            "bnom_5g_ms": self.edge_params.bnom_5g_ms,
            "bnom_sat_ms": self.edge_params.bnom_sat_ms,
            "ewma_lambda": self.edge_params.ewma_lambda,
            "window_s": self.edge_params.window_s,
        }
        (run_dir / "config_used.json").write_text(json.dumps(config_used, indent=2), encoding="utf-8")

    def _write_summary(self, run_dir: Path) -> None:
        summary = {
            "scenario_name": self.scenario_name,
            "baseline_config_id": self.baseline_config_id,
            "window_s": self.edge_params.window_s,
            "slot_ms": self.slot_ms,
            "configs": [],
        }
        for cfg in self.edge_configs_sorted:
            entry = {
                "config_id": cfg.config_id,
                "ter": cfg.ter,
                "sat": cfg.sat,
                "latency_p50_mean": {},
                "latency_p95_mean": {},
                "latency_p99_mean": {},
                "latency_gain_mean_ms": {},
                "latency_gain_mean_pct": {},
                "compliance_service_mean": {},
                "compliance_mean": {},
                "compliance_min": {},
                "global_compliance_mean": {},
                "core_traffic_saved_mbps_mean": {},
                "core_traffic_saved_pct_mean": {},
                "core_traffic_saved_mbps_mean_total": None,
                "core_traffic_saved_mbit_total": {},
                "core_traffic_saved_mbit_total_all": None,
            }
            for tech in ("5g", "sat"):
                entry["latency_p50_mean"][tech] = _mean(
                    self._summary_latency[cfg.config_id][tech]["p50"]
                )
                entry["latency_p95_mean"][tech] = _mean(
                    self._summary_latency[cfg.config_id][tech]["p95"]
                )
                entry["latency_p99_mean"][tech] = _mean(
                    self._summary_latency[cfg.config_id][tech]["p99"]
                )
                entry["latency_gain_mean_ms"][tech] = _mean(
                    self._summary_latency_gain[cfg.config_id][tech]
                )
                entry["latency_gain_mean_pct"][tech] = _mean(
                    self._summary_latency_gain_pct[cfg.config_id][tech]
                )
                entry["core_traffic_saved_mbps_mean"][tech] = _mean(
                    self._summary_video_saved[cfg.config_id][tech]
                )
                entry["core_traffic_saved_pct_mean"][tech] = _mean(
                    self._summary_video_saved_pct[cfg.config_id][tech]
                )
                saved_values = self._summary_video_saved[cfg.config_id][tech]
                if saved_values:
                    entry["core_traffic_saved_mbit_total"][tech] = sum(saved_values) * (
                        self.slot_ms / 1000.0
                    )
                else:
                    entry["core_traffic_saved_mbit_total"][tech] = None
                entry["compliance_service_mean"][tech] = {
                    service: _mean(self._summary_compliance[cfg.config_id][tech][service])
                    for service in ("ETCS2", "Voice", "Video")
                }
                entry["compliance_mean"][tech] = _mean(
                    self._summary_compliance_mean[cfg.config_id][tech]
                )
                entry["compliance_min"][tech] = _mean(
                    self._summary_compliance_min[cfg.config_id][tech]
                )
                entry["global_compliance_mean"][tech] = entry["compliance_min"][tech]

            entry["core_traffic_saved_mbps_mean_total"] = _mean(
                self._summary_video_saved_total[cfg.config_id]
            )
            total_saved_values = self._summary_video_saved_total[cfg.config_id]
            if total_saved_values:
                entry["core_traffic_saved_mbit_total_all"] = sum(total_saved_values) * (
                    self.slot_ms / 1000.0
                )
            summary["configs"].append(entry)

        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def _build_slot(self, row: ScenarioRow, now_ms: int, window_ms: int) -> Dict:
        observed = {
            "5g": {
                "e2e_ms": row.metrics_5g["e2e_ms"],
                "ul_mbps": row.metrics_5g["ul_mbps"],
                "dl_mbps": row.metrics_5g["dl_mbps"],
                "bler": row.metrics_5g["bler"],
                "jitter_ms": row.metrics_5g["jitter_ms"],
                "loss": row.metrics_5g["loss"],
            },
            "sat": {
                "e2e_ms": row.metrics_sat["e2e_ms"],
                "ul_mbps": row.metrics_sat["ul_mbps"],
                "dl_mbps": row.metrics_sat["dl_mbps"],
                "bler": row.metrics_sat["bler"],
                "jitter_ms": row.metrics_sat["jitter_ms"],
                "loss": row.metrics_sat["loss"],
            },
        }

        availability_ratio = {}
        for tech, metrics in (("5g", row.metrics_5g), ("sat", row.metrics_sat)):
            available = metrics["e2e_ms"] is not None
            window = self._availability_windows[tech]
            window.append((now_ms, 1.0 if available else 0.0))
            _trim_window(window, now_ms, window_ms)
            availability_ratio[tech] = (
                sum(flag for _, flag in window) / len(window) if window else 0.0
            )

        baseline = {}
        excess = {}
        for tech, metrics in (("5g", row.metrics_5g), ("sat", row.metrics_sat)):
            baseline_val, excess_val = self._update_baseline(
                tech,
                now_ms,
                metrics["e2e_ms"],
                window_ms,
            )
            baseline[tech] = baseline_val
            excess[tech] = excess_val

        compute_cloud_ms = self._sample_compute_cloud()

        config_results = []
        latency_by_config: Dict[str, Dict[str, Optional[float]]] = {}
        baseline_result = None
        for cfg in self.edge_configs_sorted:
            result, latencies = self._build_edge_result(
                cfg,
                baseline,
                excess,
                row,
                now_ms,
                window_ms,
                compute_cloud_ms,
            )
            latency_by_config[cfg.config_id] = latencies
            config_results.append(result)
            if cfg.config_id == self.baseline_config_id:
                baseline_result = result

        if baseline_result is None and config_results:
            baseline_result = config_results[0]

        baseline_latencies = latency_by_config.get(self.baseline_config_id, {})
        baseline_raw = baseline_result["latency_raw_ms"] if baseline_result else {"5g": None, "sat": None}
        for result in config_results:
            config_id = result["config_id"]
            for tech in ("5g", "sat"):
                base = baseline_latencies.get(tech)
                value = result["latency_edge_ms"][tech]
                if base is None or value is None or base <= 0:
                    gain_ms = None
                    gain_pct = None
                else:
                    gain_ms = base - value
                    gain_pct = gain_ms / base
                result["latency_gain_ms"][tech] = gain_ms
                result["latency_gain_pct"][tech] = gain_pct
                if gain_ms is not None:
                    self._summary_latency_gain[config_id][tech].append(float(gain_ms))
                if gain_pct is not None:
                    self._summary_latency_gain_pct[config_id][tech].append(float(gain_pct))

        saved_totals = {}
        for result in config_results:
            total = 0.0
            seen = False
            for value in result["core_traffic_saved_mbps"].values():
                if value is None:
                    continue
                total += float(value)
                seen = True
            saved_totals[result["config_id"]] = {
                "5g": result["core_traffic_saved_mbps"].get("5g"),
                "sat": result["core_traffic_saved_mbps"].get("sat"),
                "total": total if seen else None,
            }
            if seen:
                self._summary_video_saved_total[result["config_id"]].append(total)

        edge_results = []
        for result in config_results:
            config_id = result["config_id"]
            for tech in ("5g", "sat"):
                totals = saved_totals.get(config_id, {"5g": None, "sat": None, "total": None})
                edge_results.append(
                    {
                        "config_id": config_id,
                        "is_baseline": config_id == self.baseline_config_id,
                        "techno": tech,
                        "ter_level": result["ter_level"],
                        "sat_level": result["sat_level"],
                        "available": result["available"][tech],
                        "edge_fraction": result["edge_fraction"][tech],
                        "beta_video_filter": result["beta_video_filter"][tech],
                        "latency_raw_ms": result["latency_raw_ms"][tech],
                        "latency_edge_ms": result["latency_edge_ms"][tech],
                        "baseline_latency_raw_ms": baseline_raw.get(tech),
                        "baseline_latency_edge_ms": baseline_latencies.get(tech),
                        "latency_gain_ms": result["latency_gain_ms"][tech],
                        "latency_gain_pct": result["latency_gain_pct"][tech],
                        "latency_p50_ms": result["latency_p50_ms"][tech],
                        "latency_p95_ms": result["latency_p95_ms"][tech],
                        "latency_p99_ms": result["latency_p99_ms"][tech],
                        "window_fill_ratio": result["window_fill_ratio"][tech],
                        "compute_ms": result["compute_ms"][tech],
                        "detour_ms": result["detour_ms"][tech],
                        "throughput_ul_mbps": result["throughput_ul_mbps"][tech],
                        "throughput_dl_mbps": result["throughput_dl_mbps"][tech],
                        "throughput_effective_mbps": result["throughput_effective_mbps"][tech],
                        "core_traffic_saved_mbps": result["core_traffic_saved_mbps"][tech],
                        "core_traffic_saved_pct": result["core_traffic_saved_pct"][tech],
                        "core_traffic_saved_mbps_5g": totals["5g"],
                        "core_traffic_saved_mbps_sat": totals["sat"],
                        "core_traffic_saved_mbps_total": totals["total"],
                        "compliance": {
                            "etcs": result["compliance"]["etcs"][tech],
                            "voice": result["compliance"]["voice"][tech],
                            "video": result["compliance"]["video"][tech],
                        },
                        "compliance_slot": {
                            "etcs": result["compliance_slot"]["etcs"][tech],
                            "voice": result["compliance_slot"]["voice"][tech],
                            "video": result["compliance_slot"]["video"][tech],
                        },
                        "compliance_mean": result["compliance_mean"][tech],
                        "compliance_min": result["compliance_min"][tech],
                        "global_compliance": result["global_compliance"][tech],
                        "worst_service_compliance": result["worst_service_compliance"][tech],
                    }
                )

        return {
            "timestamp": row.time_iso,
            "t_runtime": _format_time_ms(now_ms),
            "t_scenario": row.time_iso,
            "t_rel_s": (row.time_ms - self.scenario_start_ms) / 1000.0,
            "scenario": self.scenario_name,
            "baseline_config_id": self.baseline_config_id,
            "gps": {"lat": row.gps_lat, "lon": row.gps_lon},
            "speed_mps": row.speed_mps,
            "available_5g": row.metrics_5g["e2e_ms"] is not None,
            "available_sat": row.metrics_sat["e2e_ms"] is not None,
            "availability_ratio": availability_ratio,
            "observed": observed,
            "edge_results": edge_results,
        }

    def _build_edge_result(
        self,
        cfg: EdgeConfig,
        baseline: Dict[str, Optional[float]],
        excess: Dict[str, Optional[float]],
        row: ScenarioRow,
        now_ms: int,
        window_ms: int,
        compute_cloud_ms: float,
    ) -> Tuple[Dict, Dict[str, Optional[float]]]:
        result = {
            "config_id": cfg.config_id,
            "ter_level": cfg.ter,
            "sat_level": cfg.sat,
            "available": {},
            "edge_fraction": {},
            "latency_raw_ms": {},
            "latency_edge_ms": {},
            "latency_gain_ms": {},
            "latency_gain_pct": {},
            "latency_p50_ms": {},
            "latency_p95_ms": {},
            "latency_p99_ms": {},
            "window_fill_ratio": {},
            "compute_ms": {},
            "detour_ms": {},
            "throughput_ul_mbps": {},
            "throughput_dl_mbps": {},
            "throughput_effective_mbps": {},
            "core_traffic_saved_mbps": {},
            "core_traffic_saved_pct": {},
            "beta_video_filter": {},
            "compliance": {"etcs": {}, "voice": {}, "video": {}},
            "compliance_slot": {"etcs": {}, "voice": {}, "video": {}},
            "compliance_mean": {},
            "compliance_min": {},
            "global_compliance": {},
            "worst_service_compliance": {},
        }
        latencies: Dict[str, Optional[float]] = {"5g": None, "sat": None}

        for tech, metrics in (("5g", row.metrics_5g), ("sat", row.metrics_sat)):
            latency_raw = metrics["e2e_ms"]
            edge_fraction = self._edge_fraction(cfg, tech)
            latency, compute_delta, detour_ms = self._edge_latency(
                cfg, tech, baseline, excess, metrics, compute_cloud_ms, edge_fraction
            )
            result["available"][tech] = latency_raw is not None
            result["edge_fraction"][tech] = edge_fraction
            result["latency_raw_ms"][tech] = latency_raw
            result["latency_edge_ms"][tech] = latency
            result["compute_ms"][tech] = compute_delta if latency is not None else None
            result["detour_ms"][tech] = detour_ms if latency is not None else None
            result["throughput_ul_mbps"][tech] = metrics.get("ul_mbps")
            result["throughput_dl_mbps"][tech] = metrics.get("dl_mbps")

            ul_effective, saved, saved_pct, beta = self._video_metrics(cfg, metrics, edge_fraction)
            result["throughput_effective_mbps"][tech] = ul_effective
            result["core_traffic_saved_mbps"][tech] = saved
            result["core_traffic_saved_pct"][tech] = saved_pct
            result["beta_video_filter"][tech] = beta

            if latency is None:
                result["latency_p50_ms"][tech] = None
                result["latency_p95_ms"][tech] = None
                result["latency_p99_ms"][tech] = None
                result["window_fill_ratio"][tech] = 0.0
                for service_key in result["compliance"]:
                    result["compliance"][service_key][tech] = None
                    result["compliance_slot"][service_key][tech] = None
                result["compliance_mean"][tech] = None
                result["compliance_min"][tech] = None
                result["global_compliance"][tech] = None
                result["worst_service_compliance"][tech] = None
                latencies[tech] = None
                continue

            latencies[tech] = latency
            lat_window = self._lat_windows[cfg.config_id][tech]
            lat_window.append((now_ms, latency))
            _trim_window(lat_window, now_ms, window_ms)

            lat_values = [value for _, value in lat_window]
            result["latency_p50_ms"][tech] = _quantile(lat_values, 0.50)
            result["latency_p95_ms"][tech] = _quantile(lat_values, 0.95)
            result["latency_p99_ms"][tech] = _quantile(lat_values, 0.99)
            result["window_fill_ratio"][tech] = self._window_fill_ratio(len(lat_values), window_ms)

            service_compliance = {}
            service_slot = {}
            for service in ("ETCS2", "Voice", "Video"):
                ok = self._check_compliance(service, metrics, latency, cfg)
                service_slot[service] = int(ok)
                window = self._compliance_windows[cfg.config_id][tech][service]
                window.append((now_ms, 1.0 if ok else 0.0))
                _trim_window(window, now_ms, window_ms)
                ratio = sum(flag for _, flag in window) / len(window) if window else None
                service_compliance[service] = ratio
            result["compliance"]["etcs"][tech] = service_compliance["ETCS2"]
            result["compliance"]["voice"][tech] = service_compliance["Voice"]
            result["compliance"]["video"][tech] = service_compliance["Video"]
            result["compliance_slot"]["etcs"][tech] = service_slot["ETCS2"]
            result["compliance_slot"]["voice"][tech] = service_slot["Voice"]
            result["compliance_slot"]["video"][tech] = service_slot["Video"]

            values = [value for value in service_compliance.values() if value is not None]
            compliance_mean = sum(values) / len(values) if values else None
            compliance_min = min(values) if values else None
            result["compliance_mean"][tech] = compliance_mean
            result["compliance_min"][tech] = compliance_min
            result["global_compliance"][tech] = compliance_min
            result["worst_service_compliance"][tech] = compliance_min

            if result["latency_p50_ms"][tech] is not None:
                self._summary_latency[cfg.config_id][tech]["p50"].append(
                    float(result["latency_p50_ms"][tech])
                )
            if result["latency_p95_ms"][tech] is not None:
                self._summary_latency[cfg.config_id][tech]["p95"].append(
                    float(result["latency_p95_ms"][tech])
                )
            if result["latency_p99_ms"][tech] is not None:
                self._summary_latency[cfg.config_id][tech]["p99"].append(
                    float(result["latency_p99_ms"][tech])
                )
            for service in ("ETCS2", "Voice", "Video"):
                ratio = service_compliance[service]
                if ratio is not None:
                    self._summary_compliance[cfg.config_id][tech][service].append(float(ratio))
            if compliance_mean is not None:
                self._summary_compliance_mean[cfg.config_id][tech].append(float(compliance_mean))
            if compliance_min is not None:
                self._summary_compliance_min[cfg.config_id][tech].append(float(compliance_min))
            if saved is not None:
                self._summary_video_saved[cfg.config_id][tech].append(float(saved))
            if saved_pct is not None:
                self._summary_video_saved_pct[cfg.config_id][tech].append(float(saved_pct))

        return result, latencies

    def _update_baseline(
        self,
        tech: str,
        now_ms: int,
        observed: Optional[float],
        window_ms: int,
    ) -> Tuple[Optional[float], Optional[float]]:
        window = self._baseline_windows[tech]
        if observed is not None:
            window.append((now_ms, observed))
        _trim_window(window, now_ms, window_ms)
        bnom = self.edge_params.bnom_5g_ms if tech == "5g" else self.edge_params.bnom_sat_ms
        b_val = bnom
        if window:
            values = [value for _, value in window]
            p05 = _quantile(values, 0.05)
            prev = self._baseline[tech]
            if p05 is not None:
                if prev is None:
                    b_val = p05
                else:
                    b_val = self.edge_params.ewma_lambda * p05 + (1.0 - self.edge_params.ewma_lambda) * prev
            b_val = max(b_val, bnom)

        self._baseline[tech] = b_val
        if observed is None:
            return b_val, None
        return b_val, max(0.0, observed - b_val)

    def _edge_latency(
        self,
        cfg: EdgeConfig,
        tech: str,
        baseline: Dict[str, Optional[float]],
        excess: Dict[str, Optional[float]],
        metrics: Dict[str, Optional[float]],
        compute_cloud_ms: float,
        edge_fraction: float,
    ) -> Tuple[Optional[float], float, float]:
        if metrics["e2e_ms"] is None:
            return None, 0.0, 0.0
        base = baseline[tech] or 0.0
        extra = excess[tech] or 0.0
        alpha = float(self.edge_params.alpha.get(tech, {}).get(cfg.config_id, 1.0))
        edge_fraction = min(1.0, max(0.0, edge_fraction))
        alpha_partial = (1.0 - edge_fraction) + edge_fraction * alpha
        delta_compute_full = self._compute_delta(cfg, tech, compute_cloud_ms)
        delta_compute = edge_fraction * delta_compute_full
        latency = extra + alpha_partial * base + delta_compute
        detour_ms = 0.0
        if tech == "sat" and edge_fraction < 1.0:
            detour_base = self._detour_base_ms(cfg)
            detour_ms = (1.0 - edge_fraction) * detour_base
            latency += detour_ms
            if metrics["e2e_ms"] is not None:
                latency = min(latency, float(metrics["e2e_ms"]))
        return latency, delta_compute, detour_ms

    def _compute_delta(self, cfg: EdgeConfig, tech: str, compute_cloud_ms: float) -> float:
        if tech == "5g":
            if cfg.ter == "TER_BS_EDGE":
                k_loc = self.edge_params.k_loc.get("ter_bs", 1.0)
            elif cfg.ter == "TER_REGIONAL_EDGE":
                k_loc = self.edge_params.k_loc.get("ter_regional", 1.0)
            elif cfg.ter == "TER_NATIONAL":
                k_loc = self.edge_params.k_loc.get("ter_national", 1.0)
            else:
                k_loc = self.edge_params.k_loc.get("cloud", 1.0)
        else:
            if cfg.sat == "SAT_ONBOARD":
                k_loc = self.edge_params.k_loc.get("sat_onboard", 1.0)
            elif cfg.sat == "SAT_GW_EDGE":
                k_loc = self.edge_params.k_loc.get("sat_gw", 1.0)
            else:
                k_loc = self.edge_params.k_loc.get("cloud", 1.0)
        return compute_cloud_ms * (k_loc - 1.0)

    def _sample_compute_cloud(self) -> float:
        mu = self.edge_params.compute_mu
        sigma = self.edge_params.compute_sigma
        sample = float(math.exp(mu + sigma * self._randn()))
        if sample < self.edge_params.compute_min_ms:
            sample = self.edge_params.compute_min_ms
        if sample > self.edge_params.compute_max_ms:
            sample = self.edge_params.compute_max_ms
        return sample

    @staticmethod
    def _randn() -> float:
        return math.sqrt(-2.0 * math.log(max(1e-12, random.random()))) * math.cos(
            2.0 * math.pi * random.random()
        )

    def _check_compliance(
        self,
        service: str,
        metrics: Dict[str, Optional[float]],
        latency: float,
        cfg: EdgeConfig,
    ) -> bool:
        thresholds = self.edge_params.kpi_thresholds[service]
        jitter = metrics.get("jitter_ms") or 0.0
        loss = metrics.get("loss") or 0.0
        throughput = self._throughput_for_service(service, metrics, cfg)
        if throughput is None:
            throughput = -1.0
        return (
            latency <= thresholds["latency_ms"]
            and jitter <= thresholds["jitter_ms"]
            and loss <= thresholds.get("loss_ratio", thresholds.get("loss", 0.0))
            and throughput >= thresholds["throughput_mbps"]
        )

    def _throughput(self, metrics: Dict[str, Optional[float]]) -> Optional[float]:
        ul = metrics.get("ul_mbps")
        dl = metrics.get("dl_mbps")
        if ul is None and dl is None:
            return None
        return (ul or 0.0) + (dl or 0.0)

    def _throughput_for_service(
        self,
        service: str,
        metrics: Dict[str, Optional[float]],
        cfg: EdgeConfig,
    ) -> Optional[float]:
        if service == "Video":
            return metrics.get("ul_mbps")
        return self._throughput(metrics)

    def _video_metrics(
        self,
        cfg: EdgeConfig,
        metrics: Dict[str, Optional[float]],
        edge_fraction: float,
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        ul = metrics.get("ul_mbps")
        if ul is None:
            return None, None, None, None
        beta = self._beta_for_config(cfg)
        if not cfg.video_filter:
            beta = 1.0
        edge_fraction = min(1.0, max(0.0, edge_fraction))
        ul_effective = ul * (1.0 - edge_fraction * (1.0 - beta))
        saved = ul - ul_effective
        saved_pct = saved / ul if ul > 0 else None
        return ul_effective, saved, saved_pct, beta

    def _beta_for_config(self, cfg: EdgeConfig) -> float:
        level_key = f"{cfg.ter}__{cfg.sat}"
        if level_key in self.edge_params.beta_video_filter_by_level:
            return self.edge_params.beta_video_filter_by_level[level_key]
        if cfg.config_id in self.edge_params.beta_video_filter_by_config:
            return self.edge_params.beta_video_filter_by_config[cfg.config_id]
        return self.edge_params.beta_video_filter
