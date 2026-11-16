"""Read MODIS HDF4 tiles and resample them onto the analysis grid.

This replaces the "Build Virtual Raster" + "Export / Save As" steps of the
QGIS workflow, which mosaicked the tiles and reprojected them to ESRI:102033 at 500 m
with nearest-neighbour resampling.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from pyproj import Transformer

from .grid import Grid
from .sinusoidal import SINUSOIDAL_PROJ4, TILE_SIZE_M, tile_bounds

Tile = tuple[int, int]

_CHUNK_ROWS = 512
_EDGE_POINTS = 201


def read_layer(path: Path | str, layer: str) -> np.ndarray:
    """Read one scientific dataset (for example ``LC_Type1``) of a MODIS HDF4 file."""
    from pyhdf.SD import SD, SDC

    hdf = SD(str(path), SDC.READ)
    try:
        dataset = hdf.select(layer)
        try:
            return dataset.get()
        finally:
            dataset.endaccess()
    finally:
        hdf.end()


def tile_window(tile: Tile, grid: Grid) -> tuple[slice, slice] | None:
    """Rows and columns of ``grid`` that can receive data from a sinusoidal tile."""
    x_min, y_min, x_max, y_max = tile_bounds(*tile)
    t = np.linspace(0.0, 1.0, _EDGE_POINTS)
    edge_x = np.concatenate(
        [x_min + (x_max - x_min) * t, np.full_like(t, x_max), x_max - (x_max - x_min) * t,
         np.full_like(t, x_min)]
    )  # fmt: skip
    edge_y = np.concatenate(
        [np.full_like(t, y_max), y_max - (y_max - y_min) * t, np.full_like(t, y_min),
         y_min + (y_max - y_min) * t]
    )  # fmt: skip
    to_grid = Transformer.from_crs(SINUSOIDAL_PROJ4, grid.crs, always_xy=True)
    gx, gy = to_grid.transform(edge_x, edge_y)
    ok = np.isfinite(gx) & np.isfinite(gy)
    if not ok.any():
        return None
    return grid.window(gx[ok].min(), gy[ok].min(), gx[ok].max(), gy[ok].max(), pad=2)


def _fill_from_tile(
    tile: Tile, sources: Sequence[np.ndarray], targets: Sequence[np.ndarray], grid: Grid
) -> None:
    """Copy into ``targets`` every grid pixel whose centre falls inside ``tile``."""
    window = tile_window(tile, grid)
    if window is None:
        return
    rows, cols = window
    side = sources[0].shape[0]
    resolution = TILE_SIZE_M / side
    tile_x_min, _, _, tile_y_max = tile_bounds(*tile)
    to_sinusoidal = Transformer.from_crs(grid.crs, SINUSOIDAL_PROJ4, always_xy=True)
    xs = grid.x_centres(cols.start, cols.stop)

    for row0 in range(rows.start, rows.stop, _CHUNK_ROWS):
        row1 = min(row0 + _CHUNK_ROWS, rows.stop)
        gx, gy = np.meshgrid(xs, grid.y_centres(row0, row1))
        sx, sy = to_sinusoidal.transform(gx, gy)
        with np.errstate(invalid="ignore"):
            col = np.floor((sx - tile_x_min) / resolution)
            row = np.floor((tile_y_max - sy) / resolution)
            inside = (col >= 0) & (col < side) & (row >= 0) & (row < side)
        if not inside.any():
            continue
        src_rows = row[inside].astype(np.intp)
        src_cols = col[inside].astype(np.intp)
        for source, target in zip(sources, targets, strict=True):
            target[row0:row1, cols][inside] = source[src_rows, src_cols]


def resample_tiles(
    tiles: Mapping[Tile, Path],
    layers: Sequence[str],
    grid: Grid,
    fill_values: Sequence[int],
    workers: int = 4,
) -> list[np.ndarray]:
    """Nearest-neighbour resampling of MODIS tiles onto ``grid``.

    For every grid pixel the value of the tile pixel that contains its centre is taken
    (the rule of ``gdalwarp -r near``). Because the tiles do not overlap, each grid pixel
    is written by at most one tile, so tiles can be processed independently.

    Returns one array per layer, filled with the corresponding fill value where no tile
    provides data.
    """
    if not tiles:
        raise ValueError("no MODIS tiles to resample")
    items = sorted(tiles.items())
    hdf_lock = threading.Lock()  # the HDF4 library is not thread-safe

    def read(path: Path) -> list[np.ndarray]:
        with hdf_lock:
            sources = [read_layer(path, layer) for layer in layers]
        side = sources[0].shape[0]
        if any(source.shape != (side, side) for source in sources):
            raise ValueError(f"{path}: layers are not square tiles of the same size")
        return sources

    # The first tile is read up front to learn the data type of each layer.
    first = read(items[0][1])
    targets = [
        np.full(grid.shape, fill, dtype=source.dtype)
        for source, fill in zip(first, fill_values, strict=True)
    ]
    _fill_from_tile(items[0][0], first, targets, grid)
    del first

    def process(item: tuple[Tile, Path]) -> None:
        tile, path = item
        _fill_from_tile(tile, read(path), targets, grid)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(process, items[1:]))
    return targets
