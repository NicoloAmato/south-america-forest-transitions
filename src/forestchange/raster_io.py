"""Write rasters of the analysis grid as compressed, tiled GeoTIFFs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling

from . import config
from .grid import Grid

_OVERVIEW_FACTORS = [2, 4, 8, 16, 32]


def _rgba(colour: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16), alpha)


# Colour table for the GIS output.
CHANGE_COLOURMAP = {
    config.OTHER: _rgba(config.LAND_COLOUR),
    **{code: _rgba(colour) for code, colour in config.CLASS_COLOURS.items()},
    config.NODATA: (0, 0, 0, 0),
}


def write_geotiff(
    path: Path,
    array: np.ndarray,
    grid: Grid,
    nodata: float | None = None,
    colourmap: dict[int, tuple[int, int, int, int]] | None = None,
    description: str | None = None,
) -> Path:
    """Write one band on the analysis grid. A colour map makes it open styled in QGIS."""
    if array.shape != grid.shape:
        raise ValueError(f"array shape {array.shape} does not match the grid {grid.shape}")
    path.parent.mkdir(parents=True, exist_ok=True)
    floating = np.issubdtype(array.dtype, np.floating)
    profile = {
        "driver": "GTiff",
        "height": grid.height,
        "width": grid.width,
        "count": 1,
        "dtype": array.dtype.name,
        "crs": grid.crs,
        "transform": grid.transform,
        "nodata": nodata,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "compress": "deflate",
        "predictor": 3 if floating else 2,
        "BIGTIFF": "IF_SAFER",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)
        if colourmap is not None:
            dst.write_colormap(1, colourmap)
            dst.colorinterp = [ColorInterp.palette]
        if description:
            dst.set_band_description(1, description)
        factors = [factor for factor in _OVERVIEW_FACTORS if factor <= min(grid.shape)]
        if factors:
            dst.build_overviews(factors, Resampling.nearest)
    return path
