from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from src.core.state import FlowState, Packet, TrainState


def _video_interval_ms(packet_bytes: int, bitrate_mbps: float) -> float:
    bits = packet_bytes * 8
    seconds = bits / (bitrate_mbps * 1_000_000.0)
    return seconds * 1000.0


def init_flow_states(manifest: Dict, rng: np.random.Generator) -> Dict[str, FlowState]:
    traffic = manifest["traffic"]
    flows: Dict[str, FlowState] = {}

    etcs_interval = traffic["ETCS2"]["interval_ms"]
    flows["ETCS2"] = FlowState(
        app_type="ETCS2",
        packet_size_bytes=traffic["ETCS2"]["packet_bytes"],
        interval_ms=etcs_interval,
        next_time_ms=float(rng.uniform(0, etcs_interval)),
    )

    voice_interval = traffic["Voice"]["interval_ms"]
    flows["Voice"] = FlowState(
        app_type="Voice",
        packet_size_bytes=traffic["Voice"]["packet_bytes"],
        interval_ms=voice_interval,
        next_time_ms=float(rng.uniform(0, voice_interval)),
    )

    video_profile = traffic["video_profile"]
    bitrate = traffic["Video"]["bitrate_mbps"][video_profile]
    video_interval = _video_interval_ms(traffic["Video"]["packet_bytes"], bitrate)
    flows["Video"] = FlowState(
        app_type="Video",
        packet_size_bytes=traffic["Video"]["packet_bytes"],
        interval_ms=video_interval,
        next_time_ms=float(rng.uniform(0, video_interval)),
    )

    return flows


def generate_packets(
    train: TrainState,
    time_ms: float,
    packet_id_start: int,
) -> Tuple[List[Packet], int]:
    packets: List[Packet] = []
    next_packet_id = packet_id_start
    for flow in train.flows.values():
        while time_ms + 1e-9 >= flow.next_time_ms:
            packets.append(
                Packet(
                    packet_id=next_packet_id,
                    train_id=train.train_id,
                    app_type=flow.app_type,
                    size_bytes=flow.packet_size_bytes,
                    gen_time_ms=time_ms,
                    access=train.access or "NONE",
                )
            )
            next_packet_id += 1
            flow.next_time_ms += flow.interval_ms
    return packets, next_packet_id
