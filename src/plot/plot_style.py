from __future__ import annotations

import matplotlib as mpl


def apply_style() -> None:
    mpl.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "figure.figsize": (7.0, 4.0),
            "font.family": "serif",
            "font.serif": ["DejaVu Serif"],
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "axes.linewidth": 0.8,
            "lines.linewidth": 1.6,
            "lines.markersize": 4,
            "legend.fontsize": 9,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "grid.alpha": 0.25,
        }
    )


def palette() -> list[str]:
    return ["#1B4965", "#5FA8D3", "#CAE9FF", "#62B6CB", "#8A5A44", "#D4A373"]
