from __future__ import annotations

import argparse
import os

from src.security.server import create_server


def main() -> None:
    config_dir = os.getenv("SECURITY_CONFIG_DIR", "configs")
    default_manifest = os.path.join(config_dir, "security_manifest.json")
    default_runs = os.getenv("SECURITY_RUNS_DIR", "runs/security")

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("SECURITY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SECURITY_PORT", "8090")))
    parser.add_argument("--manifest", default=default_manifest)
    parser.add_argument("--output-root", default=default_runs)
    args = parser.parse_args()

    server = create_server(args.host, args.port, args.manifest, args.output_root)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
