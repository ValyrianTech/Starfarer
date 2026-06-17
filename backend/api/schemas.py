from pydantic import BaseModel
from typing import Optional, Any


class NewGameRequest(BaseModel):
    seed: Optional[int] = None
    ship_name: Optional[str] = None
    game_id: Optional[str] = None


class JumpRequest(BaseModel):
    target_system_id: str


class LandRequest(BaseModel):
    body_id: str


class ResolveEventRequest(BaseModel):
    choice_index: int


class TradeRequest(BaseModel):
    action: str
    item: str
    quantity: int = 1


class UpgradeRequest(BaseModel):
    upgrade_id: str


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: str


class GameResponse(BaseModel):
    game_id: str
    state: Any


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
