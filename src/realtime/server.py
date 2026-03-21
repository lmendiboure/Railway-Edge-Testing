from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

from src.realtime.edge_params import EdgeParams, load_edge_params
from src.realtime.manifest import ScenarioConfig, load_realtime_manifest
from src.realtime.runner import RealtimeRunner, load_scenario


AGENT_ID = os.getenv("SIM_AGENT_ID", "railenium-edge-simulator")
DISPLAY_NAME = os.getenv("SIM_DISPLAY_NAME", "Railenium Edge Simulator")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class RunnerManager:
    scenarios: Dict[str, ScenarioConfig]
    edge_params: EdgeParams
    runner: Optional[RealtimeRunner] = None
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
            elif not config.csv_path.exists():
                missing.append(str(config.csv_path))
        if not self.edge_params.source_path.exists():
            missing.append(str(self.edge_params.source_path))
        ready = not missing
        return {"ready": ready, "missing": missing, "timestamp": _now_iso()}

    def start(self, config_name: str, start_time: Optional[datetime]) -> Dict[str, object]:
        config = self.scenarios.get(config_name)
        if config is None:
            return {"accepted": False, "status": "failed", "message": "unknown scenario"}
        if not config.csv_path.exists():
            return {
                "accepted": False,
                "status": "failed",
                "message": f"missing CSV: {config.csv_path}",
            }
        with self.lock:
            if self.runner and self.runner.state == "running":
                return {"accepted": False, "status": "failed", "message": "runner busy"}
            rows = load_scenario(config.csv_path)
            self.runner = RealtimeRunner(
                config.name,
                config.slot_ms,
                rows,
                config.csv_path,
                self.edge_params,
            )
            start_timestamp = self.runner.start(start_time)
        return {
            "accepted": True,
            "status": "started",
            "start_timestamp": start_timestamp,
        }

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

        _json_response(self, 400, {"accepted": False, "status": "failed", "message": "unknown action"})


def create_server(host: str, port: int, manifest_path: str, edge_params_path: str) -> ThreadingHTTPServer:
    scenarios = load_realtime_manifest(Path(manifest_path))
    edge_params = load_edge_params(Path(edge_params_path))
    manager = RunnerManager(scenarios=scenarios, edge_params=edge_params)
    OrchestratorHandler.manager = manager
    return ThreadingHTTPServer((host, port), OrchestratorHandler)
