# Forest change in South America, 2001–2021

This geoinformatics project uses MODIS land cover and surface reflectance to
classify forest-to-non-forest transitions and NDVI change on a common 500 m grid.
The pipeline exports a GeoTIFF and area statistics that can be opened in QGIS.

Run the analysis from the repository root with uv and an Earthdata Login account.

```sh
uv sync --locked
uv run forest-change login
uv run forest-change reproduce
```

The generated files are written to `data/output/`.
