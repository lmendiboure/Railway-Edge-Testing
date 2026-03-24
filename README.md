# Edge Evaluation Platform

This repository provides two ways to evaluate edge placement for a hybrid 5G + LEO setup:

1) Batch simulator for offline experiments and paper figures
2) Realtime replay + orchestrator for live demos and GUI monitoring

The platform computes service KPIs (ETCS2, Voice, Video), tail latency, and edge benefits across
multiple edge configurations.

## Requirements

- Python 3
- Install dependencies:

```
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Tests

```
PYTHONPATH=. python3 -m unittest
```

## Docker deployment (VM)

The platform can run two stacks:

Edge stack:

- `edge-simulator` (orchestrator endpoints + realtime replay)
- `edge-gui` (reads outputs and renders the GUI)

Security stack:

- `security-simulator` (orchestrator endpoints + security replay)
- `security-gui` (reads outputs and renders the GUI)

Optional gateway:

- `gateway` (reverse proxy to access GUIs/APIs without ports)

### 1) Prepare environment

```
cp .env.example .env
```

Adjust ports if needed:

- `SIM_PORT` (default 8080)
- `GUI_PORT` (default 8501)
- `SECURITY_PORT` (default 8090)
- `SECURITY_GUI_PORT` (default 8601)
- `GATEWAY_PORT` (default 80)

### 2) Launch

```
docker compose --profile edge up --build
```

Security only:

```
docker compose --profile security up --build
```

Full stack:

```
docker compose --profile edge --profile security up --build

Gateway (no ports in URLs):

```
docker compose --profile edge --profile security --profile gateway up --build
```
```

### 3) Verify

```
curl http://localhost:${SIM_PORT}/agents
curl http://localhost:${SIM_PORT}/status/railenium-edge-simulator
curl http://localhost:${SECURITY_PORT}/agents
curl http://localhost:${SECURITY_PORT}/status/railenium-security-simulator
```

GUI:

- Edge: `http://localhost:${GUI_PORT}`
- Security: `http://localhost:${SECURITY_GUI_PORT}`

Gateway:

- `http://localhost:${GATEWAY_PORT}/edge/`
- `http://localhost:${GATEWAY_PORT}/security/`

### 4) Start a realtime run

```
curl -s -X POST http://localhost:${SIM_PORT}/control/railenium-edge-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"example_scenario"}'
```

Start a security run:

```
curl -s -X POST http://localhost:${SECURITY_PORT}/control/railenium-security-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"dos_attack_demo"}'
```

## Mode 1: Batch simulator (offline/paper runs)

Run the simulator on a manifest, then aggregate metrics and generate plots.

Example (paper run):

```
PYTHONPATH=. python3 scripts/run.py \
  --manifest configs/paper_manifest.json \
  --output runs_paper_v4

PYTHONPATH=. python3 scripts/analyze.py \
  --manifest configs/paper_manifest.json \
  --runs runs_paper_v4

PYTHONPATH=. python3 scripts/derive_service_metrics.py \
  --manifest configs/paper_manifest.json \
  --runs runs_paper_v4 \
  --tail-configs P2-A,P2-B,P2-D,P2-E

PYTHONPATH=. python3 scripts/plot.py \
  --mapping configs/figure_mapping.json \
  --runs runs_paper_v4
```

Smaller sanity run:

```
PYTHONPATH=. python3 scripts/run.py \
  --manifest configs/sanity_short_manifest.json \
  --output runs_sanity_short
```

Outputs:
- Run data: `runs_*/<config>/seed_*/`
- Aggregated metrics: `runs_*/_aggregated/`
- Figures: `runs_*/_aggregated/figures/`

## Mode 2: Realtime replay + orchestrator

This mode replays a CSV trace and computes edge-centric metrics per slot.

### 1) Prepare a scenario

Scenario CSVs can be declared in `configs/realtime_manifest.json` or auto-discovered.
Any CSV placed in `scenarios/edge/` is auto-registered as a scenario using the
filename (without extension). Auto-discovered scenarios use `slot_ms=1000` unless
you override them in the manifest.
Columns required:

- `time` (epoch seconds/ms or ISO-8601)
- `gps_lat`, `gps_lon`, `speed_mps`

Optional per-tech columns:

- 5G: `e2e_latency_5g_ms`, `ul_mbps_5g`, `dl_mbps_5g`, `jitter_5g_ms`, `loss_5g`, `bler_5g`
- SAT: `e2e_latency_sat_ms`, `ul_mbps_sat`, `dl_mbps_sat`, `jitter_sat_ms`, `loss_sat`, `bler_sat`

Generate the example CSV (optional):

```
python3 scripts/generate_example_scenario.py
```

### 2) Start the orchestrator server

```
PYTHONPATH=. python3 scripts/realtime_server.py \
  --manifest configs/realtime_manifest.json \
  --edge-params configs/realtime_edge_params.json \
  --port 8000
```

### 3) Start a scenario (simulate an orchestrator client)

```
curl -s -X POST http://localhost:8000/control/railenium-edge-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"example_scenario"}'
```

Outputs are written to:
`runs/realtime_replay/<scenario>/<start_timestamp>/slot_metrics.jsonl`

### 4) Optional GUI

```
PYTHONPATH=. python3 scripts/realtime_gui_server.py \
  --run-dir runs/realtime_replay/example_scenario/<start_timestamp> \
  --port 8001
```

Open: `http://localhost:8001`

## Mode 3: Security simulator (skeleton)

This mode replays an attack scenario against baseline metrics and emits minimal
per-slot impacts (latency, jitter, loss, throughput).

### 1) Prepare a security scenario

Security scenarios are defined in `configs/security_manifest.json` and reference:

- Attack CSV: `scenarios/security/dos_attack_demo.csv`
- Baseline CSV: `scenarios/edge/example_scenario.csv`

Available demo modes:

- `interactive_demo`: baseline replay + live controls (no CSV attack timeline applied)
- `dos_attack_demo`: CSV-driven timeline for reproducible runs

Attack CSV columns:

- `time`
- `attack_active`
- `attack_type`
- `target`
- `intensity`
- `mitigation_active`

Generate the example attack CSV (optional):

```
python3 scripts/generate_security_scenario.py
```

### 2) Start the security orchestrator server

```
PYTHONPATH=. python3 scripts/security_server.py \
  --manifest configs/security_manifest.json \
  --port 8090
```

### 3) Start a security scenario

```
curl -s -X POST http://localhost:8090/control/railenium-security-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"interactive_demo"}'
```

Outputs are written to:
`runs/security/<scenario>/<start_timestamp>/slot_metrics.jsonl`

### 4) Optional security GUI

```
PYTHONPATH=. python3 scripts/security_gui_server.py \
  --output-root runs/security \
  --port 8601
```

Open: `http://localhost:8601`

The security GUI sends live control updates via:

```
POST /control/railenium-security-simulator
{"action":"set_attack", "attack_active": true, "attack_type": "dos", "target": "5g", "intensity": 0.6}
```

## Realtime edge parameters

`configs/realtime_edge_params.json` controls:

- Rolling window and baseline smoothing
- Edge configs to compare
- Alpha factors per tech/config
- Compute parameters
- Video filtering (bandwidth saved)
- Partial satellite deployment:
  - `sat_edge_fraction` per config (0..1)
  - `sat_detour_ms` per config (optional)
  - or `sat_edge_fraction_by_level` / `sat_detour_ms_by_level`

Partial SAT deployment blends raw and edge latency and adds a small detour penalty.

## Notes

- Output directories (`runs_*`, `runs/realtime_replay`) are ignored by git.
- Specs and local PDFs are ignored by git (see `.gitignore`).

## FAQ

**How do I choose which edge configs are compared in realtime?**

Edit `configs/realtime_edge_params.json`:

- `edge_configs` controls which configs appear in the GUI and outputs.
- `alpha` controls the latency reduction per config/tech.
- `sat_edge_fraction` enables partial SAT deployment.

**Where are the realtime outputs?**

Each run writes:
`runs/realtime_replay/<scenario>/<start_timestamp>/slot_metrics.jsonl`

**How do I reduce output size?**

- Increase `slot_ms` in `configs/realtime_manifest.json`.
- Reduce the number of `edge_configs` in `configs/realtime_edge_params.json`.

**How do I change the rolling window?**

Edit `window_s` in `configs/realtime_edge_params.json`.

**I want to add new metrics to the GUI. Where do they come from?**

- Slot metrics are written in `src/realtime/runner.py`.
- GUI reads them via `scripts/realtime_gui_server.py` (`/api/latest`, `/api/slots`).

## Architecture (High Level)

```
                   +-----------------------------+
                   |  Realtime Orchestrator API  |
                   |  scripts/realtime_server.py |
                   +-------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   |  Realtime Replay Runner     |
                   |  src/realtime/runner.py     |
                   +-------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   |  slot_metrics.jsonl         |
                   |  runs/realtime_replay/...   |
                   +-------------+---------------+
                                 |
                 +---------------+---------------+
                 |                               |
                 v                               v
   +-------------------------+      +-------------------------+
   | Batch Aggregation       |      | Minimal GUI             |
   | scripts/analyze.py      |      | scripts/realtime_gui... |
    +-------------------------+      +-------------------------+
```

## Architecture (Security)

```
                   +-----------------------------+
                   |  Security Orchestrator API  |
                   |  scripts/security_server.py |
                   +-------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   |  Security Replay Runner     |
                   |  src/security/runner.py     |
                   +-------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   |  slot_metrics.jsonl         |
                   |  runs/security/...          |
                   +-------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   |  Minimal Security GUI       |
                   |  scripts/security_gui...    |
                   +-----------------------------+
```

## Architecture (Gateway)

```
                   +-----------------------------+
                   |        Nginx Gateway        |
                   |        gateway/nginx.conf   |
                   +-------------+---------------+
                                 |
          +----------------------+----------------------+
          |                      |                      |
          v                      v                      v
   +--------------+      +-----------------+     +-------------------+
   | /edge/       | ---> | edge-gui (8501) |     | /edge-api/         |
   +--------------+      +-----------------+     +-------------------+
                                              -> | edge-simulator    |
                                                 | (8080)            |
                                                 +-------------------+

   +--------------+      +-------------------+   +-------------------+
   | /security/   | ---> | security-gui      |   | /security-api/     |
   +--------------+      | (8601)            |   +-------------------+
                                              -> | security-simulator|
                                                 | (8090)            |
                                                 +-------------------+
```
