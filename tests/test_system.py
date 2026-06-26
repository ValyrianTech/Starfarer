import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.models.system import Body, StarSystem, validate_system_type


def _make_body_dict(biome=None):
    """Helper to create a minimal dict with required fields for Body.from_dict."""
    return {
        "id": "body_001",
        "name": "Test Planet",
        "body_type": "terrestrial",
        "size": 3,
        "distance_from_star": 1.5,
        "biome": biome,
        "description": "",
        "poi_count": 0,
        "explored": False,
    }


def _make_body(**kwargs):
    """Helper to create a Body instance with sensible defaults."""
    defaults = {
        "id": "body_001",
        "name": "Test Planet",
        "body_type": "terrestrial",
        "size": 3,
        "distance_from_star": 1.5,
        "biome": None,
        "description": "",
        "poi_count": 0,
        "explored": False,
    }
    defaults.update(kwargs)
    return Body(**defaults)


class TestBodyFromDictBiomeFix:
    def test_from_dict_biome_none(self) -> None:
        body = Body.from_dict(_make_body_dict(biome=None))
        assert body.biome is None

    def test_from_dict_biome_desert(self) -> None:
        body = Body.from_dict(_make_body_dict(biome="desert"))
        assert body.biome == "desert"

    def test_from_dict_biome_missing_key(self) -> None:
        d = {
            "id": "body_001",
            "name": "Test Planet",
            "body_type": "terrestrial",
            "size": 3,
            "distance_from_star": 1.5,
        }
        body = Body.from_dict(d)
        assert body.biome is None

    def test_from_dict_biome_empty_string(self) -> None:
        body = Body.from_dict(_make_body_dict(biome=""))
        assert body.biome == ""

    def test_roundtrip_biome_none(self) -> None:
        original = _make_body(biome=None)
        d = original.to_dict()
        restored = Body.from_dict(d)
        assert restored.biome is None

    def test_roundtrip_biome_desert(self) -> None:
        original = _make_body(biome="desert")
        d = original.to_dict()
        restored = Body.from_dict(d)
        assert restored.biome == "desert"

    def test_roundtrip_all_fields(self) -> None:
        original = _make_body(
            biome="arctic",
            description="A frozen world",
            poi_count=3,
            explored=True,
        )
        d = original.to_dict()
        restored = Body.from_dict(d)
        assert restored == original

    def test_from_dict_biome_not_converted_to_empty_string(self) -> None:
        body = Body.from_dict(_make_body_dict(biome=None))
        assert body.biome != ""


class TestValidateSystemType:
    def test_valid_types(self) -> None:
        for system_type in ["civilized", "agricultural", "frontier", "nebula", "uncharted", "ancient"]:
            validate_system_type(system_type)

    def test_invalid_type_raises(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="Unknown system_type"):
            validate_system_type("invalid_type")


class TestStarSystem:
    def test_from_dict_constructs(self) -> None:
        d = {
            "id": "sys_001",
            "name": "Alpha Centauri",
            "x": 100.0,
            "y": 200.0,
            "star_type": "G",
            "star_color": "#ffff00",
            "phenomenon": "none",
            "phenomenon_desc": "",
                       "has_trading_station": True,
            "bodies": [],
            "visited": False,
            "scanned": False,
            "system_type": "civilized",
        }
        system = StarSystem.from_dict(d)
        assert system.id == "sys_001"
        assert system.name == "Alpha Centauri"
        assert system.x == 100.0
        assert system.y == 200.0
        assert system.star_type == "G"
        assert system.has_trading_station is True
        assert system.bodies == []

    def test_from_dict_with_bodies(self) -> None:
        body_dict = _make_body_dict(biome="ocean")
        d = {
            "id": "sys_002",
            "name": "Beta Hydri",
            "x": 300.0,
            "y": 400.0,
            "star_type": "K",
            "star_color": "#ffa500",
            "phenomenon": "nebula",
            "phenomenon_desc": "A shimmering nebula",
            "has_trading_station": False,
            "bodies": [body_dict],
            "visited": True,
            "scanned": True,
            "system_type": "frontier",
        }
        system = StarSystem.from_dict(d)
        assert len(system.bodies) == 1
        assert system.bodies[0].biome == "ocean"

    def test_system_roundtrip(self) -> None:
        body = _make_body(biome="volcanic")
        system = StarSystem(
            id="sys_003",
            name="Gamma Draconis",
            x=500.0,
            y=600.0,
            star_type="M",
            star_color="#ff0000",
            phenomenon="pulsar",
            phenomenon_desc="A rapidly spinning pulsar",
            has_trading_station=True,
            bodies=[body],
            visited=True,
            scanned=True,
            system_type="ancient",
        )
        d = system.to_dict()
        restored = StarSystem.from_dict(d)
        assert restored == system
