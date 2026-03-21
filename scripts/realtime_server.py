from __future__ import annotations

import argparse
import os

from src.realtime.server import create_server


def main() -> None:
    config_dir = os.getenv("SIM_CONFIG_DIR", "configs")
    default_manifest = os.path.join(config_dir, "realtime_manifest.json")
    default_edge_params = os.path.join(config_dir, "realtime_edge_params.json")

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("SIM_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SIM_PORT", "8000")))
    parser.add_argument("--manifest", default=default_manifest)
    parser.add_argument("--edge-params", default=default_edge_params)
    args = parser.parse_args()

    server = create_server(args.host, args.port, args.manifest, args.edge_params)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
