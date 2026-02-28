from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional


class FlowLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = path.open("w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)
        self.writer.writerow(
            [
                "time",
                "train_id",
                "app_type",
                "latency_ms",
                "jitter_ms",
                "loss_flag",
                "throughput_mbps",
                "access_latency_ms",
                "transport_to_edge_ms",
                "compute_latency_ms",
                "transport_return_ms",
                "detour_latency_ms",
            ]
        )

    def log_packet(
        self,
        time_ms: float,
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
        detour_latency_ms: Optional[float],
    ) -> None:
        self.writer.writerow(
            [
                f"{time_ms:.3f}",
                train_id,
                app_type,
                "" if latency_ms is None else f"{latency_ms:.3f}",
                "" if jitter_ms is None else f"{jitter_ms:.3f}",
                loss_flag,
                f"{throughput_mbps:.6f}",
                "" if access_latency_ms is None else f"{access_latency_ms:.3f}",
                "" if transport_to_edge_ms is None else f"{transport_to_edge_ms:.3f}",
                "" if compute_latency_ms is None else f"{compute_latency_ms:.3f}",
                "" if transport_return_ms is None else f"{transport_return_ms:.3f}",
                "" if detour_latency_ms is None else f"{detour_latency_ms:.3f}",
            ]
        )

    def close(self) -> None:
        self.file.close()


class EventLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = path.open("w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)
        self.writer.writerow(["time", "event_type", "train_id", "node_id", "detour_type", "added_latency"])

    def log_event(
        self,
        time_ms: float,
        event_type: str,
        train_id: Optional[int],
        node_id: Optional[str],
        detour_type: Optional[str],
        added_latency_ms: Optional[float],
    ) -> None:
        self.writer.writerow(
            [
                f"{time_ms:.3f}",
                event_type,
                "" if train_id is None else train_id,
                "" if node_id is None else node_id,
                "" if detour_type is None else detour_type,
                "" if added_latency_ms is None else f"{added_latency_ms:.3f}",
            ]
        )

    def close(self) -> None:
        self.file.close()


def write_summary(path: Path, summary: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
