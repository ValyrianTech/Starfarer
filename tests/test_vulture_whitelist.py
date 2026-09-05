import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend import vulture_whitelist
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

    def test_getattr_records_accessed_names(self) -> None:
        whitelist = Whitelist()
        whitelist.anything  # noqa: B018
        whitelist.some_random_attribute  # noqa: B018
        whitelist.health  # noqa: B018
        assert "anything" in whitelist.__dict__
        assert "some_random_attribute" in whitelist.__dict__
        assert "health" in whitelist.__dict__
        assert whitelist.__dict__["anything"] is None


class TestModule:
    def test_exposes_whitelist_instance(self) -> None:
        assert hasattr(vulture_whitelist, "whitelist")
        assert isinstance(vulture_whitelist.whitelist, Whitelist)

    def test_whitelist_attribute_access_returns_none(self) -> None:
        assert vulture_whitelist.whitelist.health is None
        assert vulture_whitelist.whitelist.api_new_game is None
        assert vulture_whitelist.whitelist.api_scan is None

    def test_module_whitelist_records_names(self) -> None:
        whitelist = vulture_whitelist.whitelist
        assert len(whitelist.__dict__) > 0
        assert "health" in whitelist.__dict__
        assert "GAME_NAME" in whitelist.__dict__

    def test_all_route_names_present(self) -> None:
        whitelist = vulture_whitelist.whitelist
        expected = {
            "health",
            "api_new_game",
            "api_get_game",
            "api_galaxy",
            "api_system_detail",
            "api_jump",
            "api_scan",
            "api_land",
            "api_atmospheric_scan",
            "api_sub_surface_explore",
            "api_explore",
            "api_resolve_event",
            "api_log",
            "api_log_paginated",
            "api_discoveries",
            "api_cargo",
            "api_lore",
            "api_codex",
            "api_trade",
            "api_bulk_sell",
            "api_upgrade",
            "api_upgrades_info",
            "api_nearby",
            "api_distress",
            "api_salvage",
            "api_salvage_craft",
            "api_factions",
            "api_faction_detail",
            "api_faction_mission",
            "api_missions",
            "api_accept_mission",
            "api_complete_mission",
            "api_save",
            "api_load",
            "api_dismiss_hint",
            "api_leaderboard",
            "api_spectate_games",
            "api_spectate_stream",
            "api_system_ghosts",
            "api_leave_ghost",
            "api_crossroads_items",
            "api_donate_item",
            "api_claim_item",
            "api_crossroads_lore",
            "api_donate_lore",
            "api_claim_lore",
            "api_crossroads_messages",
            "api_post_message",
            "api_ripples",
            "api_acknowledge_ripple",
            "index",
        }
        missing = expected - set(whitelist.__dict__.keys())
        assert not missing, f"Missing route handler names in whitelist: {sorted(missing)}"

    def test_all_config_constants_present(self) -> None:
        whitelist = vulture_whitelist.whitelist
        expected = {
            "GAME_NAME",
            "GAME_VERSION",
            "MAX_CARGO",
            "MAX_HULL",
            "MAX_FUEL",
            "MAX_MORALE",
            "MAX_CREW",
            "BIOME_COLORS",
            "ALL_DISCOVERY_CATEGORIES",
        }
        missing = expected - set(whitelist.__dict__.keys())
        assert not missing, f"Missing config constants in whitelist: {sorted(missing)}"

    def test_all_fixtures_present(self) -> None:
        whitelist = vulture_whitelist.whitelist
        expected = {"setup_db", "lore_frags", "cleanup_messages"}
        missing = expected - set(whitelist.__dict__.keys())
        assert not missing, f"Missing fixtures in whitelist: {sorted(missing)}"

    def test_all_misc_names_present(self) -> None:
        whitelist = vulture_whitelist.whitelist
        expected = {"side_effect", "row_factory", "application", "status", "text_not_blank"}
        missing = expected - set(whitelist.__dict__.keys())
        assert not missing, f"Missing misc names in whitelist: {sorted(missing)}"
