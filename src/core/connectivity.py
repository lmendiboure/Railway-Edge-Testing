from __future__ import annotations

from typing import Dict

import numpy as np

from src.core.state import TrainState


def resolve_connectivity_state(
    segment_type: str, tunnel_mode: str, override: str, mapping: Dict[str, str]
) -> str:
    if override == "LEO_ONLY_STRICT":
        return "LEO_ONLY"
    state = mapping.get(segment_type, "NONE")
    if state == "TUNNEL_MODE":
        return tunnel_mode
    return state


def update_state_spike(
    rng: np.random.Generator, train: TrainState, state_changed: bool, config: Dict[str, float]
) -> None:
    if not state_changed:
        return
    low, high = config["state_change_spike_ms"]
    dur_low, dur_high = config["state_change_duration_ms"]
    train.state_spike_ms = float(rng.uniform(low, high))
    train.state_spike_remaining_ms = float(rng.uniform(dur_low, dur_high))


def tick_spikes(train: TrainState, dt_ms: float) -> None:
    if train.state_spike_remaining_ms > 0:
        train.state_spike_remaining_ms = max(0.0, train.state_spike_remaining_ms - dt_ms)
        if train.state_spike_remaining_ms == 0:
            train.state_spike_ms = 0.0
    if train.beam_spike_remaining_ms > 0:
        train.beam_spike_remaining_ms = max(0.0, train.beam_spike_remaining_ms - dt_ms)
        if train.beam_spike_remaining_ms == 0:
            train.beam_spike_ms = 0.0
