"""
Pydantic request schemas for multiplayer API endpoints.

Defines the data models used for validating request bodies
for the Ghosts in the Void multiplayer layer.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class LeaveGhostRequest(BaseModel):
    """Request body for leaving a ghost signature in a star system."""

    message: Optional[str] = None


class DonateItemRequest(BaseModel):
    """Request body for donating an item to the Crossroads."""

    game_id: str
    item_name: str
    quantity: int = 1
    message: Optional[str] = None


class ClaimItemRequest(BaseModel):
    """Request body for claiming an item from the Crossroads."""

    game_id: str


class DonateLoreRequest(BaseModel):
    """Request body for donating a lore fragment to the Crossroads."""

    game_id: str
    fragment_id: str
    message: Optional[str] = None


class ClaimLoreRequest(BaseModel):
    """Request body for claiming a lore fragment from the Crossroads."""

    game_id: str


class PostMessageRequest(BaseModel):
    """Request body for posting a message at the Crossroads."""

    game_id: str
    text: str = Field(..., min_length=1, max_length=500)
    player_name: Optional[str] = None

    @field_validator('text')
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        """Validate that the message text is not blank or whitespace-only.

        :param v: The raw text value from the request body.
        :type v: str
        :returns: The text with leading and trailing whitespace removed.
        :rtype: str
        :raises ValueError: If the stripped text is empty.
        """
        if not v.strip():
            raise ValueError('Message text cannot be blank')
        return v.strip()
