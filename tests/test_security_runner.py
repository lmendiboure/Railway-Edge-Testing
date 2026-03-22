import unittest
from pathlib import Path

from src.security.runner import (
    AttackRow,
    BaselineRow,
    SecurityRunner,
    build_attack_rows_from_baseline,
)


def _baseline_row(time_ms: int) -> BaselineRow:
    return BaselineRow(
        time_ms=time_ms,
        metrics_5g={
            "e2e_ms": 100.0,
            "ul_mbps": 20.0,
            "dl_mbps": 25.0,
            "bler": 0.0,
            "jitter_ms": 10.0,
            "loss": 0.01,
        },
        metrics_sat={
            "e2e_ms": 200.0,
            "ul_mbps": 8.0,
            "dl_mbps": 10.0,
            "bler": 0.0,
            "jitter_ms": 30.0,
            "loss": 0.02,
        },
    )


class TestSecurityRunner(unittest.TestCase):
    def test_interactive_mode_uses_live_state(self) -> None:
        baseline_rows = [_baseline_row(0)]
        attack_rows = build_attack_rows_from_baseline(baseline_rows)
        runner = SecurityRunner(
            scenario_name="interactive_demo",
            slot_ms=1000,
            attack_rows=attack_rows,
            baseline_rows=baseline_rows,
            attack_csv_path=None,
            baseline_csv_path=Path("baseline.csv"),
            output_root=Path("."),
            default_attack_type="dos",
            default_target="5g",
            mode="interactive",
        )
        runner.set_attack(
            attack_active=True,
            attack_type="dos",
            target="5g",
            intensity=0.5,
            mitigation_active=False,
        )

        slot = runner._build_slot(attack_rows[0], baseline_rows[0], baseline_rows[0].time_ms)

        self.assertTrue(slot["attack_active"])
        self.assertEqual(slot["attack_type"], "dos")
        self.assertEqual(slot["target_segment"], "5g")
        self.assertAlmostEqual(slot["attack_intensity"], 0.5)
        self.assertAlmostEqual(slot["impacted"]["latency_ms"], 130.0)
        self.assertAlmostEqual(slot["impacted"]["jitter_ms"], 20.0)
        self.assertAlmostEqual(slot["impacted"]["loss"], 0.02)
        self.assertAlmostEqual(slot["impacted"]["throughput_mbps"], 16.0)

    def test_timeline_mode_uses_csv_rows(self) -> None:
        baseline_rows = [_baseline_row(0)]
        attack_rows = [
            AttackRow(
                time_ms=0,
                time_iso="1970-01-01T00:00:00.000Z",
                attack_active=True,
                attack_type="loss",
                target="sat",
                intensity=1.0,
                mitigation_active=False,
            )
        ]
        runner = SecurityRunner(
            scenario_name="timeline_demo",
            slot_ms=1000,
            attack_rows=attack_rows,
            baseline_rows=baseline_rows,
            attack_csv_path=None,
            baseline_csv_path=Path("baseline.csv"),
            output_root=Path("."),
            default_attack_type="dos",
            default_target="5g",
            mode="timeline",
        )

        slot = runner._build_slot(attack_rows[0], baseline_rows[0], baseline_rows[0].time_ms)

        self.assertEqual(slot["target_segment"], "sat")
        self.assertAlmostEqual(slot["impacted"]["loss"], 0.07)

    def test_set_attack_clamps_intensity(self) -> None:
        baseline_rows = [_baseline_row(0)]
        attack_rows = build_attack_rows_from_baseline(baseline_rows)
        runner = SecurityRunner(
            scenario_name="interactive_demo",
            slot_ms=1000,
            attack_rows=attack_rows,
            baseline_rows=baseline_rows,
            attack_csv_path=None,
            baseline_csv_path=Path("baseline.csv"),
            output_root=Path("."),
            default_attack_type="dos",
            default_target="5g",
            mode="interactive",
        )

        state = runner.set_attack(intensity=1.8)
        self.assertEqual(state["intensity"], 1.0)
