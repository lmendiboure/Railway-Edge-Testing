GUI Quickstart (Realtime Replay)

1) (Optional) Generate the example scenario CSV

```
python3 scripts/generate_example_scenario.py
```

2) Start the realtime orchestrator server

```
PYTHONPATH=. python3 scripts/realtime_server.py \
  --manifest configs/realtime_manifest.json \
  --edge-params configs/realtime_edge_params.json \
  --port 8000
```

3) Start a scenario (simulate orchestrator)

```
curl -s -X POST http://localhost:8000/control/railenium-edge-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"example_scenario"}'
```

The response contains start_timestamp.

4) Find the latest run directory (if you don't want to copy the timestamp)

```
python3 - <<'PY'
from pathlib import Path
root = Path("runs/realtime_replay/example_scenario")
latest = max(root.iterdir(), key=lambda p: p.stat().st_mtime)
print(latest)
PY
```

5) Start the GUI server

```
PYTHONPATH=. python3 scripts/realtime_gui_server.py \
  --run-dir runs/realtime_replay/example_scenario/<start_timestamp> \
  --port 8001
```

6) Open the GUI

Open `http://localhost:8001` in a browser.

7) Stop the scenario

```
curl -s -X POST http://localhost:8000/control/railenium-edge-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"stop"}'
```
