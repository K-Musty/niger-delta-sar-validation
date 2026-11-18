#!/usr/bin/env python3
"""
Generate a study-area map showing the 67 NOSDRA incident locations
in the Niger Delta, color-coded by habitat type.

Uses geopandas + matplotlib (no cartopy required).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from matplotlib.lines import Line2D

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

CAND_CSV = config.DATA_INTERIM / "candidates_flagged.csv"
OBS_CSV  = config.DATA_INTERIM / "observability_classes.csv"
OUT_PNG  = config.FIGURES / "figure_1_study_area.png"


def main():
    # Load incident data
    cand = pd.read_csv(CAND_CSV)
    obs  = pd.read_csv(OBS_CSV)

    # Get most common habitat per incident
    hab_mode = (
        obs.groupby("incident_id")["habitat_group"]
        .agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "unknown")
        .reset_index()
    )
    incidents = cand.merge(hab_mode, on="incident_id", how="left")
    incidents["habitat_group"] = incidents["habitat_group"].fillna("unknown")

    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(
        incidents,
        geometry=gpd.points_from_xy(incidents["lon"], incidents["lat"]),
        crs="EPSG:4326"
    )

    # Load Nigeria boundary. Prefer geopandas' own dataset, then the
    # naturalearth_lowres copy bundled with pyogrio.
    ne_candidates = []
    try:
        from geopandas.datasets import get_path
        ne_candidates.append(Path(get_path("naturalearth_lowres")))
    except Exception:
        pass
    ne_candidates.append(
        Path(sys.prefix) / "lib" / "python3.10" / "site-packages" /
        "pyogrio" / "tests" / "fixtures" / "naturalearth_lowres" /
        "naturalearth_lowres.shp"
    )
    ne_path = next((p for p in ne_candidates if p.exists()), None)
    if ne_path is None:
        raise FileNotFoundError(
            "No Natural Earth low-res boundary found; install the "
            "geopandas naturalearth_lowres dataset."
        )
    world = gpd.read_file(ne_path)
    nigeria = world[world["name"] == "Nigeria"]

    # Niger Delta extent (with padding)
    lon_min, lon_max = 4.5, 9.5
    lat_min, lat_max = 3.8, 7.2

    # Habitat colors
    habitat_colors = {
        "open_water": "#2196F3",  # blue
        "swamp": "#4CAF50",       # green
        "land": "#D32F2F",        # red
        "unknown": "#9E9E9E",     # grey
    }
    habitat_labels = {
        "open_water": "Open water",
        "swamp": "Swamp",
        "land": "Terrestrial",
        "unknown": "Unknown",
    }

    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(10, 8))

    # Plot Nigeria boundary
    nigeria.plot(ax=ax, color="#F5F5DC", edgecolor="#666666", linewidth=0.8)

    # Plot neighboring countries (for context)
    neighbors = world[world["name"].isin(["Cameroon", "Benin", "Niger", "Chad"])]
    neighbors.plot(ax=ax, color="#E8E8E8", edgecolor="#999999", linewidth=0.5)

    # Re-plot Nigeria on top
    nigeria.plot(ax=ax, color="#F5F5DC", edgecolor="#333333", linewidth=1.0)

    # NDDC state boundaries note
    nddc_states = ["ABIA", "AKWA IBOM", "BAYELSA", "CROSS RIVER",
                   "DELTA", "EDO", "IMO", "ONDO", "RIVERS"]

    # Plot incidents by habitat
    for hab, color in habitat_colors.items():
        subset = gdf[gdf["habitat_group"] == hab]
        if len(subset) > 0:
            subset.plot(
                ax=ax,
                color=color,
                markersize=60,
                edgecolor="black",
                linewidth=0.5,
                zorder=5,
                label=f"{habitat_labels[hab]} (n={len(subset)})"
            )

    # Set extent
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)

    # Labels
    ax.set_xlabel("Longitude (°E)", fontsize=11)
    ax.set_ylabel("Latitude (°N)", fontsize=11)
    ax.set_title("Study area: NOSDRA incident locations\nin the Niger Delta (n=67)",
                 fontsize=13, fontweight="bold")

    # Grid
    ax.grid(True, alpha=0.3, linestyle="--")

    # Legend
    ax.legend(
        loc="upper left",
        fontsize=9,
        framealpha=0.9,
        edgecolor="#CCCCCC",
        title="Habitat type",
        title_fontsize=10,
    )

    # Add state labels at approximate centroids
    state_labels = {
        "Rivers": (6.95, 4.85),
        "Bayelsa": (6.15, 4.75),
        "Delta": (5.75, 5.55),
        "Akwa Ibom": (7.85, 4.95),
        "Abia": (7.45, 5.55),
        "Imo": (7.0, 5.55),
        "Edo": (5.65, 6.55),
        "Cross River": (8.55, 5.85),
        "Ondo": (4.85, 6.55),
    }
    for state, (lon, lat) in state_labels.items():
        if lon_min < lon < lon_max and lat_min < lat < lat_max:
            ax.annotate(
                state, xy=(lon, lat),
                fontsize=7, ha="center", va="center",
                color="#555555", fontstyle="italic",
            )

    # North arrow
    ax.annotate(
        "N", xy=(0.95, 0.95), xycoords="axes fraction",
        fontsize=14, fontweight="bold", ha="center", va="top"
    )
    ax.annotate(
        "", xy=(0.95, 0.94), xycoords="axes fraction",
        xytext=(0.95, 0.86), textcoords="axes fraction",
        arrowprops=dict(arrowstyle="->", lw=1.5, color="black")
    )

    # Scale bar (approximate)
    # At ~5°N, 1° longitude ≈ 111 km
    bar_lon = lon_min + 0.5
    bar_lat = lat_min + 0.3
    bar_length_deg = 1.0  # ~111 km
    ax.plot([bar_lon, bar_lon + bar_length_deg], [bar_lat, bar_lat],
            color="black", linewidth=2)
    ax.text(bar_lon + bar_length_deg / 2, bar_lat + 0.1, "~111 km",
            ha="center", fontsize=8)

    # Add Gulf of Guinea label
    ax.text(6.0, 4.0, "Gulf of Guinea", fontsize=9, fontstyle="italic",
            color="#4477AA", ha="center")

    plt.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PNG, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()

    print(f"Study area map saved to {OUT_PNG}")
    print(f"Incidents plotted: {len(gdf)}")
    for hab in habitat_colors:
        n = len(gdf[gdf["habitat_group"] == hab])
        if n > 0:
            print(f"  {habitat_labels[hab]}: {n}")


if __name__ == "__main__":
    main()
