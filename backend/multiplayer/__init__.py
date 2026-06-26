"""
Multiplayer package for the 'Ghosts in the Void' asynchronous shared universe system.

Provides ghost signatures (player traces left in star systems), Crossroads
(a shared trading post for item and lore donations/messages), and discovery
ripple propagation (notifications when nearby discoveries are made).

Modules:
    - :mod:`~backend.multiplayer.api`: REST API endpoints for multiplayer features.
    - :mod:`~backend.multiplayer.models`: Data models for ghosts, crossroads, and ripples.
    - :mod:`~backend.multiplayer.schemas`: Pydantic request/response validation schemas.
    - :mod:`~backend.multiplayer.ghosts`: Ghost signature recording and retrieval.
    - :mod:`~backend.multiplayer.crossroads`: Crossroads donation, claim, and message logic.
    - :mod:`~backend.multiplayer.ripples`: Discovery ripple generation and acknowledgement.
    - :mod:`~backend.multiplayer.database`: Multiplayer database initialization.
"""