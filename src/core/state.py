from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CorridorSegment:
    segment_type: str
    length_m: float


@dataclass
class Packet:
    packet_id: int
    train_id: int
    app_type: str
    size_bytes: int
    gen_time_ms: float
    access: str
    compute_enqueue_time_ms: float = 0.0
    compute_latency_ms: float = 0.0
    shaping_arrival_ms: float = 0.0
    detour_latency_ms: float = 0.0
    detour_queue_ms: float = 0.0


@dataclass
class FlowState:
    app_type: str
    packet_size_bytes: int
    interval_ms: float
    next_time_ms: float
    last_latency_ms: Optional[float] = None
    delivered_bytes_window: Deque[Tuple[float, int]] = field(default_factory=deque)


@dataclass
class TrainState:
    train_id: int
    region_id: int
    position_m: float
    speed_m_s: float
    corridor: List[CorridorSegment]
    segment_index: int
    segment_offset_m: float
    connectivity_state: str
    access: Optional[str]
    bs_id: str
    beam_id: str
    gw_id: str
    flows: Dict[str, FlowState]
    state_spike_ms: float = 0.0
    state_spike_remaining_ms: float = 0.0
    beam_spike_ms: float = 0.0
    beam_spike_remaining_ms: float = 0.0


@dataclass
class ComputeNode:
    node_id: str
    mu_pkt_s: float
    q_max: int
    service_kappa: float = 1.0
    queue: Deque[Packet] = field(default_factory=deque)
    processed_packets: int = 0
    dropped_packets: int = 0
    queue_len_sum: int = 0
    queue_len_steps: int = 0
    max_queue_len: int = 0
    service_time_sum_ms: float = 0.0

    def record_occupancy(self) -> None:
        current_len = len(self.queue)
        self.queue_len_sum += current_len
        self.queue_len_steps += 1
        if current_len > self.max_queue_len:
            self.max_queue_len = current_len


@dataclass
class ShapingNode:
    node_id: str
    queues: Dict[str, Deque[Packet]] = field(default_factory=dict)
    queue_len_sum: int = 0
    queue_len_steps: int = 0
    last_utilization: float = 0.0
    spike_remaining_steps: int = 0
    spike_amp_ms: float = 0.0

    def ensure_app(self, app_type: str) -> None:
        if app_type not in self.queues:
            self.queues[app_type] = deque()

    def record_occupancy(self) -> None:
        total_len = sum(len(queue) for queue in self.queues.values())
        self.queue_len_sum += total_len
        self.queue_len_steps += 1
