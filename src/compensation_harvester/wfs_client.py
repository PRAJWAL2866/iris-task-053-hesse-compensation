
"""WFS discovery and feature retrieval."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import geopandas as gpd
import pandas as pd
import requests

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

WFS_NAMESPACES = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "ows": "http://www.opengis.net/ows/1.1",
    "wfs1": "http://www.opengis.net/wfs",
}


class WFSClientError(RuntimeError):
    """Raised when a WFS request or response is invalid."""


class WFSClient:
    """Discover WFS feature types and retrieve features in pages."""

    MAX_PAGES = 10_000

    def __init__(
        self,
        settings: Settings | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": "IRIS-Hesse-Compensation-Harvester/0.1"}
        )

    def _get(self, params: dict[str, Any]) -> requests.Response:
        """Perform an HTTP GET with a timeout and useful error reporting."""
        try:
            response = self.session.get(
                self.settings.wfs_url,
                params=params,
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            request_name = params.get("request", "request")
            raise WFSClientError(
                f"WFS request failed ({request_name}): {exc}"
            ) from exc

    def get_capabilities(self) -> str:
        """Retrieve and validate the WFS GetCapabilities XML response."""
        response = self._get(
            {
                "service": "WFS",
                "request": "GetCapabilities",
            }
        )

        content_type = response.headers.get("Content-Type", "").lower()
        body = response.text.strip()

        if not body:
            raise WFSClientError(
                "GetCapabilities returned an empty response."
            )

        if "xml" not in content_type:
            logger.warning(
                "Capabilities response has unexpected content type %r",
                content_type,
            )

        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise WFSClientError(
                "GetCapabilities did not return valid XML. "
                "The endpoint may be incorrect or may have returned HTML."
            ) from exc

        root_name = root.tag.split("}")[-1]

        if "exception" in root_name.lower():
            raise WFSClientError(
                "WFS service returned an exception: "
                f"{body[:1000]}"
            )

        if root_name != "WFS_Capabilities":
            raise WFSClientError(
                "Unexpected GetCapabilities XML root: "
                f"{root_name!r}; expected 'WFS_Capabilities'."
            )

        return body

    def discover_feature_types(self) -> list[str]:
        """Extract advertised feature type names from capabilities XML."""
        xml_text = self.get_capabilities()
        root = ET.fromstring(xml_text)

        names = [
            element.text.strip()
            for element in root.findall(
                ".//wfs:FeatureType/wfs:Name",
                WFS_NAMESPACES,
            )
            if element.text and element.text.strip()
        ]

        if not names:
            # WFS 1.0/1.1 commonly uses the WFS 1.x namespace.
            names = [
                element.text.strip()
                for element in root.findall(
                    ".//wfs1:FeatureType/wfs1:Name",
                    WFS_NAMESPACES,
                )
                if element.text and element.text.strip()
            ]

        if not names:
            logger.warning(
                "No feature types were found in the capabilities document."
            )

        return names

    def fetch_features(self) -> gpd.GeoDataFrame:
        """Fetch all pages of the configured feature type as GeoJSON.

        Uses WFS 2.0 ``count`` and ``startIndex`` parameters. Raises an
        error if feature types cannot be discovered or the configured
        layer is not advertised.
        """
        advertised = self.discover_feature_types()
        layer = self.settings.wfs_layer

        if not advertised:
            raise WFSClientError(
                "No feature types were advertised by the WFS service; "
                "cannot validate the configured layer."
            )

        if layer not in advertised:
            raise WFSClientError(
                f"Configured layer {layer!r} was not advertised. "
                f"Available feature types: {advertised}"
            )

        page_size = self.settings.page_size
        if page_size < 1:
            raise WFSClientError(
                f"Invalid WFS page size {page_size}; it must be positive."
            )

        frames: list[gpd.GeoDataFrame] = []
        start_index = 0
        pages_fetched = 0

        while True:
            if pages_fetched >= self.MAX_PAGES:
                raise WFSClientError(
                    "WFS pagination exceeded the safety limit "
                    f"of {self.MAX_PAGES} pages."
                )

            response = self._get(
                {
                    "service": "WFS",
                    "version": "2.0.0",
                    "request": "GetFeature",
                    "typeNames": layer,
                    "outputFormat": "application/json",
                    "count": page_size,
                    "startIndex": start_index,
                    "srsName": "EPSG:4326",
                }
            )

            # Tolerate simple mocked responses or wrappers without headers.
            headers = getattr(response, "headers", {})
            content_type = headers.get("Content-Type", "").lower()

            if "html" in content_type:
                raise WFSClientError(
                    "GetFeature returned an HTML response instead of "
                    "GeoJSON. Check the endpoint, layer, and server response."
                )

            try:
                page = gpd.read_file(
                    response.content,
                    driver="GeoJSON",
                )
            except Exception as exc:
                raise WFSClientError(
                    "Could not parse GetFeature response as GeoJSON. "
                    "Check the WFS output format, endpoint, and layer."
                ) from exc

            if page.empty:
                break

            if page.geometry.name not in page.columns:
                raise WFSClientError(
                    "GetFeature response does not contain a geometry column."
                )

            pages_fetched += 1
            frames.append(page)

            logger.info(
                "Fetched %s features at startIndex=%s",
                len(page),
                start_index,
            )

            if len(page) < page_size:
                break

            start_index += len(page)

        if not frames:
            return gpd.GeoDataFrame(
                geometry=gpd.GeoSeries([], crs="EPSG:4326"),
                crs="EPSG:4326",
            )

        combined = pd.concat(frames, ignore_index=True)

        return gpd.GeoDataFrame(
            combined,
            geometry="geometry",
            crs=frames[0].crs,
        )
