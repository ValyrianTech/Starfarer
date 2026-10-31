"""
Pydantic request and response schemas for the Starfarer API.

Defines the data models used for validating API request bodies
and structuring API responses.
"""

import re

from pydantic import BaseModel, field_validator

from backend.models.faction import FACTION_DEFINITIONS


class NewGameRequest(BaseModel):
    """Request body for creating a new game.

    All fields are optional; defaults are applied on the server side
    if not specified. ``shared_universe`` defaults to ``True`` so that
    an omitted value uses the canonical shared universe.
    """

    seed: int | None = None
    ship_name: str | None = None
    game_id: str | None = None
    shared_universe: bool = True

    @field_validator("game_id")
    @classmethod
    def validate_game_id(cls, value: str | None) -> str | None:
        """Ensure an optional game_id matches the allowed character set.

        Rejects game ids containing characters outside letters, digits,
        hyphen, or underscore, or longer than 64 characters, at validation
        time so the API never accepts a game id that could be misused.

        :param value: The game id supplied in the request body.
        :type value: str | None
        :returns: The validated game id, or ``None`` if omitted.
        :rtype: str | None
        :raises ValueError: If the value does not match the allowed pattern.
        """
        if value is None:
            return value
        if not re.fullmatch(r"^[A-Za-z0-9_-]{1,64}$", value):
            raise ValueError(
                "game_id must be 1-64 characters of letters, digits, hyphen or underscore"
            )
        return value


class ResolveEventRequest(BaseModel):
    """Request body for resolving an in-game event."""

    choice_index: int


class TradeRequest(BaseModel):
    """Request body for performing a trade action.

    Supports buying fuel, repairing the hull, or selling discoveries.
    """

    action: str
    item: str
    quantity: int = 1


class BulkSellItem(BaseModel):
    """A single item in a bulk sell request."""

    item: str
    quantity: int = 1


class BulkSellRequest(BaseModel):
    """Request body for selling multiple discoveries at once."""

    items: list[BulkSellItem]


class UpgradeRequest(BaseModel):
    """Request body for purchasing a ship upgrade."""

    upgrade_id: str


class HealthResponse(BaseModel):
    """Response body for the health check endpoint."""

    status: str
    version: str
    uptime: str


class CraftRequest(BaseModel):
    """Request body for emergency crafting a discovery into resources."""

    discovery_id: str
    output: str


class AcceptMissionRequest(BaseModel):
    """Request body for accepting a faction mission."""

    mission_id: str
    faction_id: str | None = None

    @field_validator("faction_id")
    @classmethod
    def validate_faction_id(cls, value: str | None) -> str | None:
        """Ensure an optional faction_id is a known faction, if provided.

        Rejects arbitrary, unknown, or whitespace-only faction ids at
        validation time so the API never accepts missions for factions
        that do not exist.

        :param value: The faction id supplied in the request body.
        :type value: str | None
        :returns: The validated faction id, or ``None`` if omitted.
        :rtype: str | None
        :raises ValueError: If a non-empty value is not a known faction.
        """
        if value is None:
            return None
        if not value.strip():
            raise ValueError("faction_id must not be whitespace-only")
        if value not in FACTION_DEFINITIONS:
            raise ValueError(f"Unknown faction_id: {value}")
        return value


class CompleteMissionRequest(BaseModel):
    """Request body for completing a faction mission."""

    mission_id: str
    faction_id: str | None = None


class DismissHintRequest(BaseModel):
    """Request body for dismissing a hint."""

    hint_id: str
