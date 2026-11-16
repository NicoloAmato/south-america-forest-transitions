"""End-to-end run: MODIS tiles and country outlines in, final map and country table out.

See ``docs/workflow.md`` for the classification rules and output checks.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections.abc import Iterator, Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from . import analysis, config, earthdata, gadm, modis, raster_io, zonal
from .grid import Grid, analysis_grid

log = logging.getLogger("forestchange")

YEARS = (config.YEAR_START, config.YEAR_END)
_BLOCK_ROWS = 1024

NdviDates = Mapping[int, str]


# --- Where things live -------------------------------------------------------------------


def land_cover_dir(data_dir: Path, year: int) -> Path:
    return data_dir / "modis" / config.LAND_COVER_PRODUCT / f"A{year}001"


def reflectance_dir(data_dir: Path, day: str) -> Path:
    code = earthdata.acquisition_code(earthdata.composite_start(day))
    return data_dir / "modis" / config.REFLECTANCE_PRODUCT / code


def gadm_dir(data_dir: Path) -> Path:
    return data_dir / "gadm"


# --- Step 0: inputs ----------------------------------------------------------------------


def download_inputs(data_dir: Path, ndvi_dates: NdviDates = config.NDVI_COMPOSITE_START) -> None:
    """Fetch every input: MODIS land cover and reflectance tiles, GADM country outlines."""
    earthdata.ensure_login()
    for iso in config.COUNTRIES:
        gadm.fetch_level0(iso, gadm_dir(data_dir))
    log.info("GADM 4.1 outlines of %d countries ready", len(config.COUNTRIES))

    for year in YEARS:
        granules = earthdata.search_land_cover(year)
        log.info("%s %d: %d tiles", config.LAND_COVER_PRODUCT, year, len(granules))
        earthdata.download(granules, land_cover_dir(data_dir, year))

    for year in YEARS:
        granules = earthdata.search_reflectance(ndvi_dates[year])
        log.info(
            "%s composite of %s: %d tiles",
            config.REFLECTANCE_PRODUCT, ndvi_dates[year], len(granules),
        )  # fmt: skip
        earthdata.download(granules, reflectance_dir(data_dir, ndvi_dates[year]))


def _tiles(directory: Path) -> dict[modis.Tile, Path]:
    tiles = earthdata.local_tiles(directory)
    if not tiles:
        raise FileNotFoundError(f"no MODIS tiles in {directory}: run `forest-change download`")
    return tiles


# --- Steps 1-3: rasters ------------------------------------------------------------------


def _blocks(height: int) -> Iterator[slice]:
    for start in range(0, height, _BLOCK_ROWS):
        yield slice(start, min(start + _BLOCK_ROWS, height))


def land_cover(data_dir: Path, year: int, grid: Grid, workers: int) -> np.ndarray:
    """IGBP land cover of one year on the analysis grid (``LandCover_<year>_Riproiettato``)."""
    (array,) = modis.resample_tiles(
        _tiles(land_cover_dir(data_dir, year)),
        [config.LAND_COVER_LAYER],
        grid,
        [config.LAND_COVER_FILL],
        workers,
    )
    return array


def ndvi(data_dir: Path, day: str, grid: Grid, workers: int) -> np.ndarray:
    """NDVI of one 8-day composite on the analysis grid (``NDVI_<year>``)."""
    red, nir = modis.resample_tiles(
        _tiles(reflectance_dir(data_dir, day)),
        [config.RED_LAYER, config.NIR_LAYER],
        grid,
        [config.REFLECTANCE_FILL, config.REFLECTANCE_FILL],
        workers,
    )
    out = np.empty(grid.shape, dtype=np.float32)
    for rows in _blocks(grid.height):
        out[rows] = analysis.ndvi(red[rows], nir[rows])
    return out


def change_maps(
    lc_start: np.ndarray, lc_end: np.ndarray, ndvi_start: np.ndarray, ndvi_end: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """The final forest change map and the land-cover-only transition map."""
    final = np.empty(lc_start.shape, dtype=np.uint8)
    transitions = np.empty(lc_start.shape, dtype=np.uint8)
    for rows in _blocks(lc_start.shape[0]):
        change = analysis.ndvi_change(ndvi_start[rows], ndvi_end[rows])
        final[rows] = analysis.forest_change(lc_start[rows], lc_end[rows], change)
        transitions[rows] = analysis.forest_transitions(lc_start[rows], lc_end[rows])
    return final, transitions


# --- Step 4: zonal statistics ------------------------------------------------------------


def transition_table(histogram: np.ndarray, countries: pd.DataFrame) -> pd.DataFrame:
    """Per-country pixel counts of the forest / non-forest transitions (diagnostic)."""
    table = countries[["fid", "GID_0", "COUNTRY"]].reset_index(drop=True).copy()
    table["never_forest_px"] = histogram[:, analysis.NEVER_FOREST]
    table["forest_loss_px"] = histogram[:, analysis.FOREST_LOSS]
    table["stable_forest_px"] = histogram[:, analysis.FOREST_STABLE]
    table["forest_gain_px"] = histogram[:, analysis.FOREST_GAIN]
    table["nodata_px"] = histogram[:, config.NODATA]
    return table


# --- Everything --------------------------------------------------------------------------


def _versions() -> dict[str, str]:
    import pyproj
    import rasterio

    return {
        "numpy": np.__version__,
        "rasterio": rasterio.__version__,
        "gdal": rasterio.__gdal_version__,
        "pyproj": pyproj.__version__,
        "proj": pyproj.proj_version_str,
    }


def run(
    data_dir: Path,
    results_dir: Path,
    ndvi_dates: NdviDates = config.NDVI_COMPOSITE_START,
    keep_intermediates: bool = False,
    workers: int = 4,
) -> pd.DataFrame:
    """Run the whole analysis and write the outputs to ``results_dir``.

    Returns the per-country table (also written as ``forest_change_by_country.csv``).
    """
    started = time.time()
    grid = analysis_grid()
    intermediate = data_dir / "intermediate"

    def keep(name: str, array: np.ndarray, nodata: float) -> None:
        if keep_intermediates:
            raster_io.write_geotiff(intermediate / name, array, grid, nodata=nodata)

    log.info("1/5  land cover %d and %d -> 500 m grid", *YEARS)
    lc = {year: land_cover(data_dir, year, grid, workers) for year in YEARS}
    for year in YEARS:
        keep(f"LandCover_{year}.tif", lc[year], config.LAND_COVER_FILL)

    log.info("2/5  NDVI from the composites of %s and %s", *(ndvi_dates[y] for y in YEARS))
    index = {year: ndvi(data_dir, ndvi_dates[year], grid, workers) for year in YEARS}
    for year in YEARS:
        keep(f"NDVI_{year}.tif", index[year], float("nan"))

    log.info("3/5  forest masks, NDVI change classes and final map")
    final, transitions = change_maps(lc[YEARS[0]], lc[YEARS[1]], index[YEARS[0]], index[YEARS[1]])
    del lc, index

    log.info("4/5  zonal histogram per country")
    countries = gadm.load_countries(gadm_dir(data_dir))
    zones = zonal.rasterize_zones(list(countries.geometry), grid)
    n_zones = len(countries)
    table = zonal.change_table(zonal.zonal_histogram(final, zones, n_zones), countries)
    diagnostics = transition_table(zonal.zonal_histogram(transitions, zones, n_zones), countries)
    del transitions

    log.info("5/5  writing outputs to %s", results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    final[zones == 0] = config.NODATA  # clip the map to the study area
    raster_io.write_geotiff(
        results_dir / "forest_change_2001_2021.tif",
        final,
        grid,
        nodata=config.NODATA,
        colourmap=raster_io.CHANGE_COLOURMAP,
        description="1 deforestation, 10 improved, 20 stable, 30 degraded, 0 other land",
    )
    table.to_csv(results_dir / "forest_change_by_country.csv", index=False)
    geometry = countries[["GID_0", "geometry"]].merge(table, on="GID_0", validate="one_to_one")
    geometry.to_file(
        results_dir / "forest_change_by_country.gpkg", layer="forest_change_by_country", index=False
    )
    diagnostics.to_csv(results_dir / "forest_transitions_by_country.csv", index=False)

    metadata = {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "ndvi_composite_start": {str(year): ndvi_dates[year] for year in YEARS},
        "target_crs": grid.crs,
        "pixel_size_m": grid.pixel_size,
        "grid": {"x_min": grid.x_min, "y_max": grid.y_max, "width": grid.width,
                 "height": grid.height},  # fmt: skip
        "inputs": {
            **{
                f"{config.LAND_COVER_PRODUCT}_{year}": sorted(
                    path.name for path in _tiles(land_cover_dir(data_dir, year)).values()
                )
                for year in YEARS
            },
            **{
                f"{config.REFLECTANCE_PRODUCT}_{year}": sorted(
                    path.name
                    for path in _tiles(reflectance_dir(data_dir, ndvi_dates[year])).values()
                )
                for year in YEARS
            },
            "countries": list(countries["GID_0"]),
        },
        "software": _versions(),
    }
    (results_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    log.info("done in %.0f s", time.time() - started)
    return table
