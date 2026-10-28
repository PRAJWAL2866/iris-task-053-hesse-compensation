
import geopandas as gpd
import pytest
from shapely.geometry import Point

from src.compensation_harvester.config import Settings
from src.compensation_harvester.wfs_client import WFSClient, WFSClientError


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        wfs_layer="test:compensation_sites",
        page_size=2,
    )


def test_discover_feature_types(settings, monkeypatch):
    client = WFSClient(settings)

    capabilities = """<?xml version="1.0"?>
    <wfs:WFS_Capabilities
        xmlns:wfs="http://www.opengis.net/wfs/2.0">
        <wfs:FeatureTypeList>
            <wfs:FeatureType>
                <wfs:Name>test:compensation_sites</wfs:Name>
            </wfs:FeatureType>
        </wfs:FeatureTypeList>
    </wfs:WFS_Capabilities>
    """

    monkeypatch.setattr(
        client,
        "get_capabilities",
        lambda: capabilities,
    )

    assert client.discover_feature_types() == [
        "test:compensation_sites"
    ]


def test_fetch_features_paginates(settings, monkeypatch):
    client = WFSClient(settings)

    monkeypatch.setattr(
        client,
        "discover_feature_types",
        lambda: [settings.wfs_layer],
    )

    requested_params = []

    def fake_get(params):
        requested_params.append(params)
        return type("Response", (), {"content": b"mock"})()

    monkeypatch.setattr(client, "_get", fake_get)

    pages = [
        gpd.GeoDataFrame(
            {"fo_komp_id": ["A", "B"]},
            geometry=[Point(8, 50), Point(9, 51)],
            crs="EPSG:4326",
        ),
        gpd.GeoDataFrame(
            {"fo_komp_id": ["C"]},
            geometry=[Point(10, 52)],
            crs="EPSG:4326",
        ),
    ]

    def fake_read_file(*args, **kwargs):
        return pages.pop(0)

    monkeypatch.setattr(
        "src.compensation_harvester.wfs_client.gpd.read_file",
        fake_read_file,
    )

    result = client.fetch_features()

    assert len(result) == 3
    assert result["fo_komp_id"].tolist() == ["A", "B", "C"]
    assert requested_params[0]["startIndex"] == 0
    assert requested_params[1]["startIndex"] == 2
    assert requested_params[0]["count"] == 2


def test_fetch_features_rejects_unadvertised_layer(settings, monkeypatch):
    client = WFSClient(settings)

    monkeypatch.setattr(
        client,
        "discover_feature_types",
        lambda: ["test:another_layer"],
    )

    with pytest.raises(WFSClientError, match="was not advertised"):
        client.fetch_features()




def test_fetch_features_stops_at_pagination_safety_limit(
    settings, monkeypatch
):
    client = WFSClient(settings)
    client.MAX_PAGES = 2

    monkeypatch.setattr(
        client,
        "discover_feature_types",
        lambda: [settings.wfs_layer],
    )

    requested_params = []

    def fake_get(params):
        requested_params.append(params)
        return type("Response", (), {"content": b"mock"})()

    monkeypatch.setattr(client, "_get", fake_get)

    def fake_read_file(*args, **kwargs):
        return gpd.GeoDataFrame(
            {"fo_komp_id": ["A", "B"]},
            geometry=[Point(8, 50), Point(9, 51)],
            crs="EPSG:4326",
        )

    monkeypatch.setattr(
        "src.compensation_harvester.wfs_client.gpd.read_file",
        fake_read_file,
    )

    with pytest.raises(
        WFSClientError,
        match="pagination exceeded the safety limit",
    ):
        client.fetch_features()

    assert len(requested_params) == 2
