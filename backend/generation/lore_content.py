"""
Lore fragment content definitions for Starfarer: Echoes of the Void.

Defines 20 narrative lore fragments across 4 story arcs. Fragments are
defined as plain data to be loaded into :class:`LoreFragment` objects
at runtime.
"""

FRAGMENT_DATA = [
    # === Arc 1: The Architects ===
    {
        "arc": "architects",
        "fragment_number": 1,
        "title": "Echoes of the Void",
        "text": "They came from the void between galaxies, their ships the size of moons. They did not conquer\u2014they cultivated. Every world they touched bore fruit, and every fruit bore life.",
    },
    {
        "arc": "architects",
        "fragment_number": 2,
        "title": "Living Cities",
        "text": "Their cities were grown, not built. Organic spires reached toward the heavens, pulsing with bioluminescent light. The architecture breathed, adapted, healed.",
    },
    {
        "arc": "architects",
        "fragment_number": 3,
        "title": "The Seeding",
        "text": "They seeded life across a thousand worlds, each ecosystem a masterpiece of genetic artistry. From the simplest microbe to the most complex megafauna, all bore their signature.",
    },
    {
        "arc": "architects",
        "fragment_number": 4,
        "title": "The Departure",
        "text": "Something caused them to leave. The archaeological record shows a sudden, orderly exodus. They dismantled their cities, recalled their seeds, and vanished into the void from which they came.",
    },
    {
        "arc": "architects",
        "fragment_number": 5,
        "title": "The Echo",
        "text": "The signal they left behind still echoes across the galaxy. A faint, repeating pattern that some say contains their final message. Decoding it would change everything.",
    },

    # === Arc 2: The Void Signal ===
    {
        "arc": "void_signal",
        "fragment_number": 1,
        "title": "First Contact",
        "text": "A transmission of unknown origin was first detected by deep-space observatories near the galactic core. It followed no known modulation scheme and appeared to originate from outside the galaxy entirely.",
    },
    {
        "arc": "void_signal",
        "fragment_number": 2,
        "title": "The Cycle",
        "text": "It repeats every 47 standard cycles with mathematical precision. The signal strength fluctuates, suggesting a rotating source\u2014perhaps a beacon on an artificial world.",
    },
    {
        "arc": "void_signal",
        "fragment_number": 3,
        "title": "The Coordinates",
        "text": "The signal contains coordinates encoded within its carrier wave. Decryption revealed a path leading toward the galactic rim, through systems previously thought to be empty.",
    },
    {
        "arc": "void_signal",
        "fragment_number": 4,
        "title": "The Relay Network",
        "text": "Whoever built the relay network understood jump physics better than any known civilization. The relays form a chain, each one boosting the signal and pointing to the next.",
    },
    {
        "arc": "void_signal",
        "fragment_number": 5,
        "title": "Beyond the Rim",
        "text": "The final destination lies beyond the galactic rim, where few have ventured and fewer have returned. Whatever awaits there has waited eons for a visitor.",
    },

    # === Arc 3: The Fracture ===
    {
        "arc": "fracture",
        "fragment_number": 1,
        "title": "The Golden Age",
        "text": "The empire spanned three arms of the galaxy at its height. Millions of worlds, trillions of citizens, a civilization of unimaginable scale and sophistication.",
    },
    {
        "arc": "fracture",
        "fragment_number": 2,
        "title": "The Collapse",
        "text": "The cause of the collapse is disputed among scholars. Some say a plague, others a civil war, and a few whisper of something far worse\u2014a weapon that unraveled reality itself.",
    },
    {
        "arc": "fracture",
        "fragment_number": 3,
        "title": "Survivors",
        "text": "Survivor colonies still exist on the fringes of the old empire. They have regressed technologically but preserved fragments of knowledge, passed down through generations as sacred texts.",
    },
    {
        "arc": "fracture",
        "fragment_number": 4,
        "title": "Lost Technology",
        "text": "Their technology is sought by all who know of it. Gravity manipulators, matter printers, consciousness transference\u2014artifacts of a civilization that had begun to transcend physical form.",
    },
    {
        "arc": "fracture",
        "fragment_number": 5,
        "title": "The Ark",
        "text": "One city-ship escaped the destruction, carrying the last repository of their knowledge. Its location was erased from all records, but legends say it still drifts, waiting to be found.",
    },

    # === Arc 4: The Wanderer ===
    {
        "arc": "wanderer",
        "fragment_number": 1,
        "title": "Another Traveler",
        "text": "Another ship, similar to yours, was here. The engine signatures match your own vessel's design, but the readings are decades old. You are not the first to make this journey.",
    },
    {
        "arc": "wanderer",
        "fragment_number": 2,
        "title": "The Pilot's Log",
        "text": "Log entries describe a lone pilot, driven by a purpose they never fully revealed. They spoke of a 'call' they had to answer, a mystery that pulled them across the galaxy.",
    },
    {
        "arc": "wanderer",
        "fragment_number": 3,
        "title": "The Search",
        "text": "They were searching for something\u2014or someone. Cargo manifests show unusual items: ancient star charts, encrypted data cylinders, and a single, unidentifiable artifact.",
    },
    {
        "arc": "wanderer",
        "fragment_number": 4,
        "title": "Perseverance",
        "text": "Their ship was damaged, but they pressed on. Repair patches cover the hull. Log entries become more fragmented, more urgent. They were running out of time.",
    },
    {
        "arc": "wanderer",
        "fragment_number": 5,
        "title": "The Final Entry",
        "text": "The final log entry cuts off mid-sentence. The last recorded coordinates point to a system not on any chart. What they found there\u2014or what found them\u2014remains unknown.",
    },
]

ARC_DISPLAY_NAMES = {
    "architects": "The Architects",
    "void_signal": "The Void Signal",
    "fracture": "The Fracture",
    "wanderer": "The Wanderer",
}

ARC_IDS = list(ARC_DISPLAY_NAMES.keys())
