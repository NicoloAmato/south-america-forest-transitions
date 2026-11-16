"""Render charts from summary tables and a thematic map from local MODIS inputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MultipleLocator, PercentFormatter

from forestchange import config, pipeline, zonal
from forestchange.grid import analysis_grid

matplotlib.use("Agg")

import matplotlib.pyplot as plt

BACKGROUND = "#f4f6f2"
INK = "#172a24"
MUTED = "#426154"
LOSS = "#74354d"
GEO_COLOURS = (BACKGROUND, "#cbd5cd", LOSS, "#167c69", "#c4a745", "#de7540")
YEARS = (config.YEAR_START, config.YEAR_END)


def _territory_chart(data: pd.DataFrame, values: pd.Series) -> tuple[Figure, Axes]:
    names = data["COUNTRY"].replace({"FrenchGuiana": "French Guiana", "F. Guiana": "French Guiana"})
    fig, ax = plt.subplots(figsize=(10.4, 6.5), facecolor=BACKGROUND)
    fig.subplots_adjust(left=0.192, right=0.96, bottom=0.155, top=0.79)
    ax.set_facecolor(BACKGROUND)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#d5ded7")
    ax.barh(names, values.fillna(0), height=0.67, color=LOSS)
    ax.set_ylim(-0.6, len(data) - 0.4)
    ax.tick_params(axis="both", length=0, pad=8, labelcolor=INK)
    ax.spines[:].set_visible(False)
    return fig, ax


def plot_chart(table: Path, output: Path) -> None:
    data = pd.read_csv(table).sort_values("DEFOR_km2")
    areas = data["DEFOR_km2"]
    fig, ax = _territory_chart(data, areas)
    gap = areas.max() * 0.018
    for index, area in enumerate(areas):
        ax.text(area + gap, index, f"{area:,.0f}", color=INK, va="center", fontsize=10)
    ax.set_xlim(0, areas.max() * 1.20)
    ax.xaxis.set_major_locator(MultipleLocator(100_000))
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{value / 1000:.0f}k" if value else "0")
    )
    ax.set_xlabel("Area classified as forest → non-forest (km²)", color=INK, labelpad=9)
    fig.text(0.058, 0.94, "Forest-to-non-forest transitions", fontsize=24, weight="bold", color=INK)
    fig.text(
        0.059,
        0.88,
        "South America  /  2001–2021  /  MODIS land cover",
        fontsize=12,
        color=MUTED,
    )
    fig.text(
        0.059,
        0.035,
        "Classified transitions from MCD12Q1 v6.1 · GADM 4.1 reporting areas · Nicolò Amato",
        fontsize=9,
        color=MUTED,
    )
    fig.savefig(output, dpi=160)
    plt.close(fig)


def forest_loss_share(transitions: pd.DataFrame) -> pd.Series:
    """Share of 2001 forest with valid cover in both years that became non-forest."""
    loss = transitions["forest_loss_px"]
    forest_2001 = loss + transitions["stable_forest_px"]
    return loss.div(forest_2001.where(forest_2001 > 0)).mul(100)


def plot_loss_share(transitions: Path, output: Path) -> None:
    data = pd.read_csv(transitions)
    data["loss_share"] = forest_loss_share(data)
    data = data.sort_values("loss_share", na_position="first")
    shares = data["loss_share"]
    fig, ax = _territory_chart(data, shares)

    for index, share in enumerate(shares):
        position, label = (1.5, "N/A") if pd.isna(share) else (share + 1.5, f"{share:.1f}%")
        ax.text(position, index, label, color=INK, va="center", fontsize=10)
    ax.set_xlim(0, 108)
    ax.set_xticks(range(0, 101, 20))
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.set_xlabel("Share of 2001 forest classified as non-forest in 2021", color=INK, labelpad=9)
    fig.text(
        0.058,
        0.94,
        "Forest-to-non-forest share by territory",
        fontsize=24,
        weight="bold",
        color=INK,
    )
    fig.text(
        0.059,
        0.88,
        "South America  /  2001–2021  /  MODIS land cover",
        fontsize=12,
        color=MUTED,
    )
    fig.text(
        0.059,
        0.055,
        "Base includes 2001 forest pixels with valid land-cover data in both years.",
        fontsize=9,
        color=MUTED,
    )
    fig.text(
        0.059,
        0.028,
        "MCD12Q1 v6.1 · GADM 4.1 reporting areas · Nicolò Amato",
        fontsize=9,
        color=MUTED,
    )
    fig.savefig(output, dpi=160)
    plt.close(fig)


def open_reporting_areas(path: Path, crs: str) -> gpd.GeoDataFrame:
    map_units = gpd.read_file(path, columns=["GU_A3"])
    selected = map_units[map_units["GU_A3"].isin(config.COUNTRIES)]
    missing = set(config.COUNTRIES) - set(selected["GU_A3"])
    if missing:
        raise ValueError(f"Natural Earth map units missing: {', '.join(sorted(missing))}")
    return selected.to_crs(crs)


def plot_map(data: Path, map_units: Path, output: Path, workers: int) -> None:
    grid = analysis_grid()
    boundaries = open_reporting_areas(map_units, grid.crs)
    print("Reading local MODIS mosaics for the Natural Earth map", flush=True)
    land_cover = [pipeline.land_cover(data, year, grid, workers) for year in YEARS]
    index = [
        pipeline.ndvi(data, config.NDVI_COMPOSITE_START[year], grid, workers) for year in YEARS
    ]
    final, transitions = pipeline.change_maps(*land_cover, *index)
    del land_cover, index, transitions

    zones = zonal.rasterize_zones(list(boundaries.geometry), grid)
    rows, columns = grid.window(*boundaries.total_bounds, pad=8)
    lookup = np.zeros(256, dtype=np.uint8)
    codes = [config.OTHER, config.DEFORESTATION, config.IMPROVED, config.STABLE, config.DEGRADED]
    lookup[codes] = np.arange(1, len(codes) + 1, dtype=np.uint8)
    clipped = lookup[final[rows, columns]]
    clipped[zones[rows, columns] == 0] = 0
    del final, zones
    # Use nearest pixel sampling for the categorical display.
    stride = 6
    display = clipped[::stride, ::stride]
    left = grid.x_min + columns.start * grid.pixel_size
    right = grid.x_min + columns.stop * grid.pixel_size
    top = grid.y_max - rows.start * grid.pixel_size
    bottom = grid.y_max - rows.stop * grid.pixel_size

    fig = plt.figure(figsize=(10.4, 7.4), facecolor=BACKGROUND)
    panel = fig.add_axes([0.065, 0.083, 0.56, 0.705], facecolor=BACKGROUND)
    panel.imshow(
        display,
        extent=(left, right, bottom, top),
        origin="upper",
        cmap=ListedColormap(GEO_COLOURS),
        vmin=0,
        vmax=len(GEO_COLOURS) - 1,
        interpolation="nearest",
    )
    panel.set_axis_off()
    side = fig.add_axes([0.64, 0.32, 0.31, 0.44])
    side.set_axis_off()
    side.text(0, 0.975, "MAP CLASSES", color=MUTED, weight="bold", fontsize=10)
    labels = [
        "Forest → non-forest",
        "Forest with higher NDVI",
        "Forest with similar NDVI",
        "Forest with lower NDVI",
        "Other areas",
    ]
    swatches = [GEO_COLOURS[i] for i in (2, 3, 4, 5, 1)]
    side.legend(
        [Patch(facecolor=colour, edgecolor="none") for colour in swatches],
        labels,
        loc="upper left",
        bbox_to_anchor=(-0.025, 0.88),
        frameon=False,
        labelcolor=INK,
        labelspacing=1.05,
        fontsize=11,
    )
    side.text(
        0,
        0.05,
        "NDVI change is shown where pixels\nare classified as forest in both years.\n\n"
        "Composites: 28 July 2001 and 2021.",
        fontsize=10,
        color=MUTED,
        linespacing=1.45,
    )
    fig.text(0.058, 0.952, "Forest change in South America", fontsize=25, weight="bold", color=INK)
    fig.text(
        0.059,
        0.905,
        "2001–2021  /  MODIS classification",
        fontsize=13,
        color=MUTED,
    )
    fig.text(
        0.059,
        0.036,
        "NASA MODIS v6.1 · 500 m analysis grid · Natural Earth 1:10m map units · Nicolò Amato",
        fontsize=9,
        color=MUTED,
    )
    fig.savefig(output, dpi=190)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--map-units", type=Path, help="render the map using a Natural Earth 10m map units ZIP"
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--table", type=Path, default=Path("results/forest_change_by_country.csv"))
    parser.add_argument(
        "--transitions", type=Path, default=Path("results/forest_transitions_by_country.csv")
    )
    parser.add_argument("--output", type=Path, default=Path("docs/figures"))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    plot_chart(args.table, args.output / "forest_loss_by_territory.png")
    plot_loss_share(args.transitions, args.output / "forest_loss_share_by_territory.png")
    if args.map_units is not None:
        plot_map(args.data, args.map_units, args.output / "forest_change_map.png", args.workers)


if __name__ == "__main__":
    main()
