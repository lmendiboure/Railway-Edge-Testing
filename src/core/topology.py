from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from src.core.config import sat_edge_fraction
from src.core.state import ComputeNode, ShapingNode


@dataclass(frozen=True)
class Region:
    region_id: int
    bs_ids: List[str]
    beam_ids: List[str]
    gw_ids: List[str]


@dataclass
class Topology:
    regions: List[Region]
    bs_capacity_mbps: float
    beam_capacity_mbps: float
    bs_shaping: Dict[str, ShapingNode]
    beam_shaping: Dict[str, ShapingNode]
    compute_nodes: Dict[str, ComputeNode]
    gw_edge_available: Dict[str, bool]
    cloud_node_id: str
    regional_node_ids: Dict[int, str]
    onboard_node_ids: Dict[str, str]


def build_topology(
    manifest: Dict,
    rng: np.random.Generator,
    ter_mode: str,
    sat_mode: str,
) -> Topology:
    regions_count = manifest["topology"]["regions"]
    bs_per_region = manifest["topology"]["base_stations_per_region"]
    beams_per_region = manifest["topology"]["beams_per_region"]
    gws_per_region = manifest["topology"]["gateways_per_region"]

    regions: List[Region] = []
    bs_shaping: Dict[str, ShapingNode] = {}
    beam_shaping: Dict[str, ShapingNode] = {}
    compute_nodes: Dict[str, ComputeNode] = {}
    gw_edge_available: Dict[str, bool] = {}
    onboard_node_ids: Dict[str, str] = {}
    regional_node_ids: Dict[int, str] = {}

    compute_profiles = manifest["compute_profiles"]
    compute_kappa = manifest.get("compute_kappa", {})
    cloud_profile = compute_profiles["cloud"]
    cloud_kappa = compute_kappa.get("cloud", 1.0)
    cloud_node_id = "CLOUD"
    compute_nodes[cloud_node_id] = ComputeNode(
        node_id=cloud_node_id,
        mu_pkt_s=cloud_profile["mu_pkt_s"] / cloud_kappa,
        q_max=cloud_profile["q_max"],
        service_kappa=cloud_kappa,
    )

    if ter_mode == "TER_REGIONAL_EDGE":
        regional_kappa = compute_kappa.get("regional_edge", 1.0)
        for region_id in range(regions_count):
            node_id = f"REGION-{region_id}"
            regional_node_ids[region_id] = node_id
            profile = compute_profiles["regional_edge"]
            compute_nodes[node_id] = ComputeNode(
                node_id=node_id,
                mu_pkt_s=profile["mu_pkt_s"],
                q_max=profile["q_max"],
                service_kappa=regional_kappa,
            )
            compute_nodes[node_id].mu_pkt_s /= regional_kappa

    if ter_mode == "TER_BS_EDGE":
        bs_kappa = compute_kappa.get("bs_edge", 1.0)
        profile = compute_profiles["bs_edge"]
        for region_id in range(regions_count):
            for bs_index in range(bs_per_region):
                bs_id = f"R{region_id}-BS{bs_index}"
                node_id = f"EDGE-{bs_id}"
                compute_nodes[node_id] = ComputeNode(
                    node_id=node_id,
                    mu_pkt_s=profile["mu_pkt_s"],
                    q_max=profile["q_max"],
                    service_kappa=bs_kappa,
                )
                compute_nodes[node_id].mu_pkt_s /= bs_kappa

    sat_fraction = sat_edge_fraction(sat_mode)
    gateway_profile = compute_profiles["gateway"]
    onboard_profile = compute_profiles["onboard"]
    if sat_fraction is not None:
        gw_kappa = compute_kappa.get("gateway", 1.0)
        for region_id in range(regions_count):
            for gw_index in range(gws_per_region):
                gw_id = f"R{region_id}-GW{gw_index}"
                has_edge = rng.random() < sat_fraction
                gw_edge_available[gw_id] = has_edge
                if has_edge:
                    node_id = f"EDGE-{gw_id}"
                    compute_nodes[node_id] = ComputeNode(
                        node_id=node_id,
                        mu_pkt_s=gateway_profile["mu_pkt_s"],
                        q_max=gateway_profile["q_max"],
                        service_kappa=gw_kappa,
                    )
                    compute_nodes[node_id].mu_pkt_s /= gw_kappa
        if sat_fraction > 0 and not any(gw_edge_available.values()):
            fallback_gw = sorted(gw_edge_available.keys())[0]
            gw_edge_available[fallback_gw] = True
            node_id = f"EDGE-{fallback_gw}"
            compute_nodes[node_id] = ComputeNode(
                node_id=node_id,
                mu_pkt_s=gateway_profile["mu_pkt_s"],
                q_max=gateway_profile["q_max"],
                service_kappa=gw_kappa,
            )
            compute_nodes[node_id].mu_pkt_s /= gw_kappa

    if sat_mode == "SAT_ONBOARD":
        onboard_kappa = compute_kappa.get("onboard", 1.0)
        for region_id in range(regions_count):
            for beam_index in range(beams_per_region):
                beam_id = f"R{region_id}-BEAM{beam_index}"
                node_id = f"ONBOARD-{beam_id}"
                onboard_node_ids[beam_id] = node_id
                compute_nodes[node_id] = ComputeNode(
                    node_id=node_id,
                    mu_pkt_s=onboard_profile["mu_pkt_s"],
                    q_max=onboard_profile["q_max"],
                    service_kappa=onboard_kappa,
                )
                compute_nodes[node_id].mu_pkt_s /= onboard_kappa

    for region_id in range(regions_count):
        bs_ids = [f"R{region_id}-BS{idx}" for idx in range(bs_per_region)]
        beam_ids = [f"R{region_id}-BEAM{idx}" for idx in range(beams_per_region)]
        gw_ids = [f"R{region_id}-GW{idx}" for idx in range(gws_per_region)]
        regions.append(Region(region_id=region_id, bs_ids=bs_ids, beam_ids=beam_ids, gw_ids=gw_ids))
        for bs_id in bs_ids:
            bs_shaping[bs_id] = ShapingNode(node_id=bs_id)
        for beam_id in beam_ids:
            beam_shaping[beam_id] = ShapingNode(node_id=beam_id)

    return Topology(
        regions=regions,
        bs_capacity_mbps=manifest["network_profiles"]["5G"]["capacity_mbps"],
        beam_capacity_mbps=manifest["network_profiles"]["LEO"]["capacity_mbps"],
        bs_shaping=bs_shaping,
        beam_shaping=beam_shaping,
        compute_nodes=compute_nodes,
        gw_edge_available=gw_edge_available,
        cloud_node_id=cloud_node_id,
        regional_node_ids=regional_node_ids,
        onboard_node_ids=onboard_node_ids,
    )
