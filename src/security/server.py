from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

from src.security.manifest import SecurityScenarioConfig, load_security_manifest
from src.security.runner import (
    SecurityRunner,
    build_attack_rows_from_baseline,
    load_attack_scenario,
    load_baseline,
)


AGENT_ID = os.getenv("SECURITY_AGENT_ID", "railenium-security-simulator")
DISPLAY_NAME = os.getenv("SECURITY_DISPLAY_NAME", "Railenium Security Simulator")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_bool(value: object) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return None


@dataclass
class RunnerManager:
    scenarios: Dict[str, SecurityScenarioConfig]
    output_root: Path
    runner: Optional[SecurityRunner] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def get_status(self) -> Dict[str, str]:
        if self.runner is None:
            return {"status": "UP", "state": "stopped"}
        if self.runner.state == "running":
            return {"status": "BUSY", "state": "started"}
        if self.runner.state == "failed":
            return {"status": "DOWN", "state": "failed"}
        return {"status": "UP", "state": "stopped"}

    def readiness(self, config_name: Optional[str]) -> Dict[str, object]:
        missing = []
        if self.runner and self.runner.state == "running":
            return {
                "ready": False,
                "missing": [],
                "message": "runner busy",
                "timestamp": _now_iso(),
            }
        if config_name:
            config = self.scenarios.get(config_name)
            if config is None:
                missing.append(f"scenario:{config_name}")
            else:
                if config.mode != "interactive":
                    if not config.attack_csv_path or not config.attack_csv_path.exists():
                        missing.append(str(config.attack_csv_path))
                if not config.baseline_csv_path.exists():
                    missing.append(str(config.baseline_csv_path))
        ready = not missing
        return {"ready": ready, "missing": missing, "timestamp": _now_iso()}

    def start(self, config_name: str, start_time: Optional[datetime]) -> Dict[str, object]:
        config = self.scenarios.get(config_name)
        if config is None:
            return {"accepted": False, "status": "failed", "message": "unknown scenario"}
        if config.mode != "interactive":
            if not config.attack_csv_path or not config.attack_csv_path.exists():
                return {
                    "accepted": False,
                    "status": "failed",
                    "message": f"missing attack CSV: {config.attack_csv_path}",
                }
        if not config.baseline_csv_path.exists():
            return {
                "accepted": False,
                "status": "failed",
                "message": f"missing baseline CSV: {config.baseline_csv_path}",
            }
        with self.lock:
            if self.runner and self.runner.state == "running":
                return {"accepted": False, "status": "failed", "message": "runner busy"}
            baseline_rows = load_baseline(config.baseline_csv_path)
            if not baseline_rows:
                return {
                    "accepted": False,
                    "status": "failed",
                    "message": "baseline scenario empty",
                }
            if config.mode == "interactive":
                attack_rows = build_attack_rows_from_baseline(baseline_rows)
            else:
                attack_csv_path = config.attack_csv_path
                if attack_csv_path is None:
                    return {
                        "accepted": False,
                        "status": "failed",
                        "message": "missing attack CSV",
                    }
                attack_rows = load_attack_scenario(attack_csv_path)
                if not attack_rows:
                    return {
                        "accepted": False,
                        "status": "failed",
                        "message": "attack scenario empty",
                    }
            self.runner = SecurityRunner(
                config.name,
                config.slot_ms,
                attack_rows,
                baseline_rows,
                config.attack_csv_path,
                config.baseline_csv_path,
                self.output_root,
                config.attack_type,
                config.target_segment,
                config.mode,
            )
            start_timestamp = self.runner.start(start_time)
        return {
            "accepted": True,
            "status": "started",
            "start_timestamp": start_timestamp,
        }

    def set_attack(self, payload: Dict[str, object]) -> Dict[str, object]:
        with self.lock:
            if not self.runner or self.runner.state != "running":
                return {"accepted": False, "status": "failed", "message": "runner not running"}
            attack_type = payload.get("attack_type")
            if attack_type is not None:
                attack_type = str(attack_type)
            target = payload.get("target")
            if target is not None:
                target = str(target)
            intensity = payload.get("intensity")
            intensity_value: Optional[float] = None
            if isinstance(intensity, (int, float, str)):
                try:
                    intensity_value = float(intensity)
                except ValueError:
                    intensity_value = None
            state = self.runner.set_attack(
                attack_active=_parse_bool(payload.get("attack_active")),
                attack_type=attack_type,
                target=target,
                intensity=intensity_value,
                mitigation_active=_parse_bool(payload.get("mitigation_active")),
            )
        return {"accepted": True, "status": "updated", "state": state}

    def stop(self) -> Dict[str, object]:
        with self.lock:
            if self.runner:
                self.runner.stop()
        return {"accepted": True, "status": "stopped"}


class OrchestratorHandler(BaseHTTPRequestHandler):
    manager: RunnerManager

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path == "/agents":
            _json_response(
                self,
                200,
                {
                    "agents": [
                        {"agent_id": AGENT_ID, "display_name": DISPLAY_NAME},
                    ]
                },
            )
            return

        if path.startswith("/status/"):
            agent_id = path.split("/", 2)[-1]
            if agent_id != AGENT_ID:
                _json_response(self, 404, {"error": "unknown agent"})
                return
            status = self.manager.get_status()
            status["timestamp"] = _now_iso()
            if self.manager.runner and self.manager.runner.last_error:
                status["message"] = self.manager.runner.last_error
            _json_response(self, 200, status)
            return

        if path.startswith("/readiness/"):
            agent_id = path.split("/", 2)[-1]
            if agent_id != AGENT_ID:
                _json_response(self, 404, {"error": "unknown agent"})
                return
            query = parse_qs(parsed.query)
            config_name = query.get("configuration_name", [None])[0]
            _json_response(self, 200, self.manager.readiness(config_name))
            return

        _json_response(self, 404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if not path.startswith("/control/"):
            _json_response(self, 404, {"error": "not found"})
            return
        agent_id = path.split("/", 2)[-1]
        if agent_id != AGENT_ID:
            _json_response(self, 404, {"error": "unknown agent"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            _json_response(self, 400, {"accepted": False, "status": "failed", "message": "bad json"})
            return

        action = payload.get("action")
        if action == "start":
            config_name = payload.get("configuration_name")
            if not config_name:
                _json_response(
                    self,
                    400,
                    {"accepted": False, "status": "failed", "message": "missing configuration_name"},
                )
                return
            start_time = payload.get("start_time")
            start_dt = None
            if start_time:
                raw = str(start_time).replace("Z", "+00:00")
                start_dt = datetime.fromisoformat(raw)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
            _json_response(self, 200, self.manager.start(config_name, start_dt))
            return

        if action == "stop":
            _json_response(self, 200, self.manager.stop())
            return

        if action == "set_attack":
            _json_response(self, 200, self.manager.set_attack(payload))
            return

        _json_response(self, 400, {"accepted": False, "status": "failed", "message": "unknown action"})


def create_server(host: str, port: int, manifest_path: str, output_root: str) -> ThreadingHTTPServer:
    scenarios = load_security_manifest(Path(manifest_path))
    output_root_path = Path(output_root)
    manager = RunnerManager(scenarios=scenarios, output_root=output_root_path)
    OrchestratorHandler.manager = manager
    return ThreadingHTTPServer((host, port), OrchestratorHandler)
