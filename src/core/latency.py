from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np


def _bounded_normal(
    rng: np.random.Generator, mean: float, min_val: float, max_val: float, sigma: float
) -> float:
    value = float(rng.normal(mean, sigma))
    if value < min_val:
        return min_val
    if value > max_val:
        return max_val
    return value


def _sigma_from_range(min_val: float, max_val: float) -> float:
    sigma = (max_val - min_val) / 4.0
    if sigma < 3.0:
        return 3.0
    if sigma > 5.0:
        return 5.0
    return sigma


def _leo_elevation(segment_type: str, rng: np.random.Generator) -> Optional[str]:
    if segment_type == "OPEN":
        return "HIGH" if rng.random() < 0.6 else "MID"
    if segment_type == "STATION":
        return "HIGH"
    if segment_type == "RURAL_GAP":
        return "MID"
    if segment_type == "CUTTING":
        return "MID" if rng.random() < 0.5 else "LOW"
    if segment_type == "TUNNEL":
        return None
    return "MID"


def _radio_queue_delay_ms(access_type: str, utilization: float, access_load: Dict) -> float:
    q_max = access_load.get("radio_queue_max_ms", {}).get(access_type)
    if q_max is None:
        q_max = 15.0 if access_type == "5G" else 25.0
    u_eff = max(0.0, utilization)
    if u_eff > 2.0:
        u_eff = 2.0
    return float(q_max) * (u_eff ** 2)


def _spike_params(access_type: str, utilization: float, access_load: Dict) -> Tuple[float, Tuple[float, float]]:
    p_base = access_load.get("spike_prob_base", {}).get(access_type)
    p_slope = access_load.get("spike_prob_slope", {}).get(access_type)
    amp_range = access_load.get("spike_amp_range_ms", {}).get(access_type)
    if p_base is None:
        p_base = 0.01 if access_type == "5G" else 0.02
    if p_slope is None:
        p_slope = 0.2 if access_type == "5G" else 0.3
    if amp_range is None:
        amp_range = (5.0, 15.0) if access_type == "5G" else (10.0, 25.0)
    p_spike = min(0.5, float(p_base) + float(p_slope) * max(0.0, utilization))
    return p_spike, (float(amp_range[0]), float(amp_range[1]))


def access_spike_parameters(
    access_type: str, utilization: float, access_load: Dict
) -> Tuple[float, float, float]:
    p_spike, amp_range = _spike_params(access_type, utilization, access_load)
    return p_spike, amp_range[0], amp_range[1]


def spike_duration_steps(access_type: str, utilization: float, access_load: Dict, rng: np.random.Generator) -> int:
    config = access_load.get("spike_duration_steps", {})
    defaults = {"base": 1.0, "slope": 4.0, "max": 10}
    params = config.get(access_type, defaults)
    base = float(params.get("base", defaults["base"]))
    slope = float(params.get("slope", defaults["slope"]))
    max_steps = int(params.get("max", defaults["max"]))

    mean_steps = max(1.0, base + slope * max(0.0, utilization))
    q = 1.0 / mean_steps
    if q < 0.1:
        q = 0.1
    if q > 1.0:
        q = 1.0
    steps = int(rng.geometric(q))
    if steps < 1:
        steps = 1
    if steps > max_steps:
        steps = max_steps
    return steps


def sample_access_latency_ms(
    access_type: str,
    segment_type: str,
    rng: np.random.Generator,
    utilization: float,
    access_load: Dict,
    spike_flag: Optional[bool] = None,
    spike_amp: Optional[float] = None,
) -> Tuple[Optional[float], float, float, float, bool]:
    if access_type == "5G":
        table: Dict[str, Tuple[float, float, float]] = {
            "STATION": (12.0, 10.0, 15.0),
            "OPEN": (15.0, 12.0, 18.0),
            "CUTTING": (20.0, 15.0, 25.0),
            "TUNNEL": (28.0, 20.0, 35.0),
            "RURAL_GAP": (30.0, 20.0, 40.0),
        }
        mean, min_val, max_val = table.get(segment_type, (15.0, 12.0, 18.0))
        sigma = _sigma_from_range(min_val, max_val)
        base = _bounded_normal(rng, mean, min_val, max_val, sigma)
        radio_q = _radio_queue_delay_ms(access_type, utilization, access_load)
        p_spike, amp_range = _spike_params(access_type, utilization, access_load)
        if spike_flag is None:
            spike_flag = rng.random() < p_spike
        if spike_amp is None:
            spike_amp = float(rng.uniform(amp_range[0], amp_range[1])) * (1.0 + max(0.0, utilization))
        spike = spike_amp if spike_flag else 0.0
        return base + radio_q + spike, radio_q, spike, p_spike, spike_flag

    if access_type == "LEO":
        elevation = _leo_elevation(segment_type, rng)
        if elevation is None:
            return None, 0.0, 0.0, 0.0, False
        table = {
            "HIGH": (30.0, 25.0, 35.0),
            "MID": (45.0, 35.0, 50.0),
            "LOW": (65.0, 50.0, 80.0),
        }
        mean, min_val, max_val = table[elevation]
        sigma = _sigma_from_range(min_val, max_val)
        base = _bounded_normal(rng, mean, min_val, max_val, sigma)
        radio_q = _radio_queue_delay_ms(access_type, utilization, access_load)
        p_spike, amp_range = _spike_params(access_type, utilization, access_load)
        if spike_flag is None:
            spike_flag = rng.random() < p_spike
        if spike_amp is None:
            spike_amp = float(rng.uniform(amp_range[0], amp_range[1])) * (1.0 + max(0.0, utilization))
        spike = spike_amp if spike_flag else 0.0
        return base + radio_q + spike, radio_q, spike, p_spike, spike_flag

    return None, 0.0, 0.0, 0.0, False


def mean_access_latency_ms(access_type: str, segment_type: str) -> Optional[float]:
    if access_type == "5G":
        table = {
            "STATION": 12.0,
            "OPEN": 15.0,
            "CUTTING": 20.0,
            "TUNNEL": 28.0,
            "RURAL_GAP": 30.0,
        }
        return table.get(segment_type, 15.0)
    if access_type == "LEO":
        if segment_type == "TUNNEL":
            return None
        if segment_type == "OPEN":
            return (30.0 + 45.0) / 2.0
        if segment_type == "STATION":
            return 30.0
        if segment_type == "RURAL_GAP":
            return 45.0
        if segment_type == "CUTTING":
            return (45.0 + 65.0) / 2.0
        return 45.0
    return None


def expected_access_rtt_ms(
    access_type: str, segment_type: str, utilization: float, access_load: Dict
) -> Optional[float]:
    base = mean_access_latency_ms(access_type, segment_type)
    if base is None:
        return None
    radio_q = _radio_queue_delay_ms(access_type, utilization, access_load)
    return 2.0 * (base + radio_q)


def transport_to_edge_latency_ms(
    access_type: str, segment_type: str, ter_mode: str, sat_mode: str
) -> float:
    if access_type == "5G":
        base_map = {
            "TER_BS_EDGE": 2.0,
            "TER_REGIONAL_EDGE": 8.0,
            "TER_NATIONAL": 20.0,
            "TER_NO_EDGE": 20.0,
        }
        base = base_map.get(ter_mode, 20.0)
        if segment_type == "RURAL_GAP" and ter_mode in {"TER_REGIONAL_EDGE", "TER_NATIONAL", "TER_NO_EDGE"}:
            base += 5.0
        return base

    if access_type == "LEO":
        if sat_mode == "SAT_ONBOARD":
            return 0.5
        if sat_mode.startswith("SAT_GW_EDGE"):
            return 3.0
        if sat_mode == "SAT_TRANSPARENT":
            return 20.0
        return 20.0

    return 0.0
