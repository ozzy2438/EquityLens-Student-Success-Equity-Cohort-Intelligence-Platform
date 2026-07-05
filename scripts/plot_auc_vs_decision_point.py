"""Regenerates docs/images/auc_vs_decision_point.png.

Sweeps `census_engagement_score`'s own `connection_strength` as a proxy for
how much information has accumulated since enrolment -- NOT a calibrated
per-week measurement, just this project's one dial for "how much does the
behavioural signal share with the same latent risk that drives attrition."
See docs/model_design.md, "Discrimination is bounded by the information
available at the decision point."

Run from the repository root: python scripts/plot_auc_vs_decision_point.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from equitylens_risk.features import generate_census_engagement_signal
from equitylens_synthetic.outcomes import (
    assign_retention_outcomes,
    compute_auc,
    generate_latent_risk,
)
from equitylens_synthetic.population import build_raked_population, load_target_set

TARGET_SET_PATH = Path("data/calibration/targets_v3_2023ref.json")
OUTPUT_PATH = Path("docs/images/auc_vs_decision_point.png")
CENSUS_CONNECTION_STRENGTH_USED = 0.4

CONNECTION_STRENGTHS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
ILLUSTRATIVE_LABELS = [
    "~wk 2",
    "~wk 4",
    "~wk 6\n(census, used)",
    "~wk 9",
    "mid-sem",
    "full-year\n(S15 annual)",
]


def main() -> None:
    target_set = load_target_set(TARGET_SET_PATH)
    population, _convergence, _integerization = build_raked_population(
        target_set, 20000, institution_id="acu", seed=42
    )
    latent_risk = generate_latent_risk(len(population), seed=100)
    population, _retention_convergence = assign_retention_outcomes(
        population, target_set, connection_strength=0.7, shared_latent_risk=latent_risk, seed=42
    )

    aucs = []
    for connection_strength in CONNECTION_STRENGTHS:
        signal = generate_census_engagement_signal(
            population, latent_risk, connection_strength=connection_strength, seed=900
        )
        aucs.append(compute_auc(signal, population["retained"]))

    census_index = CONNECTION_STRENGTHS.index(CENSUS_CONNECTION_STRENGTH_USED)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(CONNECTION_STRENGTHS, aucs, marker="o", color="#2b6cb0", linewidth=2)
    ax.scatter(
        [CONNECTION_STRENGTHS[census_index]],
        [aucs[census_index]],
        color="#c53030",
        zorder=5,
        s=90,
        label="This project's census-date model",
    )
    ax.set_xlabel("connection_strength (proxy for information accumulated since enrolment)")
    ax.set_ylabel("AUC (behavioural signal alone vs. retained)")
    ax.set_title("Discrimination vs. decision-point lead time (measured, not fitted)")
    for connection_strength, label, auc in zip(
        CONNECTION_STRENGTHS, ILLUSTRATIVE_LABELS, aucs, strict=True
    ):
        ax.annotate(
            label,
            (connection_strength, auc),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
            fontsize=8,
        )
    ax.set_ylim(0.5, 0.75)
    ax.axhline(0.5, color="gray", linestyle=":", linewidth=1, label="chance")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
