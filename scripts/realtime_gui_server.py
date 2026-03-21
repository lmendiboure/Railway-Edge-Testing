from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse


def _read_last_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    if path.stat().st_size == 0:
        return None
    read_size = min(path.stat().st_size, 1024 * 1024)
    with path.open("rb") as handle:
        handle.seek(-read_size, os.SEEK_END)
        data = handle.read(read_size).rstrip(b"\n")
    if not data:
        return None
    idx = data.rfind(b"\n")
    line = data[idx + 1 :] if idx >= 0 else data
    if not line:
        return None
    try:
        return json.loads(line.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _read_slots(path: Path, limit: Optional[int]) -> list:
    if not path.exists():
        return []
    slots = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                slots.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(slots) > limit:
                slots.pop(0)
    return slots


def _find_latest_run(output_root: Path) -> Optional[Path]:
    candidates = list(output_root.glob("**/slot_metrics.jsonl"))
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return latest.parent


class GuiHandler(BaseHTTPRequestHandler):
    base_dir: Path
    run_dir: Path
    output_root: Path
    default_scenario: Optional[str]
    fixed_run_dir: bool

    def _ensure_run_dir(self) -> None:
        if getattr(self, "fixed_run_dir", False):
            return
        search_root = self.output_root
        if self.default_scenario:
            candidate = self.output_root / self.default_scenario
            if candidate.exists():
                search_root = candidate
        latest = _find_latest_run(search_root)
        if latest is None:
            return
        current_slot = self.run_dir / "slot_metrics.jsonl"
        if not current_slot.exists():
            self.run_dir = latest
            return
        latest_slot = latest / "slot_metrics.jsonl"
        try:
            if latest_slot.stat().st_mtime > current_slot.stat().st_mtime:
                self.run_dir = latest
        except FileNotFoundError:
            self.run_dir = latest

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/latest":
            self._ensure_run_dir()
            slot_path = self.run_dir / "slot_metrics.jsonl"
            if not slot_path.exists():
                self._json(200, {"ok": False, "message": "no runs yet"})
                return
            latest = _read_last_json(slot_path)
            if latest is None:
                self._json(200, {"ok": False, "message": "no data"})
                return
            self._json(200, {"ok": True, "payload": latest})
            return

        if path == "/api/slots":
            self._ensure_run_dir()
            slot_path = self.run_dir / "slot_metrics.jsonl"
            if not slot_path.exists():
                self._json(200, {"ok": False, "message": "no runs yet", "payload": []})
                return
            query = parse_qs(parsed.query)
            limit = query.get("limit", [None])[0]
            limit_int = int(limit) if limit else None
            slots = _read_slots(slot_path, limit_int)
            self._json(200, {"ok": True, "payload": slots})
            return

        if path == "/api/info":
            self._ensure_run_dir()
            config_path = self.run_dir / "config_used.json"
            summary_path = self.run_dir / "summary.json"
            info = {
                "run_dir": str(self.run_dir),
                "config_used": None,
                "summary": None,
                "waiting": not (self.run_dir / "slot_metrics.jsonl").exists(),
            }
            if config_path.exists():
                info["config_used"] = json.loads(config_path.read_text(encoding="utf-8"))
            if summary_path.exists():
                info["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
            self._json(200, {"ok": True, "payload": info})
            return

        if path == "/":
            path = "/index.html"

        file_path = self.base_dir / path.lstrip("/")
        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return

        content_type = "text/plain"
        if file_path.suffix == ".html":
            content_type = "text/html"
        elif file_path.suffix == ".css":
            content_type = "text/css"
        elif file_path.suffix == ".js":
            content_type = "application/javascript"

        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    default_runs = os.getenv("GUI_RUNS_DIR", "runs/realtime_replay")
    default_run_dir = os.getenv("GUI_RUN_DIR")
    default_host = os.getenv("GUI_HOST", "0.0.0.0")
    default_port = int(os.getenv("GUI_PORT", "8001"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--run-dir", default=default_run_dir)
    parser.add_argument("--output-root", default=default_runs)
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent / "gui"
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = Path.cwd() / output_root

    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_absolute():
            run_dir = Path.cwd() / run_dir
    else:
        default_scenario = os.getenv("GUI_DEFAULT_SCENARIO")
        run_dir = None
        if default_scenario:
            candidate = output_root / default_scenario
            if candidate.exists():
                run_dir = _find_latest_run(candidate)
        if run_dir is None:
            run_dir = _find_latest_run(output_root)
        if run_dir is None:
            run_dir = output_root

    GuiHandler.base_dir = base_dir
    GuiHandler.run_dir = run_dir
    GuiHandler.output_root = output_root
    GuiHandler.default_scenario = os.getenv("GUI_DEFAULT_SCENARIO")
    GuiHandler.fixed_run_dir = bool(args.run_dir)

    server = ThreadingHTTPServer((args.host, args.port), GuiHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
