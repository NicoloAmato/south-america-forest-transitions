"""Country outlines from GADM 4.1 (administrative level 0).

GADM data are free for academic and non-commercial use but may not be redistributed,
so they are downloaded on demand and never committed to the repository.
See https://gadm.org/license.html
"""

from __future__ import annotations

import io
import zipfile
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from . import config


class RemoteFile(io.RawIOBase):
    """Read-only, seekable view of a file on a web server, using HTTP range requests.

    GADM publishes one zip archive per country that holds every administrative level
    (212 MB for Brazil). Opening the archive through this class lets ``zipfile`` read
    just the level-0 members instead of downloading the whole file.
    """

    def __init__(self, url: str, block_size: int = 4 * 1024 * 1024, timeout: float = 120.0):
        super().__init__()
        self._url = url
        self._block_size = block_size
        self._timeout = timeout
        self._session = requests.Session()
        head = self._session.head(url, allow_redirects=True, timeout=timeout)
        head.raise_for_status()
        if head.headers.get("Accept-Ranges", "").lower() != "bytes":
            raise OSError(f"{url}: the server does not support range requests")
        self._size = int(head.headers["Content-Length"])
        self._position = 0
        self._blocks: OrderedDict[int, bytes] = OrderedDict()

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self._size}[whence]
        self._position = max(base + offset, 0)
        return self._position

    def readinto(self, buffer) -> int:
        if self._position >= self._size:
            return 0
        index, offset = divmod(self._position, self._block_size)
        chunk = self._block(index)[offset : offset + len(buffer)]
        buffer[: len(chunk)] = chunk
        self._position += len(chunk)
        return len(chunk)

    def _block(self, index: int) -> bytes:
        if index in self._blocks:
            self._blocks.move_to_end(index)
            return self._blocks[index]
        start = index * self._block_size
        end = min(start + self._block_size, self._size) - 1
        response = self._session.get(
            self._url, headers={"Range": f"bytes={start}-{end}"}, timeout=self._timeout
        )
        response.raise_for_status()
        if response.status_code != 206 or len(response.content) != end - start + 1:
            raise OSError(f"{self._url}: unexpected answer to a range request")
        self._blocks[index] = response.content
        while len(self._blocks) > 4:
            self._blocks.popitem(last=False)
        return response.content

    def close(self) -> None:
        self._session.close()
        super().close()


def fetch_level0(iso: str, directory: Path) -> Path:
    """Download the level-0 shapefile of one country (if missing) and return its path."""
    stem = f"gadm41_{iso}_0"
    shapefile = directory / f"{stem}.shp"
    if shapefile.exists():
        return shapefile
    directory.mkdir(parents=True, exist_ok=True)
    url = config.GADM_URL.format(iso=iso)
    with io.BufferedReader(RemoteFile(url)) as remote, zipfile.ZipFile(remote) as archive:
        members = [name for name in archive.namelist() if Path(name).name.startswith(stem + ".")]
        if not any(name.endswith(".shp") for name in members):
            raise FileNotFoundError(f"{stem}.shp not found in {url}")
        # The .shp is written last: its presence marks a complete download.
        for name in sorted(members, key=lambda name: name.endswith(".shp")):
            (directory / Path(name).name).write_bytes(archive.read(name))
    return shapefile


def load_countries(
    directory: Path,
    isos: Sequence[str] = config.COUNTRIES,
    crs: str = config.TARGET_CRS,
) -> gpd.GeoDataFrame:
    """Country outlines merged into one layer and reprojected to the analysis CRS.

    Counterpart of the QGIS step "Merge vector layers (CRS: 102033)". The ``fid`` and
    ``layer`` columns identify the administrative units and their source layers.
    """
    frames = []
    for fid, iso in enumerate(isos, start=1):
        frame = gpd.read_file(fetch_level0(iso, directory))[["GID_0", "COUNTRY", "geometry"]]
        if len(frame) != 1:
            frame = frame.dissolve(by="GID_0", as_index=False, aggfunc="first")
        frame.insert(0, "fid", fid)
        frame["layer"] = f"gadm41_{iso}_0"
        frames.append(frame)
    merged = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    return merged.to_crs(crs)
