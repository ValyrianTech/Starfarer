import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import backend.vulture_whitelist as vulture_whitelist
from backend.vulture_whitelist import Whitelist


class TestWhitelist:
    def test_getattr_returns_none(self) -> None:
        whitelist = Whitelist()
        assert whitelist.anything is None
        assert whitelist.some_random_attribute is None
        assert whitelist.health is None

    def test_arbitrary_attributes_do_not_raise(self) -> None:
        whitelist = Whitelist()
        for name in ("foo", "bar", "baz", "_private", "nested.attr"):
            assert getattr(whitelist, name) is None


class TestModule:
    def test_exposes_whitelist_instance(self) -> None:
        assert hasattr(vulture_whitelist, "whitelist")
        assert isinstance(vulture_whitelist.whitelist, Whitelist)

    def test_whitelist_attribute_access_returns_none(self) -> None:
        assert vulture_whitelist.whitelist.health is None
        assert vulture_whitelist.whitelist.api_new_game is None

    def test_representative_route_names_accessible(self) -> None:
        whitelist = vulture_whitelist.whitelist
        for name in (
            "health",
            "api_new_game",
            "api_get_game",
            "api_galaxy",
            "api_system_detail",
            "api_jump",
            "api_land",
            "api_scan",
            "api_explore",
            "api_trade",
            "api_upgrade",
            "api_save",
            "api_load",
            "api_leaderboard",
        ):
            assert getattr(whitelist, name) is None

    def test_representative_config_constants_accessible(self) -> None:
        whitelist = vulture_whitelist.whitelist
        for name in (
            "GAME_NAME",
            "GAME_VERSION",
            "MAX_CARGO",
            "MAX_HULL",
            "MAX_FUEL",
            "MAX_MORALE",
            "MAX_CREW",
            "BIOME_COLORS",
            "ALL_DISCOVERY_CATEGORIES",
        ):
            assert getattr(whitelist, name) is None

    def test_representative_fixtures_accessible(self) -> None:
        whitelist = vulture_whitelist.whitelist
        for name in ("setup_db", "lore_frags", "cleanup_messages"):
            assert getattr(whitelist, name) is None

    def test_representative_misc_names_accessible(self) -> None:
        whitelist = vulture_whitelist.whitelist
        for name in ("side_effect", "row_factory", "application", "status", "text_not_blank"):
            assert getattr(whitelist, name) is None
