from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import math


class P2Quantile:
    def __init__(self, p: float) -> None:
        self.p = p
        self.count = 0
        self.q = [0.0] * 5
        self.n = [0, 0, 0, 0, 0]
        self.np = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.dn = [0.0, 0.0, 0.0, 0.0, 0.0]

    def add(self, x: float) -> None:
        if self.count < 5:
            self.q[self.count] = x
            self.count += 1
            if self.count == 5:
                self.q.sort()
                self.n = [1, 2, 3, 4, 5]
                self.np = [1, 1 + 2 * self.p, 1 + 4 * self.p, 3 + 2 * self.p, 5]
                self.dn = [0, self.p / 2, self.p, (1 + self.p) / 2, 1]
            return

        k = 0
        if x < self.q[0]:
            self.q[0] = x
            k = 0
        elif x < self.q[1]:
            k = 0
        elif x < self.q[2]:
            k = 1
        elif x < self.q[3]:
            k = 2
        elif x < self.q[4]:
            k = 3
        else:
            self.q[4] = x
            k = 3

        for i in range(k + 1, 5):
            self.n[i] += 1
        for i in range(5):
            self.np[i] += self.dn[i]

        for i in range(1, 4):
            d = self.np[i] - self.n[i]
            if (d >= 1 and self.n[i + 1] - self.n[i] > 1) or (
                d <= -1 and self.n[i - 1] - self.n[i] < -1
            ):
                d_sign = int(math.copysign(1, d))
                q_new = self._parabolic(i, d_sign)
                if self.q[i - 1] < q_new < self.q[i + 1]:
                    self.q[i] = q_new
                else:
                    self.q[i] = self._linear(i, d_sign)
                self.n[i] += d_sign

    def _parabolic(self, i: int, d: int) -> float:
        n0, n1, n2 = self.n[i - 1], self.n[i], self.n[i + 1]
        q0, q1, q2 = self.q[i - 1], self.q[i], self.q[i + 1]
        return q1 + d / (n2 - n0) * (
            (n1 - n0 + d) * (q2 - q1) / (n2 - n1)
            + (n2 - n1 - d) * (q1 - q0) / (n1 - n0)
        )

    def _linear(self, i: int, d: int) -> float:
        return self.q[i] + d * (self.q[i + d] - self.q[i]) / (self.n[i + d] - self.n[i])

    def value(self) -> Optional[float]:
        if self.count == 0:
            return None
        if self.count < 5:
            values = sorted(self.q[: self.count])
            idx = int(math.ceil(self.p * self.count)) - 1
            return values[max(0, min(idx, self.count - 1))]
        return self.q[2]


@dataclass
class MetricsCollector:
    kpi_thresholds: Dict[str, Dict[str, float]]
    train_total: Dict[int, int] = field(default_factory=dict)
    train_satisfied: Dict[int, int] = field(default_factory=dict)
    p95_voice: P2Quantile = field(default_factory=lambda: P2Quantile(0.95))
    p95_video: P2Quantile = field(default_factory=lambda: P2Quantile(0.95))
    p95_e2e: P2Quantile = field(default_factory=lambda: P2Quantile(0.95))
    p50_e2e: P2Quantile = field(default_factory=lambda: P2Quantile(0.50))
    p95_access: P2Quantile = field(default_factory=lambda: P2Quantile(0.95))
    p95_compute: P2Quantile = field(default_factory=lambda: P2Quantile(0.95))
    p99_e2e: P2Quantile = field(default_factory=lambda: P2Quantile(0.99))
    p99_access: P2Quantile = field(default_factory=lambda: P2Quantile(0.99))
    p999_e2e: P2Quantile = field(default_factory=lambda: P2Quantile(0.999))
    p999_access: P2Quantile = field(default_factory=lambda: P2Quantile(0.999))
    access_queue_p95: P2Quantile = field(default_factory=lambda: P2Quantile(0.95))
    access_spike_count: int = 0
    access_spike_prob_sum: float = 0.0
    access_spike_samples: int = 0
    detour_volume_bytes: int = 0
    delivered_packets: int = 0
    e2e_latency_sum: float = 0.0
    detour_packets: int = 0
    detour_latency_p95: P2Quantile = field(default_factory=lambda: P2Quantile(0.95))
    detour_latency_p99: P2Quantile = field(default_factory=lambda: P2Quantile(0.99))
    detour_queue_p95: P2Quantile = field(default_factory=lambda: P2Quantile(0.95))
    access_latency_sum: float = 0.0
    transport_to_edge_sum: float = 0.0
    compute_latency_sum: float = 0.0
    transport_return_sum: float = 0.0
    detour_latency_sum: float = 0.0
    flow_total: Dict[tuple[int, str], int] = field(default_factory=dict)
    flow_detour: Dict[tuple[int, str], int] = field(default_factory=dict)

    def record_packet(
        self,
        train_id: int,
        app_type: str,
        latency_ms: Optional[float],
        jitter_ms: Optional[float],
        loss_flag: int,
        throughput_mbps: float,
        access_latency_ms: Optional[float],
        transport_to_edge_ms: Optional[float],
        compute_latency_ms: Optional[float],
        transport_return_ms: Optional[float],
        detour_latency_ms: float,
        detour_queue_ms: float,
        size_bytes: int,
    ) -> None:
        self.train_total[train_id] = self.train_total.get(train_id, 0) + 1
        satisfied = 0
        if loss_flag == 0 and latency_ms is not None and jitter_ms is not None:
            thresholds = self.kpi_thresholds[app_type]
            satisfied = int(
                latency_ms <= thresholds["latency_ms"]
                and jitter_ms <= thresholds["jitter_ms"]
                and throughput_mbps >= thresholds["throughput_mbps"]
            )
        self.train_satisfied[train_id] = self.train_satisfied.get(train_id, 0) + satisfied

        if loss_flag == 0 and latency_ms is not None:
            self.delivered_packets += 1
            self.e2e_latency_sum += latency_ms
            self.p95_e2e.add(latency_ms)
            self.p50_e2e.add(latency_ms)
            self.p99_e2e.add(latency_ms)
            self.p999_e2e.add(latency_ms)
            if compute_latency_ms is not None and compute_latency_ms > 0:
                self.p95_compute.add(compute_latency_ms)
            if app_type == "Voice":
                self.p95_voice.add(latency_ms)
            if app_type == "Video":
                self.p95_video.add(latency_ms)

            flow_key = (train_id, app_type)
            self.flow_total[flow_key] = self.flow_total.get(flow_key, 0) + 1
            if detour_latency_ms > 0:
                self.detour_packets += 1
                self.flow_detour[flow_key] = self.flow_detour.get(flow_key, 0) + 1
                self.detour_latency_p95.add(detour_latency_ms)
                self.detour_latency_p99.add(detour_latency_ms)
                self.detour_queue_p95.add(detour_queue_ms)

            if access_latency_ms is not None:
                self.access_latency_sum += access_latency_ms
            if transport_to_edge_ms is not None:
                self.transport_to_edge_sum += transport_to_edge_ms
            if compute_latency_ms is not None:
                self.compute_latency_sum += compute_latency_ms
            if transport_return_ms is not None:
                self.transport_return_sum += transport_return_ms
            self.detour_latency_sum += detour_latency_ms

        if detour_latency_ms > 0:
            self.detour_volume_bytes += size_bytes

    def compliance_per_train(self) -> Dict[int, float]:
        compliances: Dict[int, float] = {}
        for train_id, total in self.train_total.items():
            satisfied = self.train_satisfied.get(train_id, 0)
            compliances[train_id] = satisfied / total if total else 0.0
        return compliances

    def mean_access_latency(self) -> float:
        if self.delivered_packets == 0:
            return 0.0
        return self.access_latency_sum / self.delivered_packets

    def mean_transport_to_edge(self) -> float:
        if self.delivered_packets == 0:
            return 0.0
        return self.transport_to_edge_sum / self.delivered_packets

    def mean_compute_latency(self) -> float:
        if self.delivered_packets == 0:
            return 0.0
        return self.compute_latency_sum / self.delivered_packets

    def mean_transport_return(self) -> float:
        if self.delivered_packets == 0:
            return 0.0
        return self.transport_return_sum / self.delivered_packets

    def mean_detour_latency(self) -> float:
        if self.delivered_packets == 0:
            return 0.0
        return self.detour_latency_sum / self.delivered_packets

    def record_access_sample(self, access_rtt_ms: float, access_queue_rtt_ms: float) -> None:
        self.p95_access.add(access_rtt_ms)
        self.p99_access.add(access_rtt_ms)
        self.p999_access.add(access_rtt_ms)
        self.access_queue_p95.add(access_queue_rtt_ms)

    def record_spike_event(self, p_spike: float, spike_flag: bool) -> None:
        self.access_spike_prob_sum += p_spike
        self.access_spike_samples += 1
        if spike_flag:
            self.access_spike_count += 1

    def p_spike_mean(self) -> float:
        if self.access_spike_samples == 0:
            return 0.0
        return self.access_spike_prob_sum / self.access_spike_samples

    def access_queue_p95_value(self) -> float:
        return self.access_queue_p95.value() or 0.0

    def p95_access_latency(self) -> float:
        return self.p95_access.value() or 0.0

    def p95_compute_latency(self) -> float:
        return self.p95_compute.value() or 0.0

    def p99_access_latency(self) -> float:
        return self.p99_access.value() or 0.0

    def p999_access_latency(self) -> float:
        return self.p999_access.value() or 0.0

    def p99_e2e_latency(self) -> float:
        return self.p99_e2e.value() or 0.0

    def p999_e2e_latency(self) -> float:
        return self.p999_e2e.value() or 0.0

    def detour_time_fraction(self) -> float:
        if self.e2e_latency_sum == 0:
            return 0.0
        return self.detour_latency_sum / self.e2e_latency_sum

    def detour_packet_ratio(self) -> float:
        if self.delivered_packets == 0:
            return 0.0
        return self.detour_packets / self.delivered_packets

    def detour_p95(self) -> float:
        return self.detour_latency_p95.value() or 0.0

    def detour_p99(self) -> float:
        return self.detour_latency_p99.value() or 0.0

    def detour_queue_p95_value(self) -> float:
        return self.detour_queue_p95.value() or 0.0
