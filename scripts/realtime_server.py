from __future__ import annotations

import argparse

from src.realtime.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--manifest", default="configs/realtime_manifest.json")
    parser.add_argument("--edge-params", default="configs/realtime_edge_params.json")
    args = parser.parse_args()

    server = create_server(args.host, args.port, args.manifest, args.edge_params)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
