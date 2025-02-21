import logging
import os
import platform
from bs4 import BeautifulSoup
from html2image import Html2Image

from .asset import Asset
from .cdx import search
from .session import Session
from .settings import DEFAULT_ROOT

logger = logging.getLogger(__name__)

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

try:
    from tqdm.auto import tqdm

    has_tqdm = True
except ImportError:
    has_tqdm = False

psl = platform.system().lower()
if "windows" in psl or "cygwin" in psl:
    invalid_chars = '<>:"\\|?*'
elif "darwin" in psl:
    invalid_chars = ":"
else:
    invalid_chars = ""


def replace_invalid_chars(path, fallback_char="_"):
    return "".join([fallback_char if c in invalid_chars else c for c in path])


class Pack(object):
    def __init__(self, url, timestamps=None, uniques_only=False, session=None):
        self.url = url + "/"
        prefix = "http://" if urlparse(url).scheme == "" else ""
        self.full_url = prefix + url
        self.parsed_url = urlparse(self.full_url)

        self.session = session or Session()

        if timestamps is None:
            self.timestamps = [
                snap["timestamp"]
                for snap in search(url, uniques_only=uniques_only, session=self.session)
            ]
        else:
            self.timestamps = timestamps

        self.assets = [Asset(self.url, ts) for ts in self.timestamps]

    def download_to(
        self,
        directory,
        raw=False,
        root=DEFAULT_ROOT,
        ignore_errors=False,
        no_clobber=False,
        progress=False,
        fallback_char="_",
        image=False,
    ):
        if progress and not has_tqdm:
            raise Exception(
                "To print progress bars, you must have `tqdm` installed. To install: pip install tqdm."
            )

        for asset in tqdm(self.assets) if progress else self.assets:
            path_head, path_tail = os.path.split(self.parsed_url.path)
            if path_tail == "":
                path_tail = f"{asset.timestamp}.html"

            filedir = os.path.join(
                directory,
                replace_invalid_chars(self.parsed_url.netloc, fallback_char),
                replace_invalid_chars(path_head.lstrip("/"), fallback_char),
            )

            filepath = os.path.join(
                filedir, replace_invalid_chars(path_tail, fallback_char)
            )

            if no_clobber and (
                os.path.exists(filepath) and os.path.getsize(filepath) > 0
            ):
                continue

            logger.info(
                "Fetching {0} @ {1}".format(asset.original_url, asset.timestamp)
            )

            try:
                content = asset.fetch(session=self.session, raw=raw, root=root)

                if content is None:
                    continue

            except Exception as e:
                if ignore_errors is True:
                    ex_name = ".".join([e.__module__, e.__class__.__name__])
                    logger.warn(
                        "ERROR -- {0} @ {1} -- {2}: {3}".format(
                            asset.original_url, asset.timestamp, ex_name, e
                        )
                    )
                    continue
                else:
                    raise

            try:
                os.makedirs(filedir)
            except OSError:
                pass

            with open(filepath, "wb") as f:
                logger.info("Writing to {0}\n".format(filepath))
                f.write(content)

            # add a base url to the saved HTML file so that images with relative path will be rendered
            # Open and read the HTML file
            with open(filepath, "r", encoding="utf-8") as file:
                soup = BeautifulSoup(file, "lxml")

            # Check if there's already a <base> tag
            base_tag = soup.base

            # If not, create one and add it to the <head> section
            if not base_tag:
                base = soup.new_tag("base", href="https://web.archive.org/")
                soup.head.insert(
                    0, base
                )  # Insert at the beginning of the <head> section

            # Save the modified HTML content
            with open(filepath, "w", encoding="utf-8") as file:
                file.write(str(soup))

            # Save images of HTML
            if image:
                hti = Html2Image(output_path=filedir)
                hti.screenshot(html_file=filepath, save_as=f"{asset.timestamp}.png")
