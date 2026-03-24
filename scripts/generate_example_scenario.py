from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main() -> None:
    output_path = Path("scenarios/edge/example_scenario.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(600):
        t = start + timedelta(seconds=i)
        lat = 44.840000 + 0.000010 * i
        lon = -0.580000 + 0.000015 * i
        speed = 17.0 + 2.0 * math.sin(i / 40.0) + 0.5 * math.sin(i / 9.0)

        avail_5g = not (120 <= i < 180 or 420 <= i < 450)
        avail_sat = True

        if avail_5g:
            e2e_5g = 38.0 + 7.0 * abs(math.sin(i / 18.0)) + 2.0 * math.sin(i / 11.0)
            ul_5g = 6.0 + 1.8 * abs(math.sin(i / 25.0))
            dl_5g = 28.0 + 6.0 * abs(math.sin(i / 30.0))
            bler_5g = 0.005 + 0.008 * abs(math.sin(i / 22.0))
            jitter_5g = 3.0 + 2.0 * abs(math.sin(i / 15.0))
            loss_5g = 0.0005 + 0.001 * abs(math.sin(i / 20.0))
        else:
            e2e_5g = ul_5g = dl_5g = bler_5g = jitter_5g = loss_5g = ""

        if avail_sat:
            e2e_sat = 92.0 + 18.0 * abs(math.sin(i / 20.0)) + 4.0 * math.sin(i / 9.0)
            ul_sat = 3.0 + 0.8 * abs(math.sin(i / 18.0))
            dl_sat = 12.0 + 3.0 * abs(math.sin(i / 16.0))
            bler_sat = 0.01 + 0.02 * abs(math.sin(i / 27.0))
            jitter_sat = 12.0 + 8.0 * abs(math.sin(i / 21.0))
            loss_sat = 0.002 + 0.004 * abs(math.sin(i / 19.0))
        else:
            e2e_sat = ul_sat = dl_sat = bler_sat = jitter_sat = loss_sat = ""

        rows.append(
            {
                "time": t.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "gps_lat": f"{lat:.6f}",
                "gps_lon": f"{lon:.6f}",
                "speed_mps": f"{speed:.3f}",
                "e2e_latency_5g_ms": f"{e2e_5g:.3f}" if avail_5g else "",
                "ul_mbps_5g": f"{ul_5g:.3f}" if avail_5g else "",
                "dl_mbps_5g": f"{dl_5g:.3f}" if avail_5g else "",
                "bler_5g": f"{bler_5g:.4f}" if avail_5g else "",
                "jitter_5g_ms": f"{jitter_5g:.3f}" if avail_5g else "",
                "loss_5g": f"{loss_5g:.4f}" if avail_5g else "",
                "e2e_latency_sat_ms": f"{e2e_sat:.3f}" if avail_sat else "",
                "ul_mbps_sat": f"{ul_sat:.3f}" if avail_sat else "",
                "dl_mbps_sat": f"{dl_sat:.3f}" if avail_sat else "",
                "bler_sat": f"{bler_sat:.4f}" if avail_sat else "",
                "jitter_sat_ms": f"{jitter_sat:.3f}" if avail_sat else "",
                "loss_sat": f"{loss_sat:.4f}" if avail_sat else "",
            }
        )

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "time",
                "gps_lat",
                "gps_lon",
                "speed_mps",
                "e2e_latency_5g_ms",
                "ul_mbps_5g",
                "dl_mbps_5g",
                "bler_5g",
                "jitter_5g_ms",
                "loss_5g",
                "e2e_latency_sat_ms",
                "ul_mbps_sat",
                "dl_mbps_sat",
                "bler_sat",
                "jitter_sat_ms",
                "loss_sat",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
