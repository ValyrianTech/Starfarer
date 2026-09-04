"""
Pydantic request and response schemas for the Starfarer API.

Defines the data models used for validating API request bodies
and structuring API responses.
"""

from pydantic import BaseModel


class NewGameRequest(BaseModel):
    """Request body for creating a new game.

    All fields are optional; defaults are applied on the server side
    if not specified.
    """

    seed: int | None = None
    ship_name: str | None = None
    game_id: str | None = None
    shared_universe: bool | None = None


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


class CompleteMissionRequest(BaseModel):
    """Request body for completing a faction mission."""

    mission_id: str
    faction_id: str | None = None


class DismissHintRequest(BaseModel):
    """Request body for dismissing a hint."""

    hint_id: str
