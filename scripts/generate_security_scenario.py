from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main() -> None:
    output_path = Path("scenarios/security/dos_attack_demo.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(120):
        t = start + timedelta(seconds=i)
        if 20 <= i < 60:
            attack_active = True
            intensity = 0.7
            mitigation = False
        elif 60 <= i < 80:
            attack_active = True
            intensity = 0.4
            mitigation = True
        else:
            attack_active = False
            intensity = 0.0
            mitigation = False

        rows.append(
            {
                "time": t.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "attack_active": "1" if attack_active else "0",
                "attack_type": "dos",
                "target": "5g",
                "intensity": f"{intensity:.2f}",
                "mitigation_active": "1" if mitigation else "0",
            }
        )

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["time", "attack_active", "attack_type", "target", "intensity", "mitigation_active"],
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
