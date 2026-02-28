from __future__ import annotations

import argparse
from pathlib import Path

from src.plot.plot_figures import generate_figures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", default="configs/figure_mapping.json")
    parser.add_argument("--runs", default="runs")
    parser.add_argument("--output", default="runs/_aggregated/figures")
    args = parser.parse_args()

    generate_figures(Path(args.mapping), Path(args.runs), Path(args.output))


if __name__ == "__main__":
    main()
