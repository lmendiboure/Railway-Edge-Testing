from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from src.core.state import CorridorSegment, TrainState


def _choose_segment_type(rng: np.random.Generator, weights: Dict[str, float]) -> str:
    types = list(weights.keys())
    probs = np.array([weights[t] for t in types], dtype=float)
    probs = probs / probs.sum()
    idx = rng.choice(len(types), p=probs)
    return types[idx]


def _sample_length_km(
    rng: np.random.Generator, bounds_km: Dict[str, Tuple[float, float]], segment_type: str
) -> float:
    low, high = bounds_km[segment_type]
    return float(rng.uniform(low, high))


def generate_corridor(
    rng: np.random.Generator,
    total_distance_m: float,
    segment_lengths_km: Dict[str, Tuple[float, float]],
    segment_weights: Dict[str, float],
) -> List[CorridorSegment]:
    segments: List[CorridorSegment] = []
    covered_m = 0.0
    while covered_m < total_distance_m:
        segment_type = _choose_segment_type(rng, segment_weights)
        length_km = _sample_length_km(rng, segment_lengths_km, segment_type)
        length_m = length_km * 1000.0
        segments.append(CorridorSegment(segment_type=segment_type, length_m=length_m))
        covered_m += length_m
    return segments


def advance_train(train: TrainState, dt_s: float) -> bool:
    distance = train.speed_m_s * dt_s
    train.position_m += distance
    remaining = distance
    segment_changed = False
    while remaining > 0:
        current_segment = train.corridor[train.segment_index]
        left = current_segment.length_m - train.segment_offset_m
        if remaining < left:
            train.segment_offset_m += remaining
            remaining = 0
        else:
            remaining -= left
            train.segment_index = min(train.segment_index + 1, len(train.corridor) - 1)
            train.segment_offset_m = 0.0
            segment_changed = True
    return segment_changed
