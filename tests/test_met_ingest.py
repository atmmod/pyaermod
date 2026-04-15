"""Tests for the met_ingest module (ASOS 1-min, ISD, IGRA, MMIF)."""

from __future__ import annotations

import gzip
import io
import math
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from pyaermod.met_ingest import (
    ASOS1MinRecord,
    IGRAFetcher,
    IGRASounding,
    ISDFetcher,
    ISDStationId,
    MMIFConfig,
    aggregate_1min_to_hourly,
    parse_asos_1min_file,
    parse_asos_1min_line,
    parse_igra_v2,
)


# ---------------------------------------------------------------------------
# ASOS 1-minute
# ---------------------------------------------------------------------------

class TestParseASOSLine:
    def test_parses_valid_line(self):
        line = "64010 KIAD 20200115 1423    extra    180 005KT"
        rec = parse_asos_1min_line(line)
        assert rec is not None
        assert rec.wban == "64010"
        assert rec.call_sign == "KIAD"
        assert rec.year == 2020 and rec.month == 1
        assert rec.day == 15 and rec.hour == 14 and rec.minute == 23
        assert rec.wind_dir_deg == 180.0
        # 5 knots -> m/s
        assert rec.wind_speed_ms == pytest.approx(5 * 0.51444)
        assert not rec.is_calm and not rec.is_variable

    def test_calm_record(self):
        line = "12345 KABC 20200101 0000    junk    000 000KT"
        rec = parse_asos_1min_line(line)
        assert rec is not None and rec.is_calm
        assert rec.wind_dir_deg is None and rec.wind_speed_ms is None

    def test_variable_record(self):
        line = "12345 KABC 20200101 0000    junk    990 003KT"
        rec = parse_asos_1min_line(line)
        assert rec is not None and rec.is_variable
        assert rec.wind_dir_deg is None

    def test_unparseable_returns_none(self):
        assert parse_asos_1min_line("garbage line") is None
        assert parse_asos_1min_line("") is None


class TestAggregate1MinToHourly:
    def _rec(self, y, mo, d, h, mi, wd, ws_ms, **kw):
        return ASOS1MinRecord(
            wban="12345", call_sign="KABC",
            year=y, month=mo, day=d, hour=h, minute=mi,
            wind_dir_deg=wd, wind_speed_ms=ws_ms,
            **kw,
        )

    def test_steady_wind_preserved(self):
        # 5 records all 180/5 m/s -> hourly 180/5
        recs = [self._rec(2020, 1, 1, 0, mi, 180.0, 5.0) for mi in range(5)]
        out = aggregate_1min_to_hourly(recs)
        assert len(out) == 1
        row = out[0]
        assert row["flag"] == "OK"
        assert row["ws"] == pytest.approx(5.0, abs=1e-3)
        assert row["wd"] == pytest.approx(180.0, abs=0.5)
        assert row["n_obs"] == 5

    def test_all_calm_hour_flagged_calm(self):
        recs = [self._rec(2020, 1, 1, 0, mi, None, None, is_calm=True) for mi in range(3)]
        out = aggregate_1min_to_hourly(recs)
        assert out[0]["flag"] == "CALM"
        assert out[0]["ws"] == 0.0

    def test_insufficient_obs_flagged(self):
        recs = [self._rec(2020, 1, 1, 0, 0, 180.0, 5.0)]  # only one valid obs
        out = aggregate_1min_to_hourly(recs)
        assert out[0]["flag"] == "INSUF"

    def test_vector_average_opposing(self):
        # 180 + 360 at equal speed -> near-zero resultant
        recs = [
            self._rec(2020, 1, 1, 0, 0, 180.0, 5.0),
            self._rec(2020, 1, 1, 0, 1, 360.0, 5.0),
        ]
        out = aggregate_1min_to_hourly(recs)
        assert out[0]["flag"] == "OK"
        assert out[0]["ws"] < 0.01

    def test_multiple_hours_sorted(self):
        recs = [
            self._rec(2020, 1, 1, 2, 0, 90.0, 3.0),
            self._rec(2020, 1, 1, 2, 1, 90.0, 3.0),
            self._rec(2020, 1, 1, 1, 0, 180.0, 5.0),
            self._rec(2020, 1, 1, 1, 1, 180.0, 5.0),
        ]
        out = aggregate_1min_to_hourly(recs)
        assert [(r["hour"]) for r in out] == [1, 2]


class TestParseASOSFile:
    def test_parses_plain_and_gz(self, tmp_path):
        text = (
            "64010 KIAD 20200115 1423    extra    180 005KT\n"
            "64010 KIAD 20200115 1424    extra    180 005KT\n"
            "garbage\n"
        )
        plain = tmp_path / "asos.txt"
        plain.write_text(text)
        recs = parse_asos_1min_file(plain)
        assert len(recs) == 2

        gz = tmp_path / "asos.txt.gz"
        with gzip.open(gz, "wt") as f:
            f.write(text)
        recs_gz = parse_asos_1min_file(gz)
        assert len(recs_gz) == 2


# ---------------------------------------------------------------------------
# ISD fetcher
# ---------------------------------------------------------------------------

class TestISDStationId:
    def test_valid(self):
        s = ISDStationId("723010", "13880")
        assert s.usaf == "723010" and s.wban == "13880"

    def test_invalid_usaf_raises(self):
        with pytest.raises(ValueError, match="USAF"):
            ISDStationId("abc123", "13880")

    def test_invalid_wban_raises(self):
        with pytest.raises(ValueError, match="WBAN"):
            ISDStationId("723010", "123")


class TestISDFetcher:
    def _isd_lite_bytes(self):
        # Two hourly records; -9999 is missing
        text = (
            "2020 01 01 00   -50  -70 10130 180  50 0 -9999 -9999\n"
            "2020 01 01 01 -9999 -9999 10131 -9999 -9999 0 0 0\n"
        )
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(text.encode("ascii"))
        return buf.getvalue()

    def test_read_hourly_parses(self, tmp_path):
        fetcher = ISDFetcher(cache_dir=tmp_path)
        with patch("pyaermod.met_ingest.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.content = self._isd_lite_bytes()
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            rows = fetcher.read_hourly(ISDStationId("723010", "13880"), 2020)
        assert len(rows) == 2
        assert rows[0]["temp_c"] == pytest.approx(-5.0)
        assert rows[0]["wind_speed_ms"] == pytest.approx(5.0)
        assert rows[1]["temp_c"] is None
        assert rows[1]["wind_dir"] is None

    def test_uses_cache_on_repeat(self, tmp_path):
        fetcher = ISDFetcher(cache_dir=tmp_path)
        with patch("pyaermod.met_ingest.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.content = self._isd_lite_bytes()
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            fetcher.fetch(ISDStationId("723010", "13880"), 2020)
            fetcher.fetch(ISDStationId("723010", "13880"), 2020)
            assert mock_req.get.call_count == 1  # second hit cache

    def test_full_isd_read_hourly_not_implemented(self):
        fetcher = ISDFetcher(use_lite=False)
        with patch.object(fetcher, "fetch", return_value=b""):
            with pytest.raises(NotImplementedError):
                fetcher.read_hourly(ISDStationId("723010", "13880"), 2020)


# ---------------------------------------------------------------------------
# IGRA
# ---------------------------------------------------------------------------

_IGRA_SAMPLE = (
    # header: ID YEAR MONTH DAY HOUR RELTIME NUMLEV P_SRC NP_SRC LAT LON
    "#USM00072469 2020 01 01 00 2359    2 ncdc6210 ncdc6210 -9999 -9999\n"
    "21 1  -9999 100000B -9999B    150A -9999 -9999   170   55\n"
    "20 1  -9999  85000B -9999B    100A -9999 -9999   200   80\n"
)


class TestParseIGRA:
    def test_parses_sounding(self):
        soundings = parse_igra_v2(_IGRA_SAMPLE)
        assert len(soundings) == 1
        s = soundings[0]
        assert s.station_id == "USM00072469"
        assert s.year == 2020 and s.num_levels == 2
        assert len(s.levels) == 2
        lvl = s.levels[0]
        assert lvl["pressure_pa"] == 100000
        assert lvl["temp_c"] == pytest.approx(15.0)
        assert lvl["wind_dir"] == 170.0
        assert lvl["wind_speed_ms"] == 5.5

    def test_empty_text_returns_empty(self):
        assert parse_igra_v2("") == []


class TestIGRAFetcher:
    def test_fetch_from_zip(self, tmp_path):
        fetcher = IGRAFetcher(cache_dir=tmp_path)
        # Build a fake zip containing the IGRA text
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("USM00072469-data.txt", _IGRA_SAMPLE)
        with patch("pyaermod.met_ingest.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.content = buf.getvalue()
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            soundings = fetcher.read_soundings("USM00072469")
        assert len(soundings) == 1 and soundings[0].num_levels == 2

    def test_cache_hit_skips_network(self, tmp_path):
        fetcher = IGRAFetcher(cache_dir=tmp_path)
        (tmp_path / "USM00072469-data.txt").write_text(_IGRA_SAMPLE, encoding="latin-1")
        with patch("pyaermod.met_ingest.requests") as mock_req:
            soundings = fetcher.read_soundings("USM00072469")
            mock_req.get.assert_not_called()
        assert len(soundings) == 1


# ---------------------------------------------------------------------------
# MMIF
# ---------------------------------------------------------------------------

class TestMMIFConfig:
    def test_basic(self):
        cfg = MMIFConfig(surface_file="wrf.sfc", profile_file="wrf.pfl")
        kw = cfg.to_meteorology()
        assert kw["surface_file"] == "wrf.sfc"
        assert kw["profile_file"] == "wrf.pfl"
        assert kw["surface_station_id"] == "MMIF"

    def test_rejects_empty_paths(self):
        with pytest.raises(ValueError):
            MMIFConfig(surface_file="", profile_file="x.pfl")
        with pytest.raises(ValueError):
            MMIFConfig(surface_file="x.sfc", profile_file="")
