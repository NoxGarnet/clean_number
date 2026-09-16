#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Point-distribution plots for specimen-level statistics."""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _plot_metric(units: pd.DataFrame, metric: str, ylabel: str, output_path: str) -> str | None:
    if units.empty or metric not in units.columns:
        return None
    groups = [
        (key, pd.to_numeric(group[metric], errors="coerce").dropna().to_numpy(float))
        for key, group in units.groupby("group_key", sort=True)
    ]
    groups = [(key, values) for key, values in groups if len(values)]
    if not groups:
        return None

    fig, ax = plt.subplots(figsize=(max(7.0, len(groups) * 1.45), 5.0))
    for index, (label, values) in enumerate(groups, 1):
        jitter = np.linspace(-0.08, 0.08, len(values)) if len(values) > 1 else np.array([0.0])
        ax.scatter(index + jitter, values, s=38, color="#4472C4", alpha=0.85, zorder=3)
        mean = float(np.mean(values))
        ax.plot([index - 0.18, index + 0.18], [mean, mean], color="#C00000", linewidth=2.2, zorder=4)
    ax.set_xticks(range(1, len(groups) + 1), [label for label, _ in groups], rotation=25, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Group")
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return output_path


def generate_statistical_plots(units: pd.DataFrame, figures_dir: str) -> list[str]:
    os.makedirs(figures_dir, exist_ok=True)
    outputs = []
    for metric, ylabel, filename in [
        ("strength_MPa", "Strength (MPa)", "statistics_strength_points.png"),
        ("modulus_GPa", "Modulus (GPa)", "statistics_modulus_points.png"),
    ]:
        output = _plot_metric(units, metric, ylabel, os.path.join(figures_dir, filename))
        if output:
            outputs.append(output)
    return outputs
