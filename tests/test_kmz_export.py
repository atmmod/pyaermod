"""Tests for the hand-rolled KMZ exporter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import pytest

from pyaermod import PointSource
from pyaermod.kmz_export import ContourPolygon, to_kmz

_KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


def _open_kml(path):
    """Return the parsed KML XML inside a .kmz archive."""
    with zipfile.ZipFile(path) as zf, zf.open("doc.kml") as f:
        return ET.parse(f).getroot()


@dataclass
class FakePolySource:
    """Stand-in for AreaPolySource exposing the .vertices attribute."""
    source_id: str
    vertices: list


class TestSmokeShape:
    def test_minimal_kmz_has_doc_kml(self, tmp_path):
        out = tmp_path / "min.kmz"
        to_kmz(out, title="Empty test")
        with zipfile.ZipFile(out) as zf:
            assert zf.namelist() == ["doc.kml"]
        root = _open_kml(out)
        assert root.tag.endswith("kml")
        # Document name reflects title
        name = root.find(".//k:Document/k:name", _KML_NS)
        assert name is not None and name.text == "Empty test"

    def test_creates_parent_directory(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "x.kmz"
        to_kmz(out)
        assert out.exists()


class TestSources:
    def test_point_source_lonlat_passthrough(self, tmp_path):
        src = PointSource(
            source_id="STK1", x_coord=-71.06, y_coord=42.36,
            stack_height=30.0, stack_temp=400.0, exit_velocity=10.0,
            stack_diameter=2.0, emission_rate=1.0,
        )
        out = tmp_path / "p.kmz"
        to_kmz(out, sources=[src])
        root = _open_kml(out)
        coords = root.find(".//k:Folder/k:Placemark/k:Point/k:coordinates",
                           _KML_NS)
        # No reprojection: x/y kept as-is
        assert coords is not None
        lon, lat, _ = coords.text.split(",")
        assert float(lon) == pytest.approx(-71.06)
        assert float(lat) == pytest.approx(42.36)

    def test_polygon_source(self, tmp_path):
        verts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        src = FakePolySource(source_id="AP1", vertices=verts)
        out = tmp_path / "poly.kmz"
        to_kmz(out, sources=[src])
        root = _open_kml(out)
        coords = root.find(
            ".//k:Polygon//k:LinearRing/k:coordinates", _KML_NS,
        )
        assert coords is not None
        # Ring is auto-closed (5 vertices on output)
        pts = [c for c in coords.text.split() if c]
        assert len(pts) == 5

    def test_unrecognized_source_is_skipped(self, tmp_path):
        @dataclass
        class Mystery:
            source_id: str = "X"
        out = tmp_path / "skip.kmz"
        to_kmz(out, sources=[Mystery()])
        root = _open_kml(out)
        # Sources folder should exist but be empty (no Placemarks)
        pms = root.findall(".//k:Folder[k:name='Sources']/k:Placemark",
                           _KML_NS)
        assert pms == []


class TestReceptors:
    def test_receptors_have_concentration_in_description(self, tmp_path):
        rcv = [(-71.0, 42.3, 0.123), (-71.1, 42.4, 4.56)]
        out = tmp_path / "r.kmz"
        to_kmz(out, receptors=rcv)
        root = _open_kml(out)
        descs = root.findall(
            ".//k:Folder[k:name='Receptors']/k:Placemark/k:description",
            _KML_NS,
        )
        assert len(descs) == 2
        assert "0.123" in descs[0].text
        assert "4.56" in descs[1].text


class TestContours:
    def test_contours_styled_and_sorted_by_level(self, tmp_path):
        contours = [
            ContourPolygon(level=10.0, coordinates=[(0, 0), (1, 0), (1, 1)]),
            ContourPolygon(level=1.0, coordinates=[(0, 0), (2, 0), (2, 2)]),
            ContourPolygon(level=100.0, coordinates=[(0, 0), (3, 0), (3, 3)]),
        ]
        out = tmp_path / "c.kmz"
        to_kmz(out, contours=contours)
        root = _open_kml(out)
        # Three Placemarks under Contours folder
        names = [pm.find("k:name", _KML_NS).text for pm in root.findall(
            ".//k:Folder[k:name='Contours']/k:Placemark", _KML_NS,
        )]
        # Sorted by level ascending
        assert names == ["1", "10", "100"]


class TestUTMReprojection:
    def test_lonlat_passthrough_when_no_zone(self, tmp_path):
        rcv = [(-71.0, 42.3, 1.0)]
        out = tmp_path / "p.kmz"
        to_kmz(out, receptors=rcv)
        root = _open_kml(out)
        coords = root.find(".//k:Folder[k:name='Receptors']"
                           "/k:Placemark/k:Point/k:coordinates", _KML_NS)
        lon, lat, _ = coords.text.split(",")
        assert float(lon) == pytest.approx(-71.0)
        assert float(lat) == pytest.approx(42.3)

    def test_utm_reprojection_when_pyproj_available(self, tmp_path):
        pytest.importorskip("pyproj")
        # UTM zone 19N point near Boston: ~327000, 4690000 -> ~-71.06, 42.35
        rcv = [(327000.0, 4690000.0, 1.0)]
        out = tmp_path / "u.kmz"
        to_kmz(out, receptors=rcv, utm_zone=19, northern_hemisphere=True)
        root = _open_kml(out)
        coords = root.find(".//k:Folder[k:name='Receptors']"
                           "/k:Placemark/k:Point/k:coordinates", _KML_NS)
        lon, lat, _ = coords.text.split(",")
        # Loose tolerance — anywhere in metro Boston is fine
        assert -71.5 < float(lon) < -70.5
        assert 42.0 < float(lat) < 42.7


class TestKmzStructure:
    def test_zip_contains_only_doc_kml(self, tmp_path):
        out = tmp_path / "z.kmz"
        to_kmz(out)
        with zipfile.ZipFile(out) as zf:
            files = zf.namelist()
        assert files == ["doc.kml"]

    def test_kml_namespace_is_ogc(self, tmp_path):
        out = tmp_path / "ns.kmz"
        to_kmz(out)
        with zipfile.ZipFile(out) as zf:
            text = zf.read("doc.kml").decode("utf-8")
        assert "http://www.opengis.net/kml/2.2" in text

    def test_palette_cycles_when_more_contours_than_colors(self, tmp_path):
        contours = [
            ContourPolygon(level=float(i), coordinates=[(0, 0), (1, 0)])
            for i in range(8)
        ]
        # default palette is 6 entries
        out = tmp_path / "p.kmz"
        to_kmz(out, contours=contours)
        # Should not raise
        assert out.exists()
