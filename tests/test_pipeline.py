"""Exercise the analysis on small rasters with real HDF, GeoTIFF and GeoPackage I/O."""

import json

import geopandas as gpd
import numpy as np
import rasterio
from pyhdf.SD import SD, SDC
from shapely.geometry import box

from forestchange import analysis, compare, config, pipeline
from forestchange.grid import Grid
from forestchange.sinusoidal import SINUSOIDAL_PROJ4, TILE_SIZE_M, tile_bounds


def test_ndvi_thresholds_and_missing_values():
    red = np.array([100, 0, config.REFLECTANCE_FILL])
    nir = np.array([300, 0, 100])
    np.testing.assert_allclose(analysis.ndvi(red, nir), [0.5, np.nan, np.nan])
    values = np.array([-2, -0.101, -0.1, 0.1, 0.101, 2, np.nan], dtype=np.float32)
    classes = analysis.classify_ndvi_change(values)
    np.testing.assert_array_equal(classes, [30, 30, 20, 20, 10, 10, 0])


def write_hdf(directory, filename, layers):
    directory.mkdir(parents=True, exist_ok=True)
    dataset = SD(str(directory / filename), SDC.WRITE | SDC.CREATE)
    try:
        for name, kind, samples in layers:
            band = dataset.create(name, kind, (5, 5))
            band[:] = np.tile(samples, (5, 1))
            band.endaccess()
    finally:
        dataset.end()


def test_synthetic_pipeline(tmp_path, monkeypatch):
    tile = "h12v09"
    dates = config.NDVI_COMPOSITE_START
    for year, land, nir in (
        (2001, [1, 1, 1, 1, 255], [300, 100, 300, 300, 100]),
        (2021, [8, 1, 1, 1, 1], [300, 300, 300, 100, 100]),
    ):
        write_hdf(
            pipeline.land_cover_dir(tmp_path, year),
            f"MCD12Q1.A{year}001.{tile}.061.test.hdf",
            [(config.LAND_COVER_LAYER, SDC.UINT8, np.array(land, dtype=np.uint8))],
        )
        write_hdf(
            pipeline.reflectance_dir(tmp_path, dates[year]),
            f"MOD09Q1.A{year}209.{tile}.061.test.hdf",
            [
                (config.RED_LAYER, SDC.INT16, np.full(5, 100, dtype=np.int16)),
                (config.NIR_LAYER, SDC.INT16, np.array(nir, dtype=np.int16)),
            ],
        )

    x_min, y_min, x_max, y_max = tile_bounds(12, 9)
    grid = Grid(SINUSOIDAL_PROJ4, x_min, y_max, TILE_SIZE_M / 5, 5, 5)
    countries = gpd.GeoDataFrame(
        {"fid": [1], "GID_0": ["TEST"], "COUNTRY": ["Test area"]},
        geometry=[box(x_min, y_min, x_max, y_max)],
        crs=grid.crs,
    )
    monkeypatch.setattr(pipeline, "analysis_grid", lambda: grid)
    monkeypatch.setattr(pipeline.gadm, "load_countries", lambda *_: countries)
    output = tmp_path / "output"
    table = pipeline.run(tmp_path, output, workers=1)
    counts = table.iloc[0]
    for code in ("1", "10", "20", "30", "NODATA"):
        assert counts[f"FIN_{code}"] == 5
    assert counts["FIN_0"] == 0
    with rasterio.open(output / "forest_change_2001_2021.tif") as result:
        np.testing.assert_array_equal(result.read(1)[0], [1, 10, 20, 30, 255])
        assert result.nodata == 255
    assert gpd.read_file(output / "forest_change_by_country.gpkg")["GID_0"].tolist() == ["TEST"]
    metadata = json.loads((output / "run_metadata.json").read_text())
    assert metadata["ndvi_composite_start"]["2001"] == dates[2001]
    summary = output / "forest_change_by_country.csv"
    assert (compare.compare_tables(summary, summary) == 0).all().all()
