import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.realtime.manifest import load_realtime_manifest


class TestRealtimeManifest(unittest.TestCase):
    def test_auto_discovers_edge_scenarios(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edge_dir = tmp_path / "edge"
            edge_dir.mkdir(parents=True)
            scenario_path = edge_dir / "auto_demo.csv"
            scenario_path.write_text("time\n0\n", encoding="utf-8")
            manifest = tmp_path / "realtime_manifest.json"
            manifest.write_text(json.dumps({}), encoding="utf-8")

            old_env = os.environ.get("SIM_SCENARIO_DIR")
            os.environ["SIM_SCENARIO_DIR"] = str(tmp_path)
            try:
                scenarios = load_realtime_manifest(manifest)
            finally:
                if old_env is None:
                    os.environ.pop("SIM_SCENARIO_DIR", None)
                else:
                    os.environ["SIM_SCENARIO_DIR"] = old_env

            self.assertIn("auto_demo", scenarios)
            cfg = scenarios["auto_demo"]
            self.assertEqual(cfg.csv_path, scenario_path)
            self.assertEqual(cfg.slot_ms, 1000)
