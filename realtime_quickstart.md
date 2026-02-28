Realtime Orchestrator Quickstart

Overview
- Single-scenario operation: only one scenario runs at a time. The server rejects a new start if a run is already active.
- Outputs: per-slot JSON lines under runs/realtime_replay/<scenario>/<start_timestamp>/slot_metrics.jsonl.

1) Prepare a scenario
- Generate the example CSV (optional):

```
python3 scripts/generate_example_scenario.py
```

- Ensure configs/realtime_manifest.json points to your CSV:

```
{
  "example_scenario": {
    "csv_path": "scenarios/example_scenario.csv",
    "slot_ms": 1000,
    "output_dir": "runs_realtime/example_scenario"
  }
}
```

2) Start the server

```
PYTHONPATH=. python3 scripts/realtime_server.py --manifest configs/realtime_manifest.json --edge-params configs/realtime_edge_params.json --port 8000
```

3) Optional GUI (separate server, no extra orchestrator endpoints)

```
PYTHONPATH=. python3 scripts/realtime_gui_server.py --run-dir runs/realtime_replay/example_scenario/<start_timestamp> --port 8001
```

Open `http://localhost:8001` in a browser.

4) Orchestrator calls (HTTP)
- Agents:

```
GET http://localhost:8000/agents
```

- Readiness (uses configuration_name query param):

```
GET http://localhost:8000/readiness/railenium-edge-simulator?configuration_name=example_scenario
```

- Start (optionally include start_time ISO-8601):

```
POST http://localhost:8000/control/railenium-edge-simulator
{
  "action": "start",
  "configuration_name": "example_scenario"
}
```

- Status:

```
GET http://localhost:8000/status/railenium-edge-simulator
```

- Watch outputs:

```
tail -f runs/realtime_replay/example_scenario/<start_timestamp>/slot_metrics.jsonl
```

- Stop:

```
POST http://localhost:8000/control/railenium-edge-simulator
{
  "action": "stop"
}
```

Notes
- /status returns both status (UP/DOWN/BUSY) and state (started/stopped/failed).
- Start time alignment uses the first CSV timestamp and the real-time clock.
- Output files include slot_metrics.jsonl, summary.json, config_used.json.
