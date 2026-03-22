import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.security.manifest import load_security_manifest


class TestSecurityManifest(unittest.TestCase):
    def test_interactive_allows_missing_attack_csv(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline_csv = tmp_path / "baseline.csv"
            baseline_csv.write_text("time,e2e_latency_5g_ms\n0,100\n", encoding="utf-8")
            manifest = tmp_path / "security_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "interactive_demo": {
                            "baseline_csv_path": str(baseline_csv),
                            "mode": "interactive",
                        }
                    }
                ),
                encoding="utf-8",
            )

            scenarios = load_security_manifest(manifest)
            cfg = scenarios["interactive_demo"]

            self.assertIsNone(cfg.attack_csv_path)
            self.assertEqual(cfg.mode, "interactive")

    def test_timeline_requires_attack_csv_entry(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline_csv = tmp_path / "baseline.csv"
            baseline_csv.write_text("time,e2e_latency_5g_ms\n0,100\n", encoding="utf-8")
            attack_csv = tmp_path / "attack.csv"
            attack_csv.write_text("time,attack_active\n0,0\n", encoding="utf-8")
            manifest = tmp_path / "security_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "timeline_demo": {
                            "attack_csv_path": str(attack_csv),
                            "baseline_csv_path": str(baseline_csv),
                            "mode": "timeline",
                        }
                    }
                ),
                encoding="utf-8",
            )

            scenarios = load_security_manifest(manifest)
            cfg = scenarios["timeline_demo"]

            self.assertIsNotNone(cfg.attack_csv_path)
            self.assertEqual(cfg.mode, "timeline")
