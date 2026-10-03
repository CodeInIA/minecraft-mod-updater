"""Mod icons for the mod table.

Icons come from Modrinth, are cached on disk and drawn together with the row's
checkbox in a single image, because a ttk.Treeview row can only show one image.
"""

import hashlib
import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageOps, ImageTk

from updater_core import CONFIG_DIR, JAR_ICON_PREFIX, USER_AGENT

ICON_DIR = os.path.join(CONFIG_DIR, "icons")
ICON = 24          # icon size in the table
BOX = 18           # checkbox size
GAP = 8            # space between checkbox and icon
SS = 4             # shapes are drawn 4x larger and scaled down for smooth edges
ACCENT = "#2E9E5B"


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * SS - 1, size * SS - 1), radius * SS, fill=255)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


class IconCache:
    def __init__(self) -> None:
        self._icons: Dict[str, Image.Image] = {}
        self._photos: Dict[Tuple, ImageTk.PhotoImage] = {}
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    # ----- loading -------------------------------------------------------- #

    @staticmethod
    def _path(url: str) -> str:
        return os.path.join(ICON_DIR, hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + ".png")

    def _prepare(self, raw: Image.Image) -> Image.Image:
        icon = ImageOps.contain(raw.convert("RGBA"), (ICON * 2, ICON * 2), Image.Resampling.LANCZOS)
        square = Image.new("RGBA", (ICON * 2, ICON * 2), (0, 0, 0, 0))
        square.paste(icon, ((ICON * 2 - icon.width) // 2, (ICON * 2 - icon.height) // 2), icon)
        return square

    def get(self, url: str) -> Optional[Image.Image]:
        if not url:
            return None
        if url not in self._icons:
            path = self._path(url)
            if not os.path.exists(path):
                return None
            try:
                with Image.open(path) as img:
                    self._icons[url] = img.convert("RGBA")
            except OSError:
                return None
        return self._icons[url]

    def missing(self, urls: Iterable[str]) -> List[str]:
        return sorted({u for u in urls if u and self.get(u) is None})

    def _fetch(self, url: str) -> bytes:
        if url.startswith(JAR_ICON_PREFIX):  # "jar:<jar path>!<member>": the icon inside a mod jar
            jar_path, _, member = url[len(JAR_ICON_PREFIX):].rpartition("!")
            with zipfile.ZipFile(jar_path) as jar:
                return jar.read(member)
        response = self._session.get(url, timeout=15)
        response.raise_for_status()
        return response.content

    def _download_one(self, url: str) -> None:
        try:
            with Image.open(io.BytesIO(self._fetch(url))) as raw:
                icon = self._prepare(raw)
            os.makedirs(ICON_DIR, exist_ok=True)
            icon.save(self._path(url), "PNG")
            self._icons[url] = icon
        except (requests.RequestException, OSError, ValueError, KeyError, zipfile.BadZipFile):
            pass  # the placeholder icon is used instead

    def download(self, urls: Iterable[str]) -> None:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(self._download_one, urls))

    # ----- drawing -------------------------------------------------------- #

    @staticmethod
    def _placeholder(dark: bool) -> Image.Image:
        size = ICON * SS
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), 5 * SS, fill="#3A3F45" if dark else "#D5D9DE")
        inset = 7 * SS
        draw.rounded_rectangle((inset, inset, size - inset, size - inset), 2 * SS,
                               outline="#6B727B" if dark else "#9AA1A9", width=2 * SS)
        return img.resize((ICON, ICON), Image.Resampling.LANCZOS)

    @staticmethod
    def _checkbox(checked: bool, dark: bool) -> Image.Image:
        size = BOX * SS
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        if checked:
            draw.rounded_rectangle((0, 0, size - 1, size - 1), 4 * SS, fill=ACCENT)
            draw.line([(4 * SS, 9 * SS), (7.5 * SS, 12.5 * SS), (14 * SS, 5.5 * SS)],
                      fill="white", width=int(2.2 * SS), joint="curve")
        else:
            draw.rounded_rectangle((SS, SS, size - 1 - SS, size - 1 - SS), 4 * SS,
                                   outline="#8A9099" if dark else "#7A8088", width=int(1.6 * SS))
        return img.resize((BOX, BOX), Image.Resampling.LANCZOS)

    def row_image(self, url: str, check: Optional[bool], dark: bool) -> ImageTk.PhotoImage:
        """Checkbox (None = no checkbox) + mod icon, as one image for a table row."""
        source = self.get(url)
        key = (url if source is not None else "", check, dark)
        if key not in self._photos:
            canvas = Image.new("RGBA", (BOX + GAP + ICON, ICON), (0, 0, 0, 0))
            if check is not None:
                box = self._checkbox(check, dark)
                canvas.paste(box, (0, (ICON - BOX) // 2), box)
            if source is not None:
                icon = source.resize((ICON, ICON), Image.Resampling.LANCZOS)
                icon.putalpha(Image.composite(icon.getchannel("A"), Image.new("L", icon.size, 0),
                                              _rounded_mask(ICON, 5)))
            else:
                icon = self._placeholder(dark)
            canvas.paste(icon, (BOX + GAP, 0), icon)
            self._photos[key] = ImageTk.PhotoImage(canvas)
        return self._photos[key]
