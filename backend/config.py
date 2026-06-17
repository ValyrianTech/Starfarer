GAME_NAME = "Starfarer: Echoes of the Void"
GAME_VERSION = "0.1.0"

DEFAULT_SHIP_NAME = "Serendipity"
DEFAULT_SEED = 42

INITIAL_FUEL = 80
INITIAL_HULL = 100
INITIAL_CARGO = 0
INITIAL_CREW = 4
INITIAL_MORALE = 80
INITIAL_CREDITS = 1000
INITIAL_JUMP_RANGE = 4
INITIAL_SCANNER = 1
MAX_CARGO = 50

MIN_ORBITALS = 1
MAX_ORBITALS = 8

GALAXY_SYSTEM_COUNT = 50
GALAXY_WIDTH = 1200
GALAXY_HEIGHT = 800

JUMP_FUEL_COST_PER_LY = 3
SCAN_FUEL_COST = 5
EXPLORE_FUEL_COST = 2

MAX_HULL = 100
MAX_FUEL = 100
MAX_MORALE = 100
MAX_CREW = 10

MORALE_LOW_THRESHOLD = 30
MORALE_DECAY_PER_JUMP = 2

STAR_SPECTRAL_TYPES = ["O", "B", "A", "F", "G", "K", "M"]
STAR_COLORS = {
    "O": "#9db4ff",
    "B": "#aabfff",
    "A": "#cad8ff",
    "F": "#f8f7ff",
    "G": "#fff4ea",
    "K": "#ffd2a1",
    "M": "#ffcc6f",
}

BIOME_TYPES = ["desert", "tundra", "jungle", "ocean", "volcanic", "barren", "gas_giant", "crystal"]
BIOME_COLORS = {
    "desert": "#d4a853",
    "tundra": "#c8e0f0",
    "jungle": "#3d8c40",
    "ocean": "#2969a8",
    "volcanic": "#8b3a1a",
    "barren": "#8a8a8a",
    "gas_giant": "#c4a882",
    "crystal": "#a8e6cf",
}

SYSTEM_PHENOMENA = ["none", "nebula", "asteroid_field", "binary_star", "pulsar", "black_hole", "ancient_gate"]
PHENOMENON_WEIGHTS = [60, 15, 10, 8, 3, 2, 2]

PLANET_NAMES = [
    "Aurelia", "Boreas", "Caelus", "Dorado", "Elysium", "Frost", "Gaia", "Hephaestus",
    "Icarus", "Juno", "Kepler", "Lyra", "Mira", "Nova", "Oberon", "Pandora",
    "Quorra", "Rhea", "Sylva", "Tartarus", "Umbriel", "Vesper", "Wraith", "Xenon",
]

MOON_NAMES = [
    "Charon", "Deimos", "Europa", "Ganymede", "Hyperion", "Io", "Janus", "Luna",
    "Mimas", "Nereid", "Oberon", "Phoebe", "Rhea", "Titan", "Umbriel",
]

UPGRADE_COSTS = {
    "hyperdrive": 500,
    "scanner": 400,
    "cargo_hold": 350,
    "hull_plating": 450,
    "fuel_tanks": 300,
    "life_support": 400,
}

UPGRADE_EFFECTS = {
    "hyperdrive": {"jump_range": 1},
    "scanner": {"scanner": 1},
    "cargo_hold": {"max_cargo": 10},
    "hull_plating": {"max_hull": 20},
    "fuel_tanks": {"max_fuel": 20},
    "life_support": {"morale_decay_reduction": 1},
}

UPGRADE_MAX_LEVELS = {
    "hyperdrive": 5,
    "scanner": 5,
    "cargo_hold": 4,
    "hull_plating": 3,
    "fuel_tanks": 3,
    "life_support": 3,
}
