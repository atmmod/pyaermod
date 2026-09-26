"""Tests for the AERSCREEN configuration: prompt answers and restart file.

The prompt order and the header layout are pinned here from the
Fortran (``AERSCREEN.FOR`` subroutines ``initprompts``, ``stacks``,
``downwash``, ``getDEMs``, ``metdata``, ``fuminp``, ``setdebug``,
``getoutfil``, ``validate`` and ``makeinput``); the EPA decks in
``test_aerscreen_known_answers.py`` pin the same layout from the other
side, and ``test_real_aerscreen.py`` runs both through the binary.
"""

from __future__ import annotations

import copy
import dataclasses
import pickle

import pytest

from pyaermod import AERSCREENConfig, AERSCREENSourceType
from pyaermod.aerscreen import (
    _REMOVED_FIELDS,
    _RENAMED_FIELDS,
    DISCRETE_RECEPTOR_FILE,
    _e,
    _f,
    _i,
)


def point(**overrides):
    kw = dict(
        title="Stack screening",
        source_type=AERSCREENSourceType.POINT,
        emission_rate=10.0,
        stack_height=30.0,
        stack_diameter=2.0,
        stack_temp=425.0,
        exit_velocity=15.0,
        albedo=0.16, bowen_ratio=0.8, roughness_length=0.1,
    )
    kw.update(overrides)
    return AERSCREENConfig(**kw)


def volume(**overrides):
    kw = dict(
        title="vol", source_type=AERSCREENSourceType.VOLUME, emission_rate=0.5,
        stack_height=5.0, lateral_dimension=10.0, vertical_dimension=4.0,
        land_use=6, climate=2,
    )
    kw.update(overrides)
    return AERSCREENConfig(**kw)


# ---------------------------------------------------------------------------
# Source types
# ---------------------------------------------------------------------------

class TestSourceType:
    def test_the_seven_aerscreen_types_and_their_prompt_letters(self):
        letters = {t: t.prompt_letter for t in AERSCREENSourceType}
        assert letters == {
            AERSCREENSourceType.POINT: "P", AERSCREENSourceType.VOLUME: "V",
            AERSCREENSourceType.AREA: "A", AERSCREENSourceType.AREACIRC: "C",
            AERSCREENSourceType.FLARE: "F", AERSCREENSourceType.POINTCAP: "S",
            AERSCREENSourceType.POINTHOR: "H",
        }

    def test_old_names_are_aliases_of_the_real_keywords(self):
        assert AERSCREENSourceType.CAPPED is AERSCREENSourceType.POINTCAP
        assert AERSCREENSourceType.HORIZONTAL is AERSCREENSourceType.POINTHOR
        assert AERSCREENSourceType.CAPPED.value == "POINTCAP"

    def test_string_source_type_coerced(self):
        assert point(source_type="pointcap").source_type is AERSCREENSourceType.POINTCAP
        with pytest.raises(ValueError, match="source_type"):
            point(source_type="chimney")

    def test_header_keywords(self):
        assert AERSCREENSourceType.POINT.header_keyword == "STACK DATA"
        assert AERSCREENSourceType.POINTHOR.header_keyword == "POINTHOR DATA"
        assert AERSCREENSourceType.AREACIRC.header_keyword == "AREACIRC DATA"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_point(self):
        cfg = point()
        assert cfg.surface_code == 0 and not cfg.terrain and cfg.fumigation_allowed

    @pytest.mark.parametrize("field, value, match", [
        ("emission_rate", 0.0, "emission_rate"),
        ("stack_height", None, "stack_height"),
        ("stack_diameter", None, "stack_diameter"),
        ("exit_velocity", -1.0, "exit_velocity"),
        ("ambient_distance", 0.0, "ambient_distance"),
        ("probe_distance", -5.0, "probe_distance"),
        ("flagpole_height", -1.0, "flagpole_height"),
        ("min_wind_speed", 0.0, "min_wind_speed"),
        ("anemometer_height", -1.0, "anemometer_height"),
        ("albedo", 1.5, "albedo"),
        ("roughness_length", -0.1, "roughness_length"),
        ("output_file", "run.txt", r"\.out"),
        ("datum", "WGS84", "datum"),
        ("dem_type", "SRTM", "dem_type"),
        ("utm_zone", 0, "utm_zone"),
    ])
    def test_bad_scalar(self, field, value, match):
        with pytest.raises(ValueError, match=match):
            point(**{field: value})

    def test_temperature_order(self):
        with pytest.raises(ValueError, match="temp_min_k"):
            point(temp_min_k=320.0, temp_max_k=310.0)

    def test_flare_requires_heat_release(self):
        with pytest.raises(ValueError, match="flare_heat_release"):
            AERSCREENConfig(title="f", source_type="FLARE", emission_rate=1.0,
                            stack_height=20.0, albedo=0.2, bowen_ratio=1.0,
                            roughness_length=0.1)
        with pytest.raises(ValueError, match="flare_heat_loss"):
            AERSCREENConfig(title="f", source_type="FLARE", emission_rate=1.0,
                            stack_height=20.0, flare_heat_release=1e6,
                            flare_heat_loss=1.5, albedo=0.2, bowen_ratio=1.0,
                            roughness_length=0.1)

    def test_volume_requires_both_dimensions(self):
        with pytest.raises(ValueError, match="vertical_dimension"):
            volume(vertical_dimension=None)

    def test_area_dimensions_and_swap(self):
        with pytest.raises(ValueError, match="area_width"):
            AERSCREENConfig(title="a", source_type="AREA", emission_rate=1.0,
                            stack_height=0.0, area_length=50.0, land_use=6)
        cfg = AERSCREENConfig(title="a", source_type="AREA", emission_rate=1.0,
                              stack_height=0.0, area_length=50.0, area_width=100.0,
                              land_use=6)
        # AERSCREEN swaps the long and short sides itself and says so.
        assert (cfg.area_length, cfg.area_width) == (100.0, 50.0)
        assert cfg.vertical_dimension == 0.0

    def test_areacirc_requires_radius(self):
        with pytest.raises(ValueError, match="radius"):
            AERSCREENConfig(title="c", source_type="AREACIRC", emission_rate=1.0,
                            stack_height=0.0, land_use=6)

    def test_urban_needs_population_above_100(self):
        with pytest.raises(ValueError, match="population"):
            point(urban=True)
        with pytest.raises(ValueError, match="population"):
            point(urban=True, population=100)
        assert point(urban=True, population=250_000).population == 250_000

    def test_no2_chemistry_requirements(self):
        with pytest.raises(ValueError, match="no2_method"):
            point(no2_method="ARM2", no2_stack_ratio=0.5, ozone_concentration=40)
        with pytest.raises(ValueError, match="no2_stack_ratio"):
            point(no2_method="olm", ozone_concentration=40)
        with pytest.raises(ValueError, match="ozone_concentration"):
            point(no2_method="OLM", no2_stack_ratio=0.5)
        with pytest.raises(ValueError, match="ozone_units"):
            point(no2_method="OLM", no2_stack_ratio=0.5, ozone_concentration=40,
                  ozone_units="ppt")
        cfg = point(no2_method="pvmrm", no2_stack_ratio=0.5, ozone_concentration=40,
                    ozone_units="ppb")
        assert (cfg.no2_method, cfg.ozone_units) == ("PVMRM", "PPB")

    def test_downwash_requires_building_or_bpip_file(self):
        with pytest.raises(ValueError, match="building_height"):
            point(downwash=True)
        with pytest.raises(ValueError, match="cannot exceed"):
            point(downwash=True, building_height=10, building_length=20,
                  building_width=30, building_angle=0, stack_direction=90,
                  stack_distance=5)
        with pytest.raises(ValueError, match="building_angle"):
            point(downwash=True, building_height=10, building_length=30,
                  building_width=20, building_angle=180, stack_direction=90,
                  stack_distance=5)
        with pytest.raises(ValueError, match="stack_direction"):
            point(downwash=True, building_height=10, building_length=30,
                  building_width=20, building_angle=10, stack_direction=361,
                  stack_distance=5)
        assert point(downwash=True, bpip_file="building.inp").downwash

    def test_downwash_only_for_elevated_releases(self):
        with pytest.raises(ValueError, match="no building downwash"):
            volume(downwash=True, bpip_file="b.inp")

    def test_terrain_requires_coordinates(self):
        with pytest.raises(ValueError, match="lat and lon"):
            point(terrain=True, dem_files=["a.tif"])
        with pytest.raises(ValueError, match="lat must"):
            point(terrain=True, lat=95.0, lon=-70.0, dem_files=["a.tif"])
        cfg = point(terrain=True, utm_easting=500000.0, utm_northing=4000000.0,
                    utm_zone=17, dem_files=["a.tif"])
        assert cfg.datum == "NAD83" and cfg.aermap_elevation

    def test_terrain_not_for_rectangular_area(self):
        with pytest.raises(ValueError, match="AREA"):
            AERSCREENConfig(title="a", source_type="AREA", emission_rate=1.0,
                            stack_height=0.0, area_length=50.0, area_width=20.0,
                            land_use=6, terrain=True, lat=40.0, lon=-80.0)

    def test_aermap_elevation_needs_terrain(self):
        with pytest.raises(ValueError, match="aermap_elevation"):
            point(aermap_elevation=True)
        assert point().aermap_elevation is False

    def test_discrete_receptors(self):
        with pytest.raises(ValueError, match="at most 10"):
            point(discrete_receptors=range(1, 12))
        with pytest.raises(ValueError, match="> 0"):
            point(discrete_receptors=[100.0, 0.0])
        cfg = point(discrete_receptors=[100, 250])
        assert cfg.discrete_receptors == (100.0, 250.0)
        assert cfg.discrete_receptor_filename == DISCRETE_RECEPTOR_FILE
        assert point(discrete_receptor_file="/x/recs.txt").discrete_receptor_filename == "recs.txt"
        assert point().discrete_receptor_filename is None

    def test_exactly_one_surface_option(self):
        with pytest.raises(ValueError, match="exactly one"):
            point(albedo=None, bowen_ratio=None, roughness_length=None)
        with pytest.raises(ValueError, match="exactly one"):
            point(land_use=3)
        with pytest.raises(ValueError, match="all of"):
            point(bowen_ratio=None)
        with pytest.raises(ValueError, match="land_use"):
            volume(land_use=9)
        with pytest.raises(ValueError, match="climate"):
            volume(climate=4)
        assert volume(climate=None).climate == 1
        assert point(albedo=None, bowen_ratio=None, roughness_length=None,
                     surface_file="sc.out").surface_code == 9

    def test_fumigation_eligibility(self):
        with pytest.raises(ValueError, match="at least 10 m"):
            volume(fumigation=True)
        with pytest.raises(ValueError, match="at least 10 m"):
            point(stack_height=9.0, fumigation=True)
        assert point(fumigation=True).fumigation
        # A 5 m flare tip with a big heat release is well above 10 m.
        flare = AERSCREENConfig(title="f", source_type="FLARE", emission_rate=1.0,
                                stack_height=5.0, flare_heat_release=1e7,
                                land_use=6, fumigation=True)
        assert flare.effective_release_height > 10.0

    def test_shoreline_parameters(self):
        with pytest.raises(ValueError, match="shoreline_distance"):
            point(shoreline_fumigation=True)
        with pytest.raises(ValueError, match="shoreline_distance"):
            point(shoreline_fumigation=True, shoreline_distance=3500.0)
        with pytest.raises(ValueError, match="shoreline_direction"):
            point(shoreline_fumigation=True, shoreline_distance=500.0,
                  shoreline_direction=400.0)

    def test_run_aermod_false_needs_fumigation(self):
        with pytest.raises(ValueError, match="run_aermod=False"):
            point(run_aermod=False)
        assert not point(run_aermod=False, fumigation=True).run_aermod


# ---------------------------------------------------------------------------
# Old field names
# ---------------------------------------------------------------------------

class TestLegacyFieldNames:
    @pytest.mark.parametrize("old", sorted(_RENAMED_FIELDS))
    def test_renamed_field_names_its_replacement(self, old):
        with pytest.raises(TypeError) as exc:
            point(**{old: 1.0})
        assert old in str(exc.value)
        assert _RENAMED_FIELDS[old] in str(exc.value)

    @pytest.mark.parametrize("old", sorted(_REMOVED_FIELDS))
    def test_removed_field_says_why(self, old):
        with pytest.raises(TypeError) as exc:
            point(**{old: ["x"]})
        assert old in str(exc.value)
        assert _REMOVED_FIELDS[old] in str(exc.value)

    def test_the_tables_cover_every_dropped_field(self):
        """Every field of the previous release that no longer exists."""
        previous = {
            "title", "source_type", "emission_rate", "stack_height",
            "stack_diameter", "stack_temp", "exit_velocity", "flare_heat_release",
            "area_length", "area_width", "initial_sigma_z", "lateral_dim",
            "vertical_dim", "urban", "population", "dominant_landuse",
            "temp_min_k", "temp_max_k", "anemometer_height", "use_adju",
            "downwash", "building_height", "building_length", "building_width",
            "building_angle", "terrain", "lat", "lon", "terrain_file",
            "fumigation", "distances", "extra_lines",
        }
        current = {f.name for f in dataclasses.fields(AERSCREENConfig)}
        dropped = previous - current
        assert dropped == set(_RENAMED_FIELDS) | set(_REMOVED_FIELDS)
        assert set(_RENAMED_FIELDS.values()) <= current
        assert not set(_RENAMED_FIELDS) & set(_REMOVED_FIELDS)

    def test_wrapped_init_still_behaves_as_a_dataclass(self):
        cfg = point()
        assert dataclasses.replace(cfg, emission_rate=2.0).emission_rate == 2.0
        with pytest.raises(TypeError, match="discrete_receptors"):
            dataclasses.replace(cfg, distances=[1.0])
        assert dataclasses.asdict(cfg)["stack_height"] == 30.0
        assert copy.deepcopy(cfg) == cfg
        assert pickle.loads(pickle.dumps(cfg)) == cfg


# ---------------------------------------------------------------------------
# Prompt answers
# ---------------------------------------------------------------------------

POINT_ANSWERS = [
    "Stack screening", "M", "P",           # initprompts
    "10", "30", "2", "425", "1", "15",     # stacks: rate, height, diameter, temp, velocity option, velocity
    "R", "", "1",                          # rural, default ambient distance, no NO2 chemistry
    "N",                                   # downwash
    "N", "", "N", "N", "",                 # getDEMs: terrain, probe, discrete, flagpole, elevation
    "", "", "", "1", "0.16", "0.8", "0.1", "N",   # metdata: temps, wind, anemometer, user SC, adjust u*
    "N", "N",                              # fuminp: inversion, shoreline
    "",                                    # debug off
    "",                                    # default output file
    "",                                    # validate: <Enter> starts the run
]


class TestPromptAnswers:
    def test_minimal_point_source(self):
        assert point().to_stdin_answers() == POINT_ANSWERS

    def test_answers_are_never_none_and_fit_the_prompt_buffer(self):
        a = point(urban=True, population=1.5e6, ambient_distance=12.5).to_stdin_answers()
        assert all(isinstance(x, str) for x in a)
        assert all(len(x) <= 15 for x in a if x not in (point().title,))

    def test_urban_and_ambient_distance_and_no2(self):
        cfg = point(urban=True, population=250_000, ambient_distance=25.0,
                    no2_method="OLM", no2_stack_ratio=0.2, ozone_concentration=40,
                    ozone_units="PPB")
        a = cfg.to_stdin_answers()
        i = a.index("15") + 1
        assert a[i:i + 8] == ["U", "250000", "25", "2", "0.2", "3", "40", "N"]
        pv = point(no2_method="PVMRM", no2_stack_ratio=0.2, ozone_concentration=0.04,
                   ozone_units="PPM").to_stdin_answers()
        j = pv.index("R") + 2
        assert pv[j:j + 4] == ["3", "0.2", "2", "0.04"]

    def test_ambient_temperature_answer(self):
        assert "0" in point(stack_temp=None).to_stdin_answers()[6]
        assert point(stack_temp=-20.0).to_stdin_answers()[6] == "-20"

    def test_single_building(self):
        cfg = point(downwash=True, building_height=25.0, building_length=50.0,
                    building_width=30.0, building_angle=45.0, stack_direction=90.0,
                    stack_distance=20.0)
        a = cfg.to_stdin_answers()
        i = a.index("1", 9) + 1           # after the NO2 option
        assert a[i:i + 8] == ["Y", "N", "25", "50", "30", "45", "90", "20"]

    def test_bpip_file(self):
        a = point(downwash=True, bpip_file="/site/my building.inp").to_stdin_answers()
        i = a.index("Y")
        assert a[i:i + 3] == ["Y", "Y", '"my building.inp"']

    def test_volume_skips_downwash_and_fumigation(self):
        a = volume().to_stdin_answers()
        assert a[:3] == ["vol", "M", "V"]
        assert a[3:7] == ["0.5", "5", "10", "4"]
        # rural, ambient, NO2, then straight to terrain
        assert a[7:11] == ["R", "", "1", "N"]
        assert a[-3:] == ["", "", ""]
        assert "2" in a and a[a.index("2") + 1:a.index("2") + 3] == ["6", "2"]
        # Against the point source: two fewer geometry answers, no downwash
        # question, two fewer surface answers (a table code and a climate
        # code instead of three values) and no fumigation questions.
        assert len(a) == len(POINT_ANSWERS) - 2 - 1 - 1 - 2

    def test_area_has_no_terrain_prompt(self):
        cfg = AERSCREENConfig(title="a", source_type="AREA", emission_rate=1.0,
                              stack_height=2.0, area_length=100.0, area_width=50.0,
                              vertical_dimension=1.0, land_use=6)
        a = cfg.to_stdin_answers()
        assert a[3:8] == ["1", "2", "100", "50", "1"]
        assert a[8:11] == ["R", "", "1"]
        assert a[11] == ""                # probe distance: no terrain question first

    def test_areacirc_and_flare_geometry(self):
        c = AERSCREENConfig(title="c", source_type="AREACIRC", emission_rate=1.0,
                            stack_height=0.0, radius=50.0, land_use=6)
        assert c.to_stdin_answers()[3:6] == ["1", "0", "50"]
        f = AERSCREENConfig(title="f", source_type="FLARE", emission_rate=1.0,
                            stack_height=20.0, flare_heat_release=1e7,
                            flare_heat_loss=0.45, land_use=6)
        assert f.to_stdin_answers()[3:7] == ["1", "20", "10000000", "0.45"]
        tiny = AERSCREENConfig(title="f", source_type="FLARE", emission_rate=1.5e-6,
                               stack_height=20.0, flare_heat_release=1e7, land_use=6)
        assert tiny.to_stdin_answers()[3] == "1.500000E-06"

    def test_terrain_prompts(self):
        cfg = point(terrain=True, utm_easting=535145.7, utm_northing=3658512.5,
                    utm_zone=17, datum="NAD27", dem_files=["x.tif"],
                    probe_distance=8000.0, flagpole_height=1.5,
                    discrete_receptors=[100, 200], source_elevation=25.0)
        a = cfg.to_stdin_answers()
        i = a.index("Y", a.index("N") )    # terrain Y
        assert a[i:i + 12] == [
            "Y", "8000", "Y", DISCRETE_RECEPTOR_FILE, "Y", "1.5", "25",
            "UTM", "535145.7", "3658512.5", "17", "1",
        ]
        latlon = point(terrain=True, lat=35.89, lon=-78.78, dem_files=["x.tif"])
        b = latlon.to_stdin_answers()
        assert b[b.index("LATLON"):b.index("LATLON") + 4] == ["LATLON", "35.89", "-78.78", "4"]
        assert b[b.index("LATLON") - 1] == ""     # AERMAP-derived elevation

    def test_meteorology_prompts(self):
        a = point(temp_min_k=260.0, temp_max_k=305.0, min_wind_speed=1.0,
                  anemometer_height=12.0, use_adju=True).to_stdin_answers()
        i = a.index("260")
        assert a[i:i + 9] == ["260", "305", "1", "12", "1", "0.16", "0.8", "0.1", "Y"]
        b = point(albedo=None, bowen_ratio=None, roughness_length=None,
                  surface_file="/met/season_3.out").to_stdin_answers()
        assert b[b.index("3"):b.index("3") + 2] == ["3", "season_3.out"]

    def test_fumigation_prompts(self):
        a = point(fumigation=True, shoreline_fumigation=True, shoreline_distance=500.0,
                  shoreline_direction=30.0).to_stdin_answers()
        assert a[-6:] == ["Y", "Y", "500", "30", "", "", ""][:6] or a[-7:] == [
            "Y", "Y", "500", "30", "", "", ""]
        b = point(shoreline_fumigation=True, shoreline_distance=500.0).to_stdin_answers()
        assert b[-7:] == ["N", "Y", "500", "", "", "", ""]

    def test_run_aermod_off_goes_through_the_fumigation_menu(self):
        both = point(fumigation=True, shoreline_fumigation=True, shoreline_distance=1.0,
                     run_aermod=False).to_stdin_answers()
        assert both[-4:] == ["5", "5", "", ""]
        inversion = point(fumigation=True, run_aermod=False).to_stdin_answers()
        assert inversion[-4:] == ["5", "3", "", ""]
        shore = point(shoreline_fumigation=True, shoreline_distance=1.0,
                      run_aermod=False).to_stdin_answers()
        assert shore[-4:] == ["5", "5", "", ""]

    def test_debug_and_output_file(self):
        a = point(debug=True, output_file="site A.out").to_stdin_answers()
        assert a[-3:] == ["Y", '"site A.out"', ""]
        assert point(output_file="aerscreen.out").to_stdin_answers()[-2] == ""


# ---------------------------------------------------------------------------
# Restart file
# ---------------------------------------------------------------------------

class TestFortranEditing:
    def test_e_editing(self):
        assert _e(1.0, 12, 4) == "  0.1000E+01"
        assert _e(0.9954, 12, 4) == "  0.9954E+00"
        assert _e(1.0e7, 12, 4) == "  0.1000E+08"
        assert _e(0.0, 12, 4) == "  0.0000E+00"
        assert _e(0.99999, 12, 4) == "  0.1000E+01"
        assert _e(-2.5e-3, 12, 4) == " -0.2500E-02"
        assert _e(1.0, 4, 4) == "****"

    def test_f_editing(self):
        assert _f(457646.86, 10, 0) == "   457647."
        assert _f(61.0, 10, 4) == "   61.0000"
        assert _f(-0.0, 10, 4) == "    0.0000"
        assert _f(0.5, 6, 1) == "   0.5"
        assert _f(123456.0, 4, 1) == "****"

    def test_i_editing(self):
        assert _i(9, 5) == "    9"
        assert _i(123456, 5) == "*****"


class TestRestartFile:
    def test_point_header_lines(self):
        deck = point().to_aerscreen_input().split("\n")
        assert deck[0] == ("** STACK DATA         Rate    Height     Temp.  Velocity"
                           "     Diam.     Flow")
        # flow = 15 * 2**2 / 0.0006009 ACFM
        assert deck[1] == "**              0.1000E+02   30.0000  425.0000   15.0000    2.0000    99850."
        assert deck[3] == ("** BUILDING DATA   BPIP    Height  Max dim.  Min dim."
                           "   Orient.   Direct.    Offset")
        assert deck[4] == "**                  N      0.0000    0.0000    0.0000    0.0000    0.0000    0.0000"
        assert deck[7] == ('**               250.00  310.00   0.5   10.000    0    0'
                           '   0.1600   0.8000   0.1000  "NA"')
        assert deck[9] == "** ADJUST U*      N"
        assert deck[12] == ("**                   N            0.0         0.0     0     0"
                            "       5000.0           0.00         N")
        assert deck[15] == '**                      N        "NA"'
        assert deck[18] == "**                      M     R            0.           1.000       N         0.00"
        assert deck[21] == "**                         N                  N         0.00      0.0     Y"
        assert deck[24] == "**                     N"
        assert deck[26] == '** OUTPUT FILE "AERSCREEN.OUT"'
        assert deck[28:] == ["CO STARTING", "   TITLEONE Stack screening",
                             "   MODELOPT CONC SCREEN  FLAT", "   AVERTIME 1",
                             "   POLLUTID OTHER", "   RUNORNOT RUN", "CO FINISHED", ""]

    def test_ambient_temperature_is_zero(self):
        assert "  425.0000" not in point(stack_temp=None).to_aerscreen_input()
        assert "    0.0000   15.0000" in point(stack_temp=None).to_aerscreen_input()

    def test_source_blocks_of_the_other_types(self):
        flare = AERSCREENConfig(title="f", source_type="FLARE", emission_rate=1.0,
                                stack_height=100.0, flare_heat_release=1e7,
                                flare_heat_loss=0.45, land_use=6)
        assert flare.to_aerscreen_input().split("\n")[1] == \
            "**              0.1000E+01  100.0000  0.1000E+08     0.450"
        assert volume().to_aerscreen_input().split("\n")[1] == \
            "**              0.5000E+00    5.0000   10.0000    4.0000"
        area = AERSCREENConfig(title="a", source_type="AREA", emission_rate=0.9954,
                               stack_height=0.9144, area_length=152.4, area_width=76.2,
                               vertical_dimension=0.09, land_use=6)
        assert area.to_aerscreen_input().split("\n")[1] == \
            "**              0.9954E+00    0.9144  152.4000   76.2000     0.0       0.09"
        circ = AERSCREENConfig(title="c", source_type="AREACIRC", emission_rate=1.0,
                               stack_height=0.0, radius=50.0, land_use=6)
        assert circ.to_aerscreen_input().split("\n")[1] == \
            "**              0.1000E+01    0.0000   50.0000      20        0.00"

    def test_modelopt_spacing_follows_makeinput(self):
        def opt(cfg):
            return next(ln for ln in cfg.to_aerscreen_input().split("\n")
                        if "MODELOPT" in ln)
        assert opt(point()) == "   MODELOPT CONC SCREEN  FLAT"
        assert opt(point(terrain=True, lat=40.0, lon=-80.0)) == "   MODELOPT CONC SCREEN"
        assert opt(point(no2_method="OLM", no2_stack_ratio=0.1, ozone_concentration=40)
                   ) == "   MODELOPT CONC SCREEN  FLAT  OLM"
        area = AERSCREENConfig(title="a", source_type="AREA", emission_rate=1.0,
                               stack_height=0.0, area_length=100.0, area_width=50.0,
                               land_use=6)
        assert opt(area) == "   MODELOPT CONC SCREEN  FLAT FASTAREA"

    def test_co_pathway_extras(self):
        cfg = point(urban=True, population=100000, flagpole_height=1.5,
                    no2_method="OLM", no2_stack_ratio=0.1, ozone_concentration=40.0,
                    downwash=True, bpip_file="/b/BUILDING.INP")
        co = cfg.to_aerscreen_input().split("CO STARTING\n")[1].split("\n")
        assert co[:9] == [
            "   TITLEONE Stack screening",
            '   TITLETWO "BUILDING.INP"',
            "   MODELOPT CONC SCREEN  FLAT  OLM",
            "   AVERTIME 1",
            "   URBANOPT   100000.",
            "   POLLUTID NO2",
            "   NO2STACK 0.1000",
            "   OZONEVAL     40.0000 PPB",
            "   FLAGPOLE     1.50",
        ]

    def test_terrain_and_receptor_blocks(self):
        cfg = point(terrain=True, utm_easting=535145.7, utm_northing=3658512.5,
                    utm_zone=17, dem_files=["x.tif"], discrete_receptors=[100.0],
                    flagpole_height=2.0, shoreline_fumigation=True,
                    shoreline_distance=500.0, debug=True, use_adju=True)
        deck = cfg.to_aerscreen_input().split("\n")
        assert deck[9] == "** ADJUST U*      Y"
        assert deck[12] == ("**                   Y       535145.7   3658512.5    17     4"
                            "      10000.0           0.00         Y")
        assert deck[15] == f'**                      Y        "{DISCRETE_RECEPTOR_FILE}"'
        assert deck[18].endswith("       Y         2.00")
        assert deck[21] == "**                         N                  Y       500.00     -9.0     Y"
        assert deck[24] == "**                     Y"

    def test_round_trip_is_idempotent(self):
        cfg = point(urban=True, population=100000, downwash=True, building_height=25.0,
                    building_length=50.0, building_width=30.0, building_angle=45.0,
                    stack_direction=90.0, stack_distance=20.0, fumigation=True,
                    discrete_receptors=[100.0, 200.0], output_file="run.out")
        text = cfg.to_aerscreen_input()
        back = AERSCREENConfig.from_aerscreen_input(text)
        assert back.to_aerscreen_input() == text
        assert back.downwash and back.building_height == 25.0
        assert back.urban and back.population == 100000.0
        assert back.discrete_receptor_file == DISCRETE_RECEPTOR_FILE
        assert back.output_file == "run.out" and back.fumigation

    def test_parser_is_list_directed(self):
        """Case, spacing and CRLF do not matter; quoted names may hold spaces."""
        text = point(surface_file="my sc.out", albedo=None, bowen_ratio=None,
                     roughness_length=None).to_aerscreen_input()
        loose = "\r\n".join(
            " ".join(ln.split()) if ln.startswith("**   ") else ln
            for ln in text.lower().split("\n")
        )
        back = AERSCREENConfig.from_aerscreen_input(loose)
        assert back.surface_file == "my sc.out"
        assert back.title == "stack screening"
        assert back.emission_rate == 10.0

    def test_parser_needs_a_source_block(self):
        with pytest.raises(ValueError, match="source data"):
            AERSCREENConfig.from_aerscreen_input("CO STARTING\nCO FINISHED\n")

    def test_staged_input_files(self):
        cfg = point(albedo=None, bowen_ratio=None, roughness_length=None,
                    surface_file="sc.out", discrete_receptor_file="r.txt",
                    downwash=True, bpip_file="b.inp", terrain=True, lat=40.0,
                    lon=-80.0, dem_files=["a.tif", "b.tif"])
        assert cfg.staged_input_files == ["sc.out", "r.txt", "b.inp", "a.tif", "b.tif"]
