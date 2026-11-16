"""Find and download the MODIS tiles from NASA Earthdata (LP DAAC).

Searching the catalogue is anonymous; downloading needs a free Earthdata Login account
(https://urs.earthdata.nasa.gov). Credentials are never stored in this repository: they
are read from the ``EARTHDATA_TOKEN`` environment variable or from ``~/.netrc``.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import earthaccess
from earthaccess.exceptions import LoginStrategyUnavailable

from . import config
from .sinusoidal import parse_acquisition, parse_tile

Tile = tuple[int, int]
_COMPOSITE_DAYS = 8


class MissingCredentials(RuntimeError):
    """No Earthdata Login credentials are configured on this machine."""


def interactive_login() -> None:
    """Ask for the Earthdata username and password and save them to ``~/.netrc``."""
    auth = earthaccess.login(strategy="interactive", persist=True)
    if not auth.authenticated:
        raise MissingCredentials("Earthdata Login did not accept the credentials")


def ensure_login() -> None:
    """Authenticate with stored credentials, without ever prompting."""
    for strategy in ("environment", "netrc"):
        try:
            auth = earthaccess.login(strategy=strategy)
        except LoginStrategyUnavailable:
            continue
        if auth.authenticated:
            return
    raise MissingCredentials(
        "No NASA Earthdata credentials found. Create a free account at "
        "https://urs.earthdata.nasa.gov and run `forest-change login` once, "
        "or set the EARTHDATA_TOKEN environment variable."
    )


def composite_start(day: str | dt.date) -> dt.date:
    """Validate the first day of an 8-day MODIS composite (day of year 1, 9, 17, ...)."""
    date = dt.date.fromisoformat(day) if isinstance(day, str) else day
    offset = (date.timetuple().tm_yday - 1) % _COMPOSITE_DAYS
    if offset:
        previous = date - dt.timedelta(days=offset)
        following = previous + dt.timedelta(days=_COMPOSITE_DAYS)
        options = [previous] + ([following] if following.year == date.year else [])
        raise ValueError(
            f"{date} is not the first day of an 8-day composite; nearest: "
            + " or ".join(str(option) for option in options)
        )
    return date


def acquisition_code(date: dt.date) -> str:
    """The ``AYYYYDDD`` token MODIS file names use for a date."""
    return f"A{date.year}{date.timetuple().tm_yday:03d}"


def _granule_name(granule) -> str:
    for link in granule.data_links():
        name = Path(link.split("?", 1)[0]).name
        if name.lower().endswith(".hdf"):
            return name
    raise ValueError("Earthdata returned a MODIS granule without an HDF download link")


def _search(product: str, start: dt.date, end: dt.date) -> list:
    """Granules of one acquisition over the study area (one per tile)."""
    found = earthaccess.search_data(
        short_name=product,
        version=config.MODIS_VERSION,
        temporal=(start.isoformat(), end.isoformat()),
        bounding_box=config.SEARCH_BBOX,
    )
    wanted = (start.year, start.timetuple().tm_yday)
    by_tile = {}
    for granule in found:
        name = _granule_name(granule)
        if parse_acquisition(name) == wanted:
            by_tile[parse_tile(name)] = granule
    return [by_tile[tile] for tile in sorted(by_tile)]


def search_land_cover(year: int) -> list:
    """MCD12Q1 granules (yearly land cover) of ``year``."""
    return _search(config.LAND_COVER_PRODUCT, dt.date(year, 1, 1), dt.date(year, 12, 31))


def search_reflectance(day: str | dt.date) -> list:
    """MOD09Q1 granules of the 8-day composite starting on ``day``."""
    start = composite_start(day)
    last = min(start + dt.timedelta(days=_COMPOSITE_DAYS - 1), dt.date(start.year, 12, 31))
    return _search(config.REFLECTANCE_PRODUCT, start, last)


def download(granules: list, directory: Path) -> dict[Tile, Path]:
    """Download granules (skipping files already present) and index them by tile."""
    if not granules:
        raise RuntimeError(f"Earthdata returned no granules for {directory.name}")
    directory.mkdir(parents=True, exist_ok=True)
    paths = earthaccess.download(granules, local_path=directory, threads=8)
    downloaded = {Path(path).name: Path(path) for path in paths if Path(path).is_file()}
    expected = {_granule_name(granule) for granule in granules}
    if missing := expected - downloaded.keys():
        raise RuntimeError(f"{len(missing)} MODIS files missing in {directory}; retry the download")
    return {parse_tile(name): downloaded[name] for name in sorted(expected)}


def local_tiles(directory: Path) -> dict[Tile, Path]:
    """Index the HDF files already downloaded to ``directory`` by tile."""
    return {parse_tile(path.name): path for path in sorted(directory.glob("*.hdf"))}
