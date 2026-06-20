"""
Pydantic request and response schemas for the Starfarer API.

Defines the data models used for validating API request bodies
and structuring API responses.
"""

from pydantic import BaseModel
from typing import Optional, Any


class NewGameRequest(BaseModel):
    """Request body for creating a new game.

    All fields are optional; defaults are applied on the server side
    if not specified.
    """

    seed: Optional[int] = None
    ship_name: Optional[str] = None
    game_id: Optional[str] = None


class JumpRequest(BaseModel):
    """Request body for initiating a hyperspace jump."""

    target_system_id: str


class LandRequest(BaseModel):
    """Request body for landing on a celestial body."""

    body_id: str


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


class GameResponse(BaseModel):
    """Response body for game-related endpoints."""

    game_id: str
    state: Any


class ErrorResponse(BaseModel):
    """Response body for error conditions."""

    error: str
    detail: Optional[str] = None
