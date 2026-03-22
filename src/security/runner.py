from __future__ import annotations

import csv
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class BaselineRow:
    time_ms: int
    metrics_5g: Dict[str, Optional[float]]
    metrics_sat: Dict[str, Optional[float]]


@dataclass(frozen=True)
class AttackRow:
    time_ms: int
    time_iso: str
    attack_active: bool
    attack_type: Optional[str]
    target: Optional[str]
    intensity: float
    mitigation_active: bool


@dataclass(frozen=True)
class AttackState:
    attack_active: bool
    attack_type: str
    target: str
    intensity: float
    mitigation_active: bool


ATTACK_EFFECTS: Dict[str, Dict[str, float]] = {
    "dos": {
        "latency_ms": 60.0,
        "jitter_ms": 20.0,
        "loss": 0.02,
        "throughput_mbps": -8.0,
    },
    "jamming": {
        "latency_ms": 30.0,
        "jitter_ms": 12.0,
        "loss": 0.015,
        "throughput_mbps": -6.0,
    },
    "latency_spike": {"latency_ms": 80.0, "jitter_ms": 6.0},
    "loss": {"loss": 0.05},
    "edge_overload": {"compute_ms": 25.0},
}

DEFAULT_EFFECT: Dict[str, float] = {
    "latency_ms": 20.0,
    "jitter_ms": 5.0,
    "loss": 0.01,
    "throughput_mbps": -3.0,
}


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


def _parse_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    raw = str(value).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _throughput(metrics: Dict[str, Optional[float]]) -> Optional[float]:
    ul = metrics.get("ul_mbps")
    dl = metrics.get("dl_mbps")
    if ul is None and dl is None:
        return None
    if ul is None:
        return dl
    if dl is None:
        return ul
    return min(ul, dl)


def load_baseline(csv_path: Path) -> List[BaselineRow]:
    rows: List[BaselineRow] = []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"time"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("Baseline CSV missing required columns")
        for record in reader:
            time_ms = _parse_time_ms(record.get("time", ""))
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
                BaselineRow(
                    time_ms=time_ms,
                    metrics_5g=metrics_5g,
                    metrics_sat=metrics_sat,
                )
            )
    rows.sort(key=lambda row: row.time_ms)
    return rows


def load_attack_scenario(csv_path: Path) -> List[AttackRow]:
    rows: List[AttackRow] = []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"time"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("Attack CSV missing required columns")
        for record in reader:
            time_ms = _parse_time_ms(record.get("time", ""))
            rows.append(
                AttackRow(
                    time_ms=time_ms,
                    time_iso=_format_time_ms(time_ms),
                    attack_active=_parse_bool(record.get("attack_active")),
                    attack_type=(record.get("attack_type") or None),
                    target=(record.get("target") or None),
                    intensity=float(record.get("intensity") or 0.0),
                    mitigation_active=_parse_bool(record.get("mitigation_active")),
                )
            )
    rows.sort(key=lambda row: row.time_ms)
    return rows


def build_attack_rows_from_baseline(baseline_rows: List[BaselineRow]) -> List[AttackRow]:
    rows: List[AttackRow] = []
    for row in baseline_rows:
        rows.append(
            AttackRow(
                time_ms=row.time_ms,
                time_iso=_format_time_ms(row.time_ms),
                attack_active=False,
                attack_type=None,
                target=None,
                intensity=0.0,
                mitigation_active=False,
            )
        )
    return rows


def _effect_for(attack_type: str) -> Dict[str, float]:
    return ATTACK_EFFECTS.get(attack_type.lower(), DEFAULT_EFFECT)


def _clamp(value: Optional[float], minimum: float, maximum: Optional[float] = None) -> Optional[float]:
    if value is None:
        return None
    if maximum is not None:
        value = min(value, maximum)
    return max(value, minimum)


class SecurityRunner:
    def __init__(
        self,
        scenario_name: str,
        slot_ms: int,
        attack_rows: List[AttackRow],
        baseline_rows: List[BaselineRow],
        attack_csv_path: Optional[Path],
        baseline_csv_path: Path,
        output_root: Path,
        default_attack_type: str,
        default_target: str,
        mode: str,
    ) -> None:
        self.scenario_name = scenario_name
        self.slot_ms = slot_ms
        self.attack_rows = attack_rows
        self.baseline_rows = baseline_rows
        self.attack_csv_path = attack_csv_path
        self.baseline_csv_path = baseline_csv_path
        self.output_root = output_root
        self.default_attack_type = default_attack_type
        self.default_target = default_target
        self.mode = mode
        self.state = "stopped"
        self.last_error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_slot: Optional[Dict] = None
        self.run_dir: Optional[Path] = None
        self._attack_state = AttackState(
            attack_active=False,
            attack_type=default_attack_type,
            target=default_target,
            intensity=0.0,
            mitigation_active=False,
        )

    def start(self, start_time: Optional[datetime]) -> str:
        if self.state == "running":
            return _format_time_ms(int(time.time() * 1000))
        self.state = "running"
        self.last_error = None
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, args=(start_time,), daemon=True)
        self._thread.start()
        return _format_time_ms(int(time.time() * 1000))

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

    def set_attack(
        self,
        attack_active: Optional[bool] = None,
        attack_type: Optional[str] = None,
        target: Optional[str] = None,
        intensity: Optional[float] = None,
        mitigation_active: Optional[bool] = None,
    ) -> Dict[str, object]:
        with self._lock:
            current = self._attack_state
            new_attack_active = attack_active if attack_active is not None else current.attack_active
            new_attack_type = attack_type if attack_type is not None else current.attack_type
            new_target = target if target is not None else current.target
            new_intensity = intensity if intensity is not None else current.intensity
            new_mitigation = mitigation_active if mitigation_active is not None else current.mitigation_active
            if new_attack_type is None:
                new_attack_type = self.default_attack_type
            if new_target is None:
                new_target = self.default_target
            try:
                new_intensity_val = float(new_intensity)
            except (TypeError, ValueError):
                new_intensity_val = current.intensity
            new_intensity_val = max(0.0, min(1.0, new_intensity_val))
            self._attack_state = AttackState(
                attack_active=bool(new_attack_active),
                attack_type=str(new_attack_type),
                target=str(new_target).lower(),
                intensity=new_intensity_val,
                mitigation_active=bool(new_mitigation),
            )
            return {
                "attack_active": self._attack_state.attack_active,
                "attack_type": self._attack_state.attack_type,
                "target": self._attack_state.target,
                "intensity": self._attack_state.intensity,
                "mitigation_active": self._attack_state.mitigation_active,
            }

    def _get_attack_state(self) -> AttackState:
        with self._lock:
            return self._attack_state

    def _run_loop(self, start_time: Optional[datetime]) -> None:
        try:
            if start_time is not None:
                now = datetime.now(timezone.utc)
                delay = (start_time - now).total_seconds()
                if delay > 0:
                    time.sleep(delay)

            start_dt = start_time or datetime.now(timezone.utc)
            run_stamp = start_dt.strftime("%Y%m%dT%H%M%SZ")
            run_dir = self.output_root / self.scenario_name / run_stamp
            run_dir.mkdir(parents=True, exist_ok=True)
            self.run_dir = run_dir

            self._write_config_used(run_dir, start_dt)

            output_path = run_dir / "slot_metrics.jsonl"
            with output_path.open("a", encoding="utf-8") as handle:
                t_rt0_ms = int(time.time() * 1000)
                t_csv0_ms = self.attack_rows[0].time_ms if self.attack_rows else t_rt0_ms
                next_tick_ms = t_rt0_ms
                idx = 0
                baseline_idx = 0

                while not self._stop_event.is_set():
                    now_ms = int(time.time() * 1000)
                    if now_ms < next_tick_ms:
                        time.sleep((next_tick_ms - now_ms) / 1000.0)
                        continue

                    now_ms = int(time.time() * 1000)
                    scenario_ms = t_csv0_ms + (now_ms - t_rt0_ms)
                    while idx < len(self.attack_rows) and self.attack_rows[idx].time_ms < scenario_ms:
                        idx += 1
                    if idx >= len(self.attack_rows):
                        break

                    while (
                        baseline_idx + 1 < len(self.baseline_rows)
                        and self.baseline_rows[baseline_idx + 1].time_ms <= scenario_ms
                    ):
                        baseline_idx += 1
                    baseline_row = self.baseline_rows[baseline_idx] if self.baseline_rows else None

                    row = self.attack_rows[idx]
                    slot = self._build_slot(row, baseline_row, scenario_ms)
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

    def _baseline_metrics(self, row: Optional[BaselineRow], target: str) -> Dict[str, Optional[float]]:
        if target == "edge":
            return {
                "latency_ms": None,
                "jitter_ms": None,
                "loss": None,
                "throughput_mbps": None,
                "compute_ms": 0.0,
            }
        if row is None:
            return {
                "latency_ms": None,
                "jitter_ms": None,
                "loss": None,
                "throughput_mbps": None,
                "compute_ms": None,
            }
        metrics = row.metrics_5g if target == "5g" else row.metrics_sat
        return {
            "latency_ms": metrics.get("e2e_ms"),
            "jitter_ms": metrics.get("jitter_ms"),
            "loss": metrics.get("loss"),
            "throughput_mbps": _throughput(metrics),
            "compute_ms": None,
        }

    def _apply_attack(
        self,
        baseline: Dict[str, Optional[float]],
        attack_type: str,
        active: bool,
        intensity: float,
    ) -> Dict[str, Dict[str, Optional[float]]]:
        if not active or intensity <= 0:
            impacted = {key: baseline.get(key) for key in baseline}
            return {"impacted": impacted, "impact": {key: 0.0 for key in baseline}}

        effect = _effect_for(attack_type)
        impact: Dict[str, Optional[float]] = {}
        impacted: Dict[str, Optional[float]] = {}
        for key in ["latency_ms", "jitter_ms", "loss", "throughput_mbps", "compute_ms"]:
            delta = effect.get(key, 0.0) * intensity
            impact[key] = delta
            base = baseline.get(key)
            if base is None:
                impacted[key] = None
                continue
            value = base + delta
            if key in {"latency_ms", "jitter_ms", "compute_ms"}:
                impacted[key] = _clamp(value, 0.0)
            elif key == "loss":
                impacted[key] = _clamp(value, 0.0, 1.0)
            elif key == "throughput_mbps":
                impacted[key] = _clamp(value, 0.0)
            else:
                impacted[key] = value
        return {"impacted": impacted, "impact": impact}

    def _build_slot(self, row: AttackRow, baseline_row: Optional[BaselineRow], now_ms: int) -> Dict:
        if self.mode == "interactive":
            state = self._get_attack_state()
            attack_type = state.attack_type or self.default_attack_type
            target = state.target or self.default_target
            attack_active = state.attack_active
            intensity = state.intensity
            mitigation_active = state.mitigation_active
        else:
            attack_type = row.attack_type or self.default_attack_type
            target = row.target or self.default_target
            attack_active = row.attack_active
            intensity = row.intensity
            mitigation_active = row.mitigation_active

        target = str(target).lower()
        if target not in {"5g", "sat", "edge"}:
            target = self.default_target

        baseline = self._baseline_metrics(baseline_row, target)
        result = self._apply_attack(baseline, attack_type, attack_active, intensity)
        t0 = self.attack_rows[0].time_ms if self.attack_rows else row.time_ms
        t_rel_s = max(0.0, (row.time_ms - t0) / 1000.0)

        return {
            "timestamp": row.time_iso,
            "t_rel_s": t_rel_s,
            "scenario": self.scenario_name,
            "target_segment": target,
            "attack_type": attack_type,
            "attack_active": attack_active,
            "attack_intensity": intensity,
            "mitigation_active": mitigation_active,
            "baseline": baseline,
            "impacted": result["impacted"],
            "impact": result["impact"],
        }

    def _write_config_used(self, run_dir: Path, start_dt: datetime) -> None:
        config_used = {
            "scenario_name": self.scenario_name,
            "attack_csv_path": str(self.attack_csv_path) if self.attack_csv_path else None,
            "baseline_csv_path": str(self.baseline_csv_path),
            "slot_ms": self.slot_ms,
            "default_attack_type": self.default_attack_type,
            "default_target_segment": self.default_target,
            "mode": self.mode,
            "start_timestamp": start_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "output_root": str(self.output_root),
        }
        (run_dir / "config_used.json").write_text(json.dumps(config_used, indent=2), encoding="utf-8")

    def _write_summary(self, run_dir: Path) -> None:
        summary = {
            "scenario_name": self.scenario_name,
            "slots": len(self.attack_rows),
            "attack_type": self.default_attack_type,
            "target_segment": self.default_target,
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
