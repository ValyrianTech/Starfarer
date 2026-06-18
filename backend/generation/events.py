"""
Procedural event generation and resolution system.

Defines the template library of in-game events and provides functions
for triggering random events and resolving player choices against them.
"""

import hashlib
import random
import uuid

from backend.models.game_state import GameState
from backend.models.event import Event, Choice


EVENT_TEMPLATES = [
    {
        "type": "exploration",
        "title": "Ancient Signal",
        "flavor": "Your comms array picks up a faint, repeating signal from the planet below. It follows no known protocol but has a deliberate pattern \u2014 clearly artificial.",
        "choices": [
            {"text": "Investigate the signal source", "outcome": "credits:50; fuel:-5; Discovered a hidden data cache."},
            {"text": "Log the frequency and move on", "outcome": "morale:-5; The crew wonders what was missed."},
            {"text": "Broadcast a response", "outcome": "morale:10; No reply came, but the attempt felt right."},
        ],
    },
    {
        "type": "hazard",
        "title": "Solar Flare",
        "flavor": "Alarms blare as the system star unleashes a massive coronal ejection directly toward your ship. Radiation levels spike.",
        "choices": [
            {"text": "Divert power to shields", "outcome": "hull:-10; fuel:-10; Shields absorbed most of the blast."},
            {"text": "Take shelter behind the nearest planet", "outcome": "fuel:-15; Safely avoided the worst of it."},
            {"text": "Ride it out", "outcome": "hull:-25; The hull groans under the onslaught."},
        ],
    },
    {
        "type": "encounter",
        "title": "Derelict Vessel",
        "flavor": "A dead ship drifts in the void, its hull scarred and dark. It belongs to no known design in your database.",
        "choices": [
            {"text": "Board the derelict", "outcome": "credits:200; cargo:2; Found valuable salvage and data logs."},
            {"text": "Scan from a safe distance", "outcome": "credits:50; Gathered some data, but left the valuables."},
            {"text": "Mark it and continue", "outcome": "morale:-10; The crew wanted to explore."},
        ],
    },
    {
        "type": "crew",
        "title": "Crew Dispute",
        "flavor": "A heated argument breaks out between two crew members over resource allocation. Morale is suffering.",
        "choices": [
            {"text": "Mediate the dispute personally", "outcome": "morale:15; fuel:-2; Your leadership settled the matter."},
            {"text": "Let them sort it out", "outcome": "morale:-10; The tension festers."},
            {"text": "Institute new resource protocols", "outcome": "morale:5; credits:-50; A bureaucratic solution, but it worked."},
        ],
    },
    {
        "type": "trade",
        "title": "Passing Merchant",
        "flavor": "A trader vessel hails you, offering rare goods at what they claim are 'fair prices'. Their ship is well-armed.",
        "choices": [
            {"text": "Trade fuel for credits", "outcome": "credits:150; fuel:-15; A profitable exchange."},
            {"text": "Buy rare technology", "outcome": "credits:-200; cargo:1; Acquired exotic tech."},
            {"text": "Decline and move on", "outcome": "A quiet decision."},
        ],
    },
    {
        "type": "discovery",
        "title": "Uncharted Ruins",
        "flavor": "Scanner detects a massive structure on the surface \u2014 clearly artificial, clearly ancient. No record of it exists.",
        "choices": [
            {"text": "Land and explore the ruins", "outcome": "fuel:-10; hull:-5; Made incredible discoveries!"},
            {"text": "Orbital survey only", "outcome": "Documented from orbit. Safer, but less rewarding."},
            {"text": "Send a probe", "outcome": "fuel:-3; credits:-50; Probe returned partial data."},
        ],
    },
    {
        "type": "crisis",
        "title": "Life Support Failure",
        "flavor": "A critical failure in the life support system threatens the entire crew. Oxygen levels are dropping fast.",
        "choices": [
            {"text": "Emergency repair \u2014 divert all power", "outcome": "hull:-20; fuel:-20; Life support restored."},
            {"text": "Evacuate to escape pods", "outcome": "crew:-1; morale:-30; Lost a crewmate, but the rest survived."},
            {"text": "Ration oxygen and hope for the best", "outcome": "morale:-20; hull:-10; Made it through, barely."},
        ],
    },
    {
        "type": "exploration",
        "title": "Wormhole Anomaly",
        "flavor": "Instruments go haywire as a swirling vortex of spacetime tears open nearby. It appears stable, briefly.",
        "choices": [
            {"text": "Enter the wormhole", "outcome": "fuel:-30; morale:20; Emerged in an uncharted region of space!"},
            {"text": "Study it from a safe distance", "outcome": "credits:100; Valuable scientific data collected."},
            {"text": "Flee immediately", "outcome": "fuel:-15; A wise precaution, perhaps."},
        ],
    },
    {
        "type": "encounter",
        "title": "Mysterious Beacon",
        "flavor": "An automated beacon transmits a looping message: coordinates to an uncharted system, plus a warning in an unknown language.",
        "choices": [
            {"text": "Plot a course to the coordinates", "outcome": "fuel:-20; A leap into the unknown."},
            {"text": "Decode the warning first", "outcome": "morale:10; credits:50; Deciphered a warning about pirates \u2014 avoided a trap."},
            {"text": "Destroy the beacon", "outcome": "Some things are better left alone."},
        ],
    },
    {
        "type": "hazard",
        "title": "Asteroid Swarm",
        "flavor": "Navigation alerts scream as a dense cluster of asteroids bears down on your position. Collision imminent.",
        "choices": [
            {"text": "Navigate through the gaps", "outcome": "fuel:-10; hull:-5; Threaded the needle."},
            {"text": "Use mining lasers to clear a path", "outcome": "fuel:-15; cargo:2; Cleared a path and collected minerals."},
            {"text": "Full reverse thrust", "outcome": "fuel:-20; Backed away safely, but used a lot of fuel."},
        ],
    },
]


def _deterministic_hash(*args) -> int:
    """Produce a deterministic integer from the given arguments."""
    seed_str = "".join(str(a) for a in args)
    return int(hashlib.md5(seed_str.encode()).hexdigest(), 16)


def trigger_event(state: GameState) -> Event | None:
    """Possibly trigger a procedural event based on the current game state.

    Events have a base 35% chance of triggering after a jump, scan, or
    exploration. If morale is low (<30), crew or crisis events are
    forced. Systems with phenomena are more likely to trigger hazard,
    discovery, or exploration events.

    :param state: The current game state.
    :type state: GameState
    :returns: A new :class:`Event` if triggered, or ``None`` otherwise.
    :rtype: Event | None
    """
    system = state.get_current_system()
    if not system:
        return None

    if state.ship.morale < 30:
        crew_events = [t for t in EVENT_TEMPLATES if t["type"] == "crew" or t["type"] == "crisis"]
        template = crew_events[_deterministic_hash(system.id, str(len(state.log_entries))) % len(crew_events)]
        return _create_event(template, system.id)

    rng = random.Random(state.seed + _deterministic_hash(system.id, len(state.events), len(state.log_entries)))

    if rng.random() < 0.35:
        if system.phenomenon != "none" and rng.random() < 0.5:
            template = rng.choice([t for t in EVENT_TEMPLATES if t["type"] in ("hazard", "discovery", "exploration")])  # pragma: no cover  # probabilistic branch
        else:
            template = rng.choice(EVENT_TEMPLATES)
        return _create_event(template, system.id)

    return None


def _create_event(template: dict, system_id: str) -> Event:
    """Instantiate an :class:`Event` from a template dictionary.

    Generates a unique event ID and creates the event with its
    title, flavour text, type, and choice list.

    :param template: The event template dictionary with keys
        ``"title"``, ``"flavor"``, ``"type"``, and ``"choices"``.
    :type template: dict
    :param system_id: The ID of the star system where the event
        occurs.
    :type system_id: str
    :returns: A newly created :class:`Event`.
    :rtype: Event
    """
    event_id = str(uuid.uuid4())[:12]
    choices = [Choice(text=c["text"], outcome=c["outcome"]) for c in template["choices"]]
    return Event(
        id=event_id,
        title=template["title"],
        flavor=template["flavor"],
        event_type=template["type"],
        choices=choices,
        system_id=system_id,
    )


def resolve_event(state: GameState, event_id: str, choice_idx: int) -> tuple[bool, str, dict]:
    """Resolve a pending event by applying the chosen outcome.

    Validates that the event exists, is not already resolved, and that
    the choice index is valid. Applies the outcome effects to the ship
    and logs the resolution.

    :param state: The current game state.
    :type state: GameState
    :param event_id: The unique identifier of the event to resolve.
    :type event_id: str
    :param choice_idx: The index of the chosen outcome (0-based).
    :type choice_idx: int
    :returns: A tuple of ``(success, message, extra_output)`` where
        ``extra_output`` is a dictionary containing the event title,
        chosen text, outcome text, and applied effects.
    :rtype: tuple[bool, str, dict]
    :raises ValueError: If the event is not found, already resolved,
        or the choice index is invalid (caught and returned as
        ``(False, message, {})``).
    """
    event = None
    for e in state.events:
        if e.id == event_id:
            event = e
            break
    if not event:
        return False, "Event not found.", {}
    if event.resolved:
        return False, "Event already resolved.", {}
    if choice_idx < 0 or choice_idx >= len(event.choices):
        return False, f"Invalid choice index: {choice_idx}.", {}

    event.resolved = True
    event.chosen = choice_idx

    choice = event.choices[choice_idx]
    effects = state.apply_choice_outcome(choice.outcome)
    state.add_log("event", f"Event '{event.title}' resolved: {choice.text}. {choice.outcome}")

    extra_output = {
        "title": event.title,
        "chosen_text": choice.text,
        "outcome_text": choice.outcome,
        "effects": effects,
    }
    return True, choice.outcome, extra_output
