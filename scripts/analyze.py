from __future__ import annotations

import argparse
from pathlib import Path

from src.analysis.aggregate import analyze_runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="configs/paper_manifest.json")
    parser.add_argument("--runs", default="runs")
    args = parser.parse_args()

    analyze_runs(Path(args.manifest), Path(args.runs))


if __name__ == "__main__":
    main()
