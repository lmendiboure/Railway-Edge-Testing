from __future__ import annotations

from dataclasses import dataclass
import csv
import math
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.core.config import RunConfig, derive_steps
from src.core.connectivity import resolve_connectivity_state, tick_spikes, update_state_spike
from src.core.corridor import advance_train, generate_corridor
from src.core.logging import EventLogger, FlowLogger, write_summary
from src.core.latency import (
    access_spike_parameters,
    expected_access_rtt_ms,
    mean_access_latency_ms,
    sample_access_latency_ms,
    spike_duration_steps,
    transport_to_edge_latency_ms,
)
from src.core.metrics import MetricsCollector
from src.core.rng import create_rng
from src.core.state import Packet, TrainState
from src.core.traffic import generate_packets, init_flow_states
from src.core.topology import Topology, build_topology


@dataclass
class PacketRecord:
    time_ms: float
    train_id: int
    app_type: str
    latency_ms: Optional[float]
    jitter_ms: Optional[float]
    loss_flag: int
    throughput_mbps: float
    access_latency_ms: Optional[float]
    transport_to_edge_ms: Optional[float]
    compute_latency_ms: Optional[float]
    transport_return_ms: Optional[float]
    detour_latency_ms: float
    detour_queue_ms: float
    size_bytes: int


@dataclass
class DetourLinkState:
    capacity_mbps: float
    backlog_bytes: float = 0.0

    def tick(self, dt_s: float) -> None:
        capacity_bytes = self.capacity_mbps * 1_000_000.0 / 8.0 * dt_s
        self.backlog_bytes = max(0.0, self.backlog_bytes - capacity_bytes)

    def enqueue(self, packet_bytes: int) -> float:
        capacity_bytes_per_ms = self.capacity_mbps * 1_000_000.0 / 8.0 / 1000.0
        if capacity_bytes_per_ms <= 0:
            return 0.0
        queue_delay_ms = self.backlog_bytes / capacity_bytes_per_ms
        self.backlog_bytes += packet_bytes
        return queue_delay_ms


def _spike_dampening(access_type: str, run_config: RunConfig, access_load: Dict) -> float:
    dampening = 1.0
    config = access_load.get("spike_amp_dampening", {})
    if access_type == "5G":
        mapping = config.get("5G", {})
        dampening = float(mapping.get(run_config.ter_mode, 1.0))
    elif access_type == "LEO":
        mapping = config.get("LEO", {})
        sat_mode = run_config.sat_mode
        if sat_mode.startswith("SAT_GW_EDGE"):
            sat_mode = "SAT_GW_EDGE"
        dampening = float(mapping.get(sat_mode, 1.0))
    if dampening <= 0:
        return 1.0
    return dampening


def _offload_factor(access_type: str, run_config: RunConfig, access_load: Dict) -> float:
    config = access_load.get("offload_factor", {})
    if access_type == "5G":
        mapping = config.get("5G", {})
        return float(mapping.get(run_config.ter_mode, 0.0))
    if access_type == "LEO":
        mapping = config.get("LEO", {})
        sat_mode = run_config.sat_mode
        if sat_mode.startswith("SAT_GW_EDGE"):
            sat_mode = "SAT_GW_EDGE"
        return float(mapping.get(sat_mode, 0.0))
    return 0.0


def _write_detours_by_flow(
    output_dir: Path, flow_total: Dict[tuple[int, str], int], flow_detour: Dict[tuple[int, str], int]
) -> None:
    path = output_dir / "detours_by_flow.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["train_id", "app_type", "detour_count", "detour_ratio"])
        for (train_id, app_type), total in sorted(flow_total.items()):
            detour_count = flow_detour.get((train_id, app_type), 0)
            ratio = detour_count / total if total else 0.0
            writer.writerow([train_id, app_type, detour_count, f"{ratio:.6f}"])


def _sample_rtt(profile: Dict[str, float], rng: np.random.Generator) -> float:
    u = float(rng.random())
    p50 = profile["rtt_p50_ms"]
    p95 = profile["rtt_p95_ms"]
    p99 = profile.get("rtt_p99_ms")
    rtt_max = profile.get("rtt_max_ms", p99 if p99 is not None else p95)

    if p99 is None:
        if u <= 0.5:
            return (u / 0.5) * p50
        if u <= 0.95:
            return p50 + (u - 0.5) / 0.45 * (p95 - p50)
        return p95 + (u - 0.95) / 0.05 * (rtt_max - p95)

    if u <= 0.5:
        return (u / 0.5) * p50
    if u <= 0.95:
        return p50 + (u - 0.5) / 0.45 * (p95 - p50)
    if u <= 0.99:
        return p95 + (u - 0.95) / 0.04 * (p99 - p95)
    return p99 + (u - 0.99) / 0.01 * (rtt_max - p99)


def _sample_compute_service_ms(
    node, manifest: Dict, rng: np.random.Generator
) -> float:
    cfg = manifest.get("compute_variability", {})
    median_ms = float(cfg.get("service_median_ms", 3.5))
    sigma = float(cfg.get("service_sigma", 0.3))
    min_ms = float(cfg.get("service_min_ms", 1.0))
    max_ms = float(cfg.get("service_max_ms", 10.0))
    if median_ms <= 0:
        median_ms = 3.5
    if sigma <= 0:
        sigma = 0.3
    scaled_median = median_ms * (node.service_kappa if node.service_kappa > 0 else 1.0)
    mu = math.log(max(1e-6, scaled_median))
    service_ms = float(rng.lognormal(mean=mu, sigma=sigma))
    if service_ms < min_ms:
        service_ms = min_ms
    if service_ms > max_ms:
        service_ms = max_ms
    return service_ms


def _select_access(
    train: TrainState, manifest: Dict, run_config: RunConfig, topology: Topology
) -> Optional[str]:
    state = train.connectivity_state
    if state == "NONE":
        return None
    if state == "5G_ONLY":
        return "5G"
    if state == "LEO_ONLY":
        return "LEO"
    segment_type = train.corridor[train.segment_index].segment_type
    access_load = manifest.get("access_load", {})
    bs_util = topology.bs_shaping[train.bs_id].last_utilization
    beam_util = topology.beam_shaping[train.beam_id].last_utilization
    bs_offload = _offload_factor("5G", run_config, access_load)
    beam_offload = _offload_factor("LEO", run_config, access_load)
    bs_util_eff = bs_util * (1.0 - bs_offload)
    beam_util_eff = beam_util * (1.0 - beam_offload)
    access_5g = expected_access_rtt_ms("5G", segment_type, bs_util_eff, access_load)
    access_leo = expected_access_rtt_ms("LEO", segment_type, beam_util_eff, access_load)
    if access_5g is None:
        return "LEO"
    if access_leo is None:
        return "5G"
    transport_5g = transport_to_edge_latency_ms("5G", segment_type, run_config.ter_mode, run_config.sat_mode)
    transport_leo = transport_to_edge_latency_ms("LEO", segment_type, run_config.ter_mode, run_config.sat_mode)
    rtt_5g = access_5g + 2.0 * transport_5g
    rtt_leo = access_leo + 2.0 * transport_leo
    if rtt_5g <= rtt_leo:
        return "5G"
    return "LEO"


def _assign_compute_node(
    train: TrainState,
    packet: Packet,
    topology: Topology,
    run_config: RunConfig,
    manifest: Dict,
    rng: np.random.Generator,
    event_logger: EventLogger,
    time_ms: float,
    detour_links: Dict[str, "DetourLinkState"],
) -> Tuple[str, float]:
    detour_latency = 0.0
    if packet.access == "5G":
        if run_config.ter_mode == "TER_BS_EDGE":
            return f"EDGE-{train.bs_id}", detour_latency
        if run_config.ter_mode == "TER_REGIONAL_EDGE":
            return topology.regional_node_ids[train.region_id], detour_latency
        return topology.cloud_node_id, detour_latency

    if packet.access == "LEO":
        if run_config.sat_mode == "SAT_ONBOARD":
            node_id = topology.onboard_node_ids.get(train.beam_id)
            if node_id is not None:
                return node_id, detour_latency
            candidates = list(topology.onboard_node_ids.values())
            if candidates:
                if manifest["detour_policy"] == "RANDOM_EDGE":
                    target_node = str(rng.choice(candidates))
                else:
                    target_node = sorted(candidates)[0]
                queue_delay = detour_links["SAT_TO_SAT"].enqueue(packet.size_bytes)
                detour_latency = 5.0 + queue_delay
                packet.detour_queue_ms = queue_delay
                event_logger.log_event(time_ms, "detour", train.train_id, target_node, "SAT_TO_SAT", detour_latency)
                return target_node, detour_latency
        if run_config.sat_mode.startswith("SAT_GW_EDGE"):
            gw_id = train.gw_id
            if topology.gw_edge_available.get(gw_id, False):
                return f"EDGE-{gw_id}", detour_latency
            candidates = [gw for gw, has_edge in topology.gw_edge_available.items() if has_edge]
            if candidates:
                if manifest["detour_policy"] == "RANDOM_EDGE":
                    target_gw = str(rng.choice(candidates))
                else:
                    target_gw = sorted(candidates)[0]
                queue_delay = detour_links["GW_TO_GW"].enqueue(packet.size_bytes)
                detour_latency = 20.0 + queue_delay
                packet.detour_queue_ms = queue_delay
                event_logger.log_event(time_ms, "detour", train.train_id, target_gw, "GW_TO_GW", detour_latency)
                return f"EDGE-{target_gw}", detour_latency
        return topology.cloud_node_id, detour_latency

    return topology.cloud_node_id, detour_latency


def _process_beam_switches(
    trains: List[TrainState],
    topology: Topology,
    manifest: Dict,
    rng: np.random.Generator,
    event_logger: EventLogger,
    time_ms: float,
    dt_s: float,
) -> None:
    rate_per_min = manifest["beam_switch"]["rate_per_min"]
    spike_low, spike_high = manifest["beam_switch"]["spike_ms"]
    duration_ms = manifest["beam_switch"]["duration_ms"]
    corr_prob = manifest["beam_switch"]["correlation_probability"]
    event_prob = (rate_per_min / 60.0) * dt_s

    trains_by_beam: Dict[str, List[TrainState]] = {}
    for train in trains:
        trains_by_beam.setdefault(train.beam_id, []).append(train)

    for region in topology.regions:
        for beam_id in region.beam_ids:
            if rng.random() >= event_prob:
                continue
            spike_ms = float(rng.uniform(spike_low, spike_high))
            affected_trains = trains_by_beam.get(beam_id, [])
            if not affected_trains:
                continue
            if rng.random() >= corr_prob:
                index = int(rng.integers(0, len(affected_trains)))
                affected_trains = [affected_trains[index]]
            for train in affected_trains:
                train.beam_spike_ms = spike_ms
                train.beam_spike_remaining_ms = duration_ms
                event_logger.log_event(time_ms, "beam_switch", train.train_id, beam_id, None, spike_ms)


def _init_trains(
    run_config: RunConfig,
    manifest: Dict,
    rng: np.random.Generator,
    topology: Topology,
    total_distance_m: float,
) -> List[TrainState]:
    trains: List[TrainState] = []
    speed_m_s = manifest["simulation"]["speed_m_s"]
    corridor_config = manifest["corridor"]
    segment_lengths = corridor_config["segment_lengths_km"]
    weights = corridor_config["segment_type_weights"]
    mapping = manifest["connectivity"]["mapping"]
    tunnel_mode = corridor_config["tunnel_mode"]

    for train_id in range(run_config.train_count):
        region_id = train_id % len(topology.regions)
        region = topology.regions[region_id]
        bs_id = region.bs_ids[train_id % len(region.bs_ids)]
        beam_id = region.beam_ids[train_id % len(region.beam_ids)]
        gw_id = region.gw_ids[train_id % len(region.gw_ids)]
        corridor = generate_corridor(rng, total_distance_m, segment_lengths, weights)
        first_segment = corridor[0].segment_type
        connectivity_state = resolve_connectivity_state(
            first_segment, tunnel_mode, run_config.connectivity_override, mapping
        )
        flows = init_flow_states(manifest, rng)
        trains.append(
            TrainState(
                train_id=train_id,
                region_id=region_id,
                position_m=0.0,
                speed_m_s=speed_m_s,
                corridor=corridor,
                segment_index=0,
                segment_offset_m=0.0,
                connectivity_state=connectivity_state,
                access=None,
                bs_id=bs_id,
                beam_id=beam_id,
                gw_id=gw_id,
                flows=flows,
            )
        )
    return trains


def run_simulation(run_config: RunConfig, manifest: Dict, output_dir: Path) -> None:
    rng = create_rng(run_config.seed)
    if "kpi_windows" not in manifest:
        manifest["kpi_windows"] = {"throughput_ms": 1000}
    video_mode = manifest.get("traffic", {}).get("video_mode")
    video_modes = manifest.get("traffic", {}).get("video_modes", {})
    if video_mode in video_modes:
        min_rate = video_modes[video_mode].get("min_rate_mbps")
        if min_rate is not None:
            manifest["kpi_thresholds"]["Video"]["throughput_mbps"] = min_rate
        if video_mode == "RAW_LQ":
            manifest["traffic"]["video_profile"] = "LQ"
        if video_mode == "RAW_HQ":
            manifest["traffic"]["video_profile"] = "HQ"
    dt_ms = manifest["simulation"]["dt_ms"]
    dt_s = dt_ms / 1000.0
    steps = derive_steps(manifest)
    total_time_s = steps * dt_s
    total_distance_m = manifest["simulation"]["speed_m_s"] * total_time_s

    topology = build_topology(manifest, rng, run_config.ter_mode, run_config.sat_mode)
    trains = _init_trains(run_config, manifest, rng, topology, total_distance_m)
    trains_by_id = {train.train_id: train for train in trains}

    detour_cfg = manifest.get("detour_links", {})
    detour_links = {
        "GW_TO_GW": DetourLinkState(detour_cfg.get("gw_gw_capacity_mbps", 200.0)),
        "SAT_TO_SAT": DetourLinkState(detour_cfg.get("sat_sat_capacity_mbps", 50.0)),
    }

    flow_logger = FlowLogger(output_dir / "flows.csv")
    event_logger = EventLogger(output_dir / "events.csv")
    metrics = MetricsCollector(manifest["kpi_thresholds"])

    compute_enabled = set(manifest.get("compute_policy", {}).get("enabled_apps", []))

    packet_id = 0
    rtt_tracker = {"max_rtt_extra": 0.0}
    for step in range(steps):
        time_ms = step * dt_ms

        for link in detour_links.values():
            link.tick(dt_s)

        for train in trains:
            advance_train(train, dt_s)

        for train in trains:
            tick_spikes(train, dt_ms)
            segment_type = train.corridor[train.segment_index].segment_type
            new_state = resolve_connectivity_state(
                segment_type,
                manifest["corridor"]["tunnel_mode"],
                run_config.connectivity_override,
                manifest["connectivity"]["mapping"],
            )
            state_changed = new_state != train.connectivity_state
            if state_changed:
                train.connectivity_state = new_state
            update_state_spike(rng, train, state_changed, manifest["connectivity"])
            if state_changed:
                event_logger.log_event(time_ms, "connectivity_change", train.train_id, None, None, train.state_spike_ms)

        _process_beam_switches(trains, topology, manifest, rng, event_logger, time_ms, dt_s)

        for train in trains:
            train.access = _select_access(train, manifest, run_config, topology)

        generated_packets: List[Packet] = []
        for train in trains:
            packets, packet_id = generate_packets(train, time_ms, packet_id)
            generated_packets.extend(packets)

        step_records: List[PacketRecord] = []
        processed_packets: List[Packet] = []

        for packet in generated_packets:
            train = trains_by_id[packet.train_id]
            if packet.access == "NONE" or packet.access is None:
                step_records.append(
                    PacketRecord(
                        time_ms=time_ms,
                        train_id=packet.train_id,
                        app_type=packet.app_type,
                        latency_ms=None,
                        jitter_ms=None,
                        loss_flag=1,
                        throughput_mbps=0.0,
                        access_latency_ms=None,
                        transport_to_edge_ms=None,
                        compute_latency_ms=None,
                        transport_return_ms=None,
                        detour_latency_ms=0.0,
                        detour_queue_ms=0.0,
                        size_bytes=packet.size_bytes,
                    )
                )
                continue

            if packet.app_type not in compute_enabled:
                packet.compute_latency_ms = 0.0
                packet.shaping_arrival_ms = time_ms
                processed_packets.append(packet)
                continue

            node_id, detour_latency = _assign_compute_node(
                train, packet, topology, run_config, manifest, rng, event_logger, time_ms, detour_links
            )
            packet.detour_latency_ms = detour_latency
            compute_node = topology.compute_nodes[node_id]
            if len(compute_node.queue) >= compute_node.q_max:
                compute_node.dropped_packets += 1
                event_logger.log_event(time_ms, "compute_overflow", packet.train_id, node_id, None, None)
                step_records.append(
                    PacketRecord(
                        time_ms=time_ms,
                        train_id=packet.train_id,
                        app_type=packet.app_type,
                        latency_ms=None,
                        jitter_ms=None,
                        loss_flag=1,
                        throughput_mbps=0.0,
                        access_latency_ms=None,
                        transport_to_edge_ms=None,
                        compute_latency_ms=None,
                        transport_return_ms=None,
                        detour_latency_ms=packet.detour_latency_ms,
                        detour_queue_ms=packet.detour_queue_ms,
                        size_bytes=packet.size_bytes,
                    )
                )
                continue
            packet.compute_enqueue_time_ms = time_ms
            compute_node.queue.append(packet)

        for node in topology.compute_nodes.values():
            node.record_occupancy()
            capacity = int(node.mu_pkt_s * dt_s)
            for _ in range(capacity):
                if not node.queue:
                    break
                packet = node.queue.popleft()
                queue_delay = time_ms - packet.compute_enqueue_time_ms
                service_ms = _sample_compute_service_ms(node, manifest, rng)
                packet.compute_latency_ms = queue_delay + service_ms
                node.service_time_sum_ms += service_ms
                processed_packets.append(packet)
                node.processed_packets += 1

        for packet in processed_packets:
            train = trains_by_id[packet.train_id]
            if packet.access == "5G":
                shaping_node = topology.bs_shaping[train.bs_id]
            else:
                shaping_node = topology.beam_shaping[train.beam_id]
            shaping_node.ensure_app(packet.app_type)
            if packet.shaping_arrival_ms == 0.0:
                packet.shaping_arrival_ms = time_ms
            shaping_node.queues[packet.app_type].append(packet)

        for shaping_node in list(topology.bs_shaping.values()) + list(topology.beam_shaping.values()):
            shaping_node.record_occupancy()

        transmitted_records: List[PacketRecord] = []

        for bs_id, shaping_node in topology.bs_shaping.items():
            _process_transmission_node(
                shaping_node,
                topology.bs_capacity_mbps,
                "5G",
                manifest,
                rng,
                time_ms,
                dt_s,
                run_config,
                metrics,
                trains_by_id,
                transmitted_records,
                step_records,
                rtt_tracker,
            )

        for beam_id, shaping_node in topology.beam_shaping.items():
            _process_transmission_node(
                shaping_node,
                topology.beam_capacity_mbps,
                "LEO",
                manifest,
                rng,
                time_ms,
                dt_s,
                run_config,
                metrics,
                trains_by_id,
                transmitted_records,
                step_records,
                rtt_tracker,
            )

        step_records.extend(transmitted_records)

        for record in step_records:
            flow_logger.log_packet(
                record.time_ms,
                record.train_id,
                record.app_type,
                record.latency_ms,
                record.jitter_ms,
                record.loss_flag,
                record.throughput_mbps,
                record.access_latency_ms,
                record.transport_to_edge_ms,
                record.compute_latency_ms,
                record.transport_return_ms,
                record.detour_latency_ms,
            )
            metrics.record_packet(
                train_id=record.train_id,
                app_type=record.app_type,
                latency_ms=record.latency_ms,
                jitter_ms=record.jitter_ms,
                loss_flag=record.loss_flag,
                throughput_mbps=record.throughput_mbps,
                access_latency_ms=record.access_latency_ms,
                transport_to_edge_ms=record.transport_to_edge_ms,
                compute_latency_ms=record.compute_latency_ms,
                transport_return_ms=record.transport_return_ms,
                detour_latency_ms=record.detour_latency_ms,
                detour_queue_ms=record.detour_queue_ms,
                size_bytes=record.size_bytes,
            )

    flow_logger.close()
    event_logger.close()

    compliance = metrics.compliance_per_train()
    compliance_global = float(sum(compliance.values()) / len(compliance)) if compliance else 0.0
    compliance_worst = float(min(compliance.values())) if compliance else 0.0

    p95_voice = metrics.p95_voice.value() or 0.0
    p95_video = metrics.p95_video.value() or 0.0
    p50_e2e = metrics.p50_e2e.value() or 0.0
    p99_e2e = metrics.p99_e2e_latency()
    p999_e2e = metrics.p999_e2e_latency()

    compute_utilizations = []
    total_compute_time_s = 0.0
    avg_compute_occupancy = 0.0
    max_compute_queue_len = 0
    for node in topology.compute_nodes.values():
        util = node.processed_packets / (node.mu_pkt_s * total_time_s) if total_time_s else 0.0
        compute_utilizations.append(util)
        total_compute_time_s += node.service_time_sum_ms / 1000.0
        if node.queue_len_steps:
            avg_compute_occupancy += node.queue_len_sum / node.queue_len_steps
        if node.max_queue_len > max_compute_queue_len:
            max_compute_queue_len = node.max_queue_len
    mean_compute_util = float(sum(compute_utilizations) / len(compute_utilizations)) if compute_utilizations else 0.0
    if topology.compute_nodes:
        avg_compute_occupancy /= len(topology.compute_nodes)

    avg_shaping_occupancy = 0.0
    shaping_nodes = list(topology.bs_shaping.values()) + list(topology.beam_shaping.values())
    for node in shaping_nodes:
        if node.queue_len_steps:
            avg_shaping_occupancy += node.queue_len_sum / node.queue_len_steps
    if shaping_nodes:
        avg_shaping_occupancy /= len(shaping_nodes)

    summary = {
        "config_id": run_config.canonical_id,
        "seed": run_config.seed,
        "version_string": run_config.version_string,
        "config_hash": run_config.config_hash,
        "compliance_global": compliance_global,
        "compliance_worst_train": compliance_worst,
        "p95_latency_voice": p95_voice,
        "p95_latency_video": p95_video,
        "p95_e2e_latency": metrics.p95_e2e.value() or 0.0,
        "p50_e2e_latency": p50_e2e,
        "p99_e2e_latency": p99_e2e,
        "p999_e2e_latency": p999_e2e,
        "p95_compute_latency": metrics.p95_compute_latency(),
        "mean_compute_utilization": mean_compute_util,
        "cpu_utilization_ratio": mean_compute_util,
        "active_edge_nodes": len([node_id for node_id in topology.compute_nodes if node_id != topology.cloud_node_id]),
        "total_compute_time_s": total_compute_time_s,
        "avg_compute_queue_occupancy": avg_compute_occupancy,
        "avg_shaping_queue_occupancy": avg_shaping_occupancy,
        "detour_volume_mb": metrics.detour_volume_bytes / (1024 * 1024),
        "mean_access_latency": metrics.mean_access_latency(),
        "mean_transport_to_edge": metrics.mean_transport_to_edge(),
        "mean_compute_latency": metrics.mean_compute_latency(),
        "mean_transport_return": metrics.mean_transport_return(),
        "mean_detour_latency": metrics.mean_detour_latency(),
        "p_spike_mean": metrics.p_spike_mean(),
        "spike_count": metrics.access_spike_count,
        "access_queue_p95": metrics.access_queue_p95_value(),
        "p95_access_latency": metrics.p95_access_latency(),
        "p99_access_latency": metrics.p99_access_latency(),
        "p999_access_latency": metrics.p999_access_latency(),
        "detour_time_fraction": metrics.detour_time_fraction(),
        "detour_packet_ratio": metrics.detour_packet_ratio(),
        "detour_added_latency_p95": metrics.detour_p95(),
        "detour_added_latency_p99": metrics.detour_p99(),
        "detour_link_queue_p95": metrics.detour_queue_p95_value(),
        "max_rtt_extra_ms": rtt_tracker["max_rtt_extra"],
        "max_compute_queue_len": max_compute_queue_len,
    }

    _write_detours_by_flow(output_dir, metrics.flow_total, metrics.flow_detour)

    write_summary(output_dir / "summary.json", summary)


def _process_transmission_node(
    shaping_node,
    capacity_mbps: float,
    access_type: str,
    manifest: Dict,
    rng: np.random.Generator,
    time_ms: float,
    dt_s: float,
    run_config: RunConfig,
    metrics: MetricsCollector,
    trains_by_id: Dict[int, TrainState],
    transmitted_records: List[PacketRecord],
    dropped_records: List[PacketRecord],
    rtt_tracker: Dict[str, float],
) -> None:
    priority = ["ETCS2", "Voice", "Video"]
    for app in priority:
        shaping_node.ensure_app(app)

    offered_by_app = {
        app: sum(packet.size_bytes for packet in shaping_node.queues[app]) for app in priority
    }
    offered_bytes = sum(offered_by_app.values())
    if offered_bytes == 0:
        return

    capacity_bytes = capacity_mbps * 1_000_000.0 / 8.0 * dt_s
    utilization = offered_bytes / capacity_bytes if capacity_bytes > 0 else 0.0
    shaping_node.last_utilization = utilization
    overload_ratio = max(0.0, (offered_bytes - capacity_bytes) / offered_bytes)
    rtt_extra = 0.0 if offered_bytes <= capacity_bytes else 10.0 + 40.0 * overload_ratio
    if rtt_extra > rtt_tracker["max_rtt_extra"]:
        rtt_tracker["max_rtt_extra"] = rtt_extra

    policy = manifest["allocation_policy"]["mode"]
    weights = manifest["allocation_policy"]["weights"]
    active_apps = [app for app in priority if offered_by_app[app] > 0]
    allocated = {app: 0.0 for app in priority}
    if active_apps:
        if policy == "WEIGHTED":
            weight_sum = sum(weights[app] for app in active_apps)
            for app in active_apps:
                allocated[app] = (weights[app] / weight_sum) * capacity_bytes
        else:
            share = capacity_bytes / len(active_apps)
            for app in active_apps:
                allocated[app] = share

    for app in active_apps:
        allocated[app] = min(allocated[app], offered_by_app[app])

    capacity_left = capacity_bytes - sum(allocated.values())
    if capacity_left > 0:
        for app in priority:
            remaining = offered_by_app[app] - allocated[app]
            if remaining <= 0:
                continue
            extra = min(remaining, capacity_left)
            allocated[app] += extra
            capacity_left -= extra
            if capacity_left <= 0:
                break

    for app in priority:
        queue = shaping_node.queues[app]
        kept = deque()
        offered_app = offered_by_app[app]
        alloc_app = allocated[app]
        drop_prob = 0.0
        if offered_app > 0 and alloc_app < offered_app:
            drop_prob = (offered_app - alloc_app) / offered_app
        while queue:
            packet = queue.popleft()
            if drop_prob > 0 and rng.random() < drop_prob:
                dropped_records.append(
                    PacketRecord(
                        time_ms=time_ms,
                        train_id=packet.train_id,
                        app_type=packet.app_type,
                        latency_ms=None,
                        jitter_ms=None,
                        loss_flag=1,
                        throughput_mbps=0.0,
                        access_latency_ms=None,
                        transport_to_edge_ms=None,
                        compute_latency_ms=None,
                        transport_return_ms=None,
                        detour_latency_ms=packet.detour_latency_ms,
                        detour_queue_ms=packet.detour_queue_ms,
                        size_bytes=packet.size_bytes,
                    )
                )
                continue
            kept.append(packet)
        shaping_node.queues[app] = kept

    capacity_left = capacity_bytes
    access_load = manifest.get("access_load", {})
    offload_factor = _offload_factor(access_type, run_config, access_load)
    utilization_eff = utilization * (1.0 - offload_factor)
    p_spike, spike_min, spike_max = access_spike_parameters(access_type, utilization_eff, access_load)
    dampening = _spike_dampening(access_type, run_config, access_load)
    if shaping_node.spike_remaining_steps > 0:
        spike_flag = True
        spike_amp = shaping_node.spike_amp_ms
        shaping_node.spike_remaining_steps -= 1
    else:
        spike_flag = rng.random() < p_spike
        spike_amp = float(rng.uniform(spike_min, spike_max)) * (1.0 + max(0.0, utilization_eff)) * dampening
        if spike_flag:
            shaping_node.spike_remaining_steps = spike_duration_steps(
                access_type, utilization_eff, access_load, rng
            ) - 1
            shaping_node.spike_amp_ms = spike_amp
    metrics.record_spike_event(p_spike, spike_flag)
    for app in priority:
        queue = shaping_node.queues[app]
        transmitted = []
        while queue and capacity_left >= queue[0].size_bytes:
            packet = queue.popleft()
            capacity_left -= packet.size_bytes
            transmitted.append(packet)
        for packet in transmitted:
            train = trains_by_id[packet.train_id]
            segment_type = train.corridor[train.segment_index].segment_type
            access_one_way, radio_q, spike_load, spike_prob, spike_flag = sample_access_latency_ms(
                access_type,
                segment_type,
                rng,
                utilization_eff,
                access_load,
                spike_flag=spike_flag,
                spike_amp=spike_amp,
            )
            if access_one_way is None:
                access_one_way = 0.0
            access_rtt = 2.0 * access_one_way + train.state_spike_ms + train.beam_spike_ms + rtt_extra
            access_queue_rtt = 2.0 * radio_q
            metrics.record_access_sample(access_rtt, access_queue_rtt)

            transport_base = transport_to_edge_latency_ms(
                access_type, segment_type, run_config.ter_mode, run_config.sat_mode
            )
            transport_total = transport_base + packet.detour_latency_ms
            queue_wait = time_ms - packet.shaping_arrival_ms
            transport_to_edge = transport_total + queue_wait
            transport_return = transport_total
            latency_ms = access_rtt + transport_to_edge + packet.compute_latency_ms + transport_return

            flow = train.flows[packet.app_type]
            if flow.last_latency_ms is None:
                jitter_ms = 0.0
            else:
                jitter_ms = abs(latency_ms - flow.last_latency_ms)
            flow.last_latency_ms = latency_ms

            window_ms = float(manifest.get("kpi_windows", {}).get("throughput_ms", 1000))
            flow.delivered_bytes_window.append((time_ms, packet.size_bytes))
            while flow.delivered_bytes_window and time_ms - flow.delivered_bytes_window[0][0] > window_ms:
                flow.delivered_bytes_window.popleft()
            bytes_window = sum(size for _, size in flow.delivered_bytes_window)
            throughput_mbps = (bytes_window * 8.0) / (window_ms / 1000.0) / 1_000_000.0

            transmitted_records.append(
                PacketRecord(
                    time_ms=time_ms,
                    train_id=packet.train_id,
                    app_type=packet.app_type,
                    latency_ms=latency_ms,
                    jitter_ms=jitter_ms,
                    loss_flag=0,
                    throughput_mbps=throughput_mbps,
                    access_latency_ms=access_rtt,
                    transport_to_edge_ms=transport_to_edge,
                    compute_latency_ms=packet.compute_latency_ms,
                    transport_return_ms=transport_return,
                    detour_latency_ms=packet.detour_latency_ms,
                    detour_queue_ms=packet.detour_queue_ms,
                    size_bytes=packet.size_bytes,
                )
            )
        if queue and capacity_left < queue[0].size_bytes:
            break
