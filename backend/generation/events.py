"""
Procedural event generation and resolution system.

Defines the template library of in-game events and provides functions
for triggering random events and resolving player choices against them.
"""

import random
import uuid
from typing import Any, Callable, Optional

from backend.models.game_state import GameState
from backend.models.event import Event, Choice
from backend.config import MORALE_LOW_THRESHOLD
from backend.utils import deterministic_hash, seeded_random


EVENT_TEMPLATES: list[dict[str, Any]] = [
    {
        "type": "exploration",
        "rarity": "common",
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
        "rarity": "common",
        "title": "Solar Flare",
        "flavor": "A massive solar flare erupts from the star, sending a wave of radiation toward your ship. Alarms blare across all decks.",
        "choices": [
            {"text": "Take cover behind the nearest planet", "outcome": "hull:-10; fuel:-5; Emergency burn to reach cover."},
            {"text": "Deploy radiation shielding", "outcome": "credits:-50; Radiation shielding deployed successfully, no damage taken."},
            {"text": "Ride it out", "outcome": "hull:-20; crew:-1; morale:-10; Radiation sickness claims a crew member."},
        ],
    },
    {
        "type": "encounter",
        "rarity": "common",
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
        "rarity": "common",
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
        "rarity": "common",
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
        "rarity": "common",
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
        "category": "crisis",
        "rarity": "common",
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
        "rarity": "common",
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
        "rarity": "common",
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
        "rarity": "common",
        "title": "Asteroid Swarm",
        "flavor": "Navigation alerts scream as a dense cluster of asteroids bears down on your position. Collision imminent.",
        "choices": [
            {"text": "Navigate through the gaps", "outcome": "fuel:-10; hull:-5; Threaded the needle."},
            {"text": "Use mining lasers to clear a path", "outcome": "fuel:-15; cargo:2; Cleared a path and collected minerals."},
            {"text": "Full reverse thrust", "outcome": "fuel:-20; Backed away safely, but used a lot of fuel."},
        ],
    },
    {
        "type": "hazard",
        "rarity": "common",
        "title": "Micrometeorite Storm",
        "flavor": "A dense cloud of micrometeorites streaks toward your ship, pinging off the hull like cosmic hail. Impact alerts flash across the bridge.",
        "choices": [
            {"text": "Activate point defense lasers", "outcome": "fuel:-10; Point defense lasers neutralized the threat, but drained power reserves."},
            {"text": "Angle hull plating", "outcome": "hull:-15; Hull plating deflected most impacts, but some got through."},
            {"text": "Dodge and weave", "outcome": "hull:-25; The evasive maneuver failed \u2014 the storm was too dense."},
        ],
    },
    {
        "type": "hazard",
        "rarity": "uncommon",
        "title": "Nebula Storm",
        "flavor": "The nebula around you begins to churn violently. Electromagnetic discharges ripple through the clouds, and your shields flicker under the onslaught.",
        "choices": [
            {"text": "Ride it out", "outcome": "hull:-10; fuel:-5; morale:-5; Weathered the storm with minor damage."},
            {"text": "Full power to shields", "outcome": "fuel:-15; hull:0; Shields held. Fuel reserves took the hit."},
            {"text": "Attempt to navigate through", "outcome": "fuel:-10; hull:-5; credits:50; Navigated the storm and salvaged valuable data."},
        ],
        "trigger_conditions": {"phenomenon": "nebula"},
    },
    {
        "type": "exploration",
        "rarity": "uncommon",
        "title": "Abandoned Outpost",
        "flavor": "Scanners reveal the remains of an old outpost on the surface below. Its design is unfamiliar and its purpose unclear.",
        "choices": [
            {"text": "Search for salvage", "outcome": "credits:100; Found valuable components and data logs in the ruins."},
            {"text": "Study the architecture", "outcome": "morale:10; The crew is fascinated by the alien design."},
            {"text": "Mark for later investigation", "outcome": "Coordinates logged for future reference."},
        ],
        "trigger_conditions": {"biomes": ["barren", "crystal", "tundra"]},
    },
    {
        "type": "crew",
        "rarity": "common",
        "title": "Crew Discovery",
        "flavor": "One of your crew members bursts onto the bridge, holding something unusual they found in the cargo bay. It wasn't in the inventory last time you checked.",
        "choices": [
            {"text": "Examine the find", "outcome": "credits:75; It's a rare mineral sample with market value."},
            {"text": "Have the crew catalog it", "outcome": "morale:5; The crew appreciates being entrusted with the find."},
            {"text": "Sell it at the next station", "outcome": "credits:50; A quick but less profitable sale."},
        ],
    },
    {
        "type": "trade",
        "rarity": "uncommon",
        "title": "Trade Route Opportunity",
        "flavor": "A passing convoy broadcasts an open invitation: a newly established trade route needs suppliers. The pay is excellent, but the route adds a detour.",
        "choices": [
            {"text": "Take the trade route", "outcome": "credits:200; fuel:-10; Delivered the goods and earned a handsome profit."},
            {"text": "Decline", "outcome": "The convoy moves on. Perhaps another time."},
            {"text": "Negotiate a better cut", "outcome": "credits:300; fuel:-10; Sharp negotiating paid off with premium rates."},
        ],
        "trigger_conditions": {"min_systems_visited": 3},
    },
    {
        "type": "narrative",
        "rarity": "rare",
        "title": "Signal from Home",
        "flavor": "A faint, nostalgic signal reaches your comms array. It's a recorded message from your home world, sent long ago and only now arriving in this region of space.",
        "choices": [
            {"text": "Listen to the full message", "outcome": "morale:20; The crew gathers in silence, reminded of what they're journeying for."},
            {"text": "Save it for later", "outcome": "morale:10; The message is archived. A comfort to know it's there."},
            {"text": "Analyze the signal source", "outcome": "morale:5; credits:50; Traced the signal path and found a relay station with valuable data."},
        ],
        "trigger_conditions": {"max_morale": 29},
    },
    {
        "type": "hazard",
        "rarity": "rare",
        "title": "Gravity Anomaly",
        "flavor": "Instruments go wild as a sudden gravity well opens nearby. Space itself seems to bend, and your ship is caught in the distortion.",
        "choices": [
            {"text": "Full burn to escape", "outcome": "fuel:-20; hull:-5; Engines screamed, but you pulled free of the anomaly."},
            {"text": "Use the slingshot", "outcome": "fuel:-10; Rode the gravity wave and saved fuel in the process."},
            {"text": "Study the anomaly", "outcome": "fuel:-5; credits:100; Observed the anomaly from the edge and gathered breakthrough data."},
        ],
    },
    {
        "type": "hazard",
        "rarity": "rare",
        "title": "Quantum Fluctuation",
        "flavor": "Space-time briefly warps around your ship. Instruments go haywire. For a moment, you see... something else. A shimmering tear in reality pulses nearby.",
        "choices": [
            {"text": "Record the anomaly", "outcome": "credits:250; Recorded a Quantum Data sample \u2014 highly valuable scientific data."},
            {"text": "Stabilize the ship", "outcome": "fuel:-10; Stabilized the ship through the fluctuation. No damage sustained."},
            {"text": "Follow the fluctuation", "outcome": "hull:-15; The fluctuation collapsed violently, stressing the hull."},
        ],
    },
    {
        "type": "encounter",
        "rarity": "uncommon",
        "title": "Derelict Signal",
        "flavor": "A weak distress signal emanates from a derelict ship drifting in the void. It's been dead for years, but its data core may still hold secrets.",
        "choices": [
            {"text": "Board the derelict", "outcome": "credits:150; hull:-5; Salvaged the data core and valuable components."},
            {"text": "Scan from a distance", "outcome": "credits:50; Remote scanning yielded partial logs and data."},
            {"text": "Report the coordinates", "outcome": "morale:10; Reported the wreck to the Cartographers Union."},
        ],
        "trigger_conditions": {"unexplored_preference": True},
    },
    {
        "type": "exploration",
        "rarity": "uncommon",
        "title": "Restricted Coordinates",
        "flavor": "The Stellar Cartographers Union reaches out with a special offer based on your standing: access to restricted system coordinates, revealing rare uncharted worlds normally off-limits to independent pilots.",
        "choices": [
            {"text": "Accept the coordinates", "outcome": "credits:100; fuel:-5; morale:10; The coordinates lead to a system rich with resources and knowledge. The Cartographers nod with approval."},
            {"text": "Decline and report unusual findings instead", "outcome": "credits:50; The Cartographers appreciate your caution and log your findings."},
            {"text": "Ask for more information first", "outcome": "morale:5; They share partial data \u2014 enough to be useful, but not their best."},
        ],
        "trigger_conditions": {"min_reputation": {"faction_id": "stellar_cartographers", "value": 20}},
    },
    {
        "type": "trade",
        "rarity": "uncommon",
        "title": "Black Market Access",
        "flavor": "A Void Traders contact discreetly signals you, offering access to their black market network \u2014 rare upgrades and exotic items not available on regular stations. Your reputation with the Syndicate has finally earned you this privilege.",
        "choices": [
            {"text": "Browse the black market inventory", "outcome": "credits:-150; cargo:2; morale:5; Acquired rare components and data cores from off-record sources."},
            {"text": "Negotiate for better terms", "outcome": "credits:-100; cargo:1; morale:10; Your reputation earned you a discount and a valuable contact."},
            {"text": "Report the black market to authorities", "outcome": "credits:50; morale:-5; The Void Traders hear about it later."},
        ],
        "trigger_conditions": {"min_reputation": {"faction_id": "void_traders", "value": 20}},
    },
    {
        "type": "crew",
        "rarity": "uncommon",
        "title": "Crew Recruitment Offer",
        "flavor": "The Free Pilots Guild comms you with an offer: they have skilled crew members looking for a berth aboard a reputable ship. A pilot with combat experience, a veteran navigator, and an engineer who served on a deep-space freighter.",
        "choices": [
            {"text": "Recruit the veteran navigator", "outcome": "crew:1; morale:10; credits:-100; The navigator brings star charts and experience."},
            {"text": "Recruit the combat pilot", "outcome": "crew:1; morale:15; credits:-150; A seasoned fighter joins your crew."},
            {"text": "Thank them but decline", "outcome": "morale:5; The Guild appreciates the courtesy call."},
        ],
        "trigger_conditions": {"min_reputation": {"faction_id": "free_pilots", "value": 20}},
    },
    {
        "type": "exploration",
        "rarity": "rare",
        "title": "Priority Salvage Rights",
        "flavor": "The Stellar Cartographers Union grants you priority salvage rights to a newly discovered derelict station. Your standing with the Union means you get first pick before anyone else arrives.",
        "choices": [
            {"text": "Conduct a thorough salvage operation", "outcome": "credits:250; cargo:2; fuel:-5; Salvaged valuable tech and data from the derelict."},
            {"text": "Focus on data recovery only", "outcome": "credits:150; morale:10; Recovered encrypted logs with fascinating historical data."},
            {"text": "Tag it for Union study teams", "outcome": "credits:100; The Union appreciates your cooperation and shares the findings."},
        ],
        "trigger_conditions": {"min_reputation": {"faction_id": "stellar_cartographers", "value": 50}},
    },
    {
        "type": "trade",
        "rarity": "rare",
        "title": "Fuel Cache Locations",
        "flavor": "The Void Traders Syndicate shares a set of coordinates: hidden fuel caches scattered across the sector. As a trusted partner, you are given access to these strategic reserves.",
        "choices": [
            {"text": "Route to the nearest cache", "outcome": "fuel:30; morale:10; Fueled up from a hidden Syndicate cache."},
            {"text": "Map all cache locations", "outcome": "fuel:15; credits:100; Mapped the cache network \u2014 valuable intel and some fuel."},
            {"text": "Share the intel with your crew", "outcome": "fuel:20; morale:15; The crew is energized knowing there are fuel reserves ahead."},
        ],
        "trigger_conditions": {"min_reputation": {"faction_id": "void_traders", "value": 50}},
    },
    {
        "type": "encounter",
        "rarity": "rare",
        "title": "Elite Crew Available",
        "flavor": "The Free Pilots Guild sends word that an elite rescue squadron is available to support your missions. Your reputation as a reliable ally has earned you access to their best personnel.",
        "choices": [
            {"text": "Accept the elite squadron support", "outcome": "morale:20; credits:200; The rescue squadron joins your operation, doubling mission payouts."},
            {"text": "Request training for your crew instead", "outcome": "morale:25; Your crew learns advanced rescue techniques from the elite pilots."},
            {"text": "Coordinate a joint mission", "outcome": "credits:300; morale:10; A coordinated rescue operation with the Guild proves highly profitable."},
        ],
        "trigger_conditions": {"min_reputation": {"faction_id": "free_pilots", "value": 50}},
    },
    {
        "type": "hazard",
        "rarity": "uncommon",
        "title": "Time Dilation Anomaly",
        "flavor": "Your ship's chronometers begin drifting. Time flows differently near the black hole's gravity well. You experience what feels like hours in minutes.",
        "choices": [
            {"text": "Push closer to study the effect", "outcome": "credits:200; hull:-15; Gained valuable scientific data from the time dilation effect."},
            {"text": "Maintain safe distance and observe", "outcome": "credits:100; Observed the time dilation from a safe distance."},
            {"text": "Withdraw immediately", "outcome": "A wise decision \u2014 some phenomena are best observed from afar."},
        ],
        "trigger_conditions": {"phenomenon": "black_hole"},
    },
    {
        "type": "discovery",
        "rarity": "uncommon",
        "title": "Hawking Radiation Harvest",
        "flavor": "Sensors detect a faint glow around the black hole's event horizon \u2014 Hawking radiation. Your ship's collectors could harvest this exotic energy.",
        "choices": [
            {"text": "Attempt to harvest", "outcome": "fuel:20; hull:-12; Successfully harvested Hawking radiation! Gained fuel and a rare Hawking Particle."},
            {"text": "Scan and record data", "outcome": "credits:150; Recorded valuable scientific data on Hawking radiation."},
            {"text": "Avoid the dangerous approach", "outcome": "Some risks aren't worth taking."},
        ],
        "trigger_conditions": {"phenomenon": "black_hole"},
    },
    {
        "type": "hazard",
        "rarity": "rare",
        "title": "Spaghettification Near-Miss",
        "flavor": "A gravitational eddy catches your ship, pulling you toward the event horizon. The hull groans as tidal forces begin to stretch the frame.",
        "choices": [
            {"text": "Full emergency thrust", "outcome": "fuel:-12; hull:-8; Escaped the gravity well with emergency thrust, but at a cost."},
            {"text": "Ride the gravity assist", "outcome": "hull:-18; fuel:15; Used the black hole's gravity for a slingshot maneuver! Saved fuel but took hull damage."},
            {"text": "Deploy gravity anchor", "outcome": "cargo:-1; Escaped unscathed by sacrificing some cargo to the black hole."},
        ],
        "trigger_conditions": {"phenomenon": "black_hole"},
    },
    {
        "type": "discovery",
        "rarity": "uncommon",
        "title": "Accretion Disk Prospecting",
        "flavor": "The black hole's accretion disk glows with superheated matter. Your sensors detect dense mineral clusters within the disk \u2014 extremely valuable but dangerous to reach.",
        "choices": [
            {"text": "Send a probe into the disk", "outcome": "credits:250; The probe returned with incredibly valuable mineral samples!"},
            {"text": "Skim the edge of the disk", "outcome": "credits:150; hull:-5; Carefully skimmed the edge and recovered some valuable materials."},
            {"text": "Observe from safe distance", "outcome": "credits:50; Recorded observations of the accretion disk from a safe distance."},
        ],
        "trigger_conditions": {"phenomenon": "black_hole"},
    },
    {
        "type": "discovery",
        "rarity": "uncommon",
        "title": "Gravitational Lens Observation",
        "flavor": "The black hole's gravity is bending light from distant stars, creating a natural telescope of unprecedented power. You can see galaxies normally hidden behind nebulae.",
        "choices": [
            {"text": "Study the lensed images carefully", "outcome": "credits:200; morale:10; Gathered valuable astronomical data from the gravitational lens!"},
            {"text": "Quick observation", "outcome": "credits:100; Recorded useful astronomical observations."},
            {"text": "Ignore \u2014 too busy navigating", "outcome": "A missed opportunity, but the journey continues."},
        ],
        "trigger_conditions": {"phenomenon": "black_hole"},
    },
    {
        "type": "hazard",
        "rarity": "uncommon",
        "title": "Ion Storm",
        "flavor": "Electromagnetic interference disrupts your ship's systems. Screens flicker, navigation wavers as the ion storm engulfs your vessel.",
        "choices": [
            {"text": "Power down non-essential systems", "outcome": "cargo:-1; Systems safely powered down, but some cargo was jettisoned."},
            {"text": "Push through with emergency power", "outcome": "fuel:-15; hull:-5; Emergency power pushed through the storm with electrical damage."},
            {"text": "Wait it out", "outcome": "fuel:-5; morale:-5; Waited out the storm safely, but morale dipped from the delay."},
        ],
    },
    {
        "type": "discovery",
        "rarity": "uncommon",
        "title": "Protostar Formation",
        "flavor": "Deep within the nebula, a protostar is forming — a baby star. The heat and pressure create a zone of rare elements.",
        "choices": [
            {"text": "Collect samples from the accretion zone", "outcome": "hull:-8; Gathered valuable mineral samples from the protostar!"},
            {"text": "Observe and record data", "outcome": "Recorded valuable scientific data on protostar formation."},
            {"text": "Avoid — too dangerous", "outcome": "A wise decision."},
        ],
        "trigger_conditions": {"phenomenon": "nebula"},
    },
    {
        "type": "encounter",
        "rarity": "uncommon",
        "title": "Nebula Navigation Puzzle",
        "flavor": "The nebula's dense gas clouds are disrupting your navigation sensors. You're flying partially blind.",
        "choices": [
            {"text": "Follow the clearing current", "outcome": "fuel:4; Found a shortcut through the nebula!"},
            {"text": "Push through systematically", "outcome": "fuel:-4; Found a minor discovery in the nebula."},
            {"text": "Wait for sensors to recalibrate", "outcome": "fuel:-2; Waited for the sensors to recalibrate."},
        ],
        "trigger_conditions": {"phenomenon": "nebula"},
    },
    {
        "type": "hazard",
        "rarity": "uncommon",
        "title": "Radiation Pulse",
        "flavor": "The pulsar's beam sweeps across your position. Radiation alarms blare as your ship is bathed in intense energy.",
        "choices": [
            {"text": "Dive behind a nearby asteroid/moon", "outcome": "fuel:-5; Emergency maneuver avoided the radiation pulse."},
            {"text": "Shield up and brace", "outcome": "hull:-12; Gained a Pulsar Radiation Sample discovery!"},
            {"text": "Try to ride the beam", "outcome": "fuel:12; hull:-18; Absorbed energy from the pulsar beam!"},
        ],
        "trigger_conditions": {"phenomenon": "pulsar"},
    },
    {
        "type": "discovery",
        "rarity": "uncommon",
        "title": "Pulsar Timing Signal",
        "flavor": "The pulsar emits a regular timing signal — so precise it could be a navigation beacon. Someone — or something — may have calibrated this.",
        "choices": [
            {"text": "Decode the signal pattern", "outcome": "credits:100; Discovered a lore fragment from the pulsar signal!"},
            {"text": "Record the timing for later study", "outcome": "Recorded the pulsar timing data for later analysis."},
            {"text": "Ignore — just another dead star", "outcome": "The journey continues."},
        ],
        "trigger_conditions": {"phenomenon": "pulsar"},
    },
    {
        "type": "hazard",
        "rarity": "rare",
        "title": "Neutron Star Proximity",
        "flavor": "The pulsar's neutron star is incredibly dense. Getting close could yield incredible scientific data, but the gravity and radiation are extreme.",
        "choices": [
            {"text": "Close approach for data", "outcome": "hull:-18; Gained a valuable Neutronium Sample discovery!"},
            {"text": "Safe orbital scan", "outcome": "Conducted a safe orbital scan of the neutron star."},
            {"text": "Keep distance", "outcome": "Some phenomena are best observed from afar."},
        ],
        "trigger_conditions": {"phenomenon": "pulsar"},
    },
    {
        "type": "encounter",
        "rarity": "uncommon",
        "title": "Orbital Mechanics Challenge",
        "flavor": "You need to navigate between two orbiting stars. The gravitational fields are complex and constantly shifting.",
        "choices": [
            {"text": "Calculate the perfect trajectory", "outcome": "fuel:-4; credits:100; Successfully used a gravity assist between the binary stars!"},
            {"text": "Take the safe long route", "outcome": "fuel:-9; Took the long way around the binary system."},
            {"text": "Hire a local pilot (if at station)", "outcome": "credits:-100; Hired a local pilot for safe passage."},
        ],
        "trigger_conditions": {"phenomenon": "binary_star"},
    },
    {
        "type": "discovery",
        "rarity": "uncommon",
        "title": "Lagrange Point Discovery",
        "flavor": "At the Lagrange point between the two stars, debris has accumulated — a graveyard of asteroids and... is that an ancient satellite?",
        "choices": [
            {"text": "Search the debris field", "outcome": "Found valuable minerals and artifacts in the debris field!"},
            {"text": "Investigate the satellite", "outcome": "credits:150; Discovered an ancient satellite with valuable data!"},
            {"text": "Scan from distance and leave", "outcome": "Scanned the Lagrange point from a safe distance."},
        ],
        "trigger_conditions": {"phenomenon": "binary_star"},
    },
    {
        "type": "crisis",
        "category": "crisis",
        "rarity": "common",
        "title": "Hull Breach",
        "flavor": "A micrometeorite or pressure differential has breached the hull. Alarms blare as atmosphere vents into the void.",
        "choices": [
            {"text": "Emergency patch", "outcome": "hull:-15; Emergency patch stabilized the breach."},
            {"text": "Use cargo to seal breach", "outcome": "cargo:-1; Sacrificed cargo to seal the breach."},
            {"text": "Activate emergency bulkheads", "outcome": "fuel:-10; Emergency bulkheads sealed the breach."},
        ],
    },
    {
        "type": "crisis",
        "category": "crisis",
        "rarity": "common",
        "title": "Engine Fire",
        "flavor": "An electrical fire has broken out in the engine room. Smoke fills the corridors as temperature alarms trigger across the ship.",
        "choices": [
            {"text": "Fire suppression system", "outcome": "fuel:-10; Fire suppression system extinguished the flames."},
            {"text": "Manual extinguisher", "outcome": "hull:-5; Smoke inhalation caused minor damage."},
            {"text": "Emergency vent", "outcome": "fuel:-5; Emergency vent extinguished the fire."},
        ],
    },
    {
        "type": "crisis",
        "category": "crisis",
        "rarity": "common",
        "title": "Radiation Leak",
        "flavor": "The ship's shielding has degraded, exposing the crew to dangerous levels of radiation. Radiation alarms blare across all decks.",
        "choices": [
            {"text": "Emergency shielding repair", "outcome": "credits:-15; Emergency shielding repaired."},
            {"text": "Evacuate to safe zone", "outcome": "fuel:-5; Evacuated to safe zone."},
            {"text": "Push through", "outcome": "morale:-10; credits:10; Pushed through and salvaged shielding materials."},
        ],
    },
    {
        "type": "crisis",
        "category": "crisis",
        "rarity": "common",
        "title": "Food Contamination",
        "flavor": "A storage container has spoiled, contaminating the food supply. The crew reports a foul smell from the cargo bay.",
        "choices": [
            {"text": "Decontaminate", "outcome": "credits:-10; Decontaminated the food supply."},
            {"text": "Ration supplies", "outcome": "morale:-10; Rationing preserved what was left."},
            {"text": "Jettison and buy fresh at next station", "outcome": "cargo:-1; Jettisoned contaminated supplies."},
        ],
    },
    {
        "type": "crisis",
        "category": "crisis",
        "rarity": "common",
        "title": "Crew Illness",
        "flavor": "A crew member has fallen ill from an unknown pathogen. They are feverish and unable to perform their duties.",
        "choices": [
            {"text": "Medical treatment", "outcome": "credits:-20; Medical treatment stabilized the crew member."},
            {"text": "Quarantine", "outcome": "morale:-5; Quarantine contained the pathogen."},
            {"text": "Synthesize antidote", "outcome": "fuel:-10; Synthesized antidote cured the illness."},
        ],
    },
]


# Default cooldowns per event type (keyed by event title)
EVENT_COOLDOWNS = {
    "Passing Merchant": 3,
    "Solar Flare": 3,
    "Asteroid Swarm": 3,
    "Micrometeorite Storm": 3,
    "Crew Discovery": 3,
    "Derelict Vessel": 3,
    "Mysterious Beacon": 3,
    "Time Dilation Anomaly": 6,
    "Hawking Radiation Harvest": 6,
    "Ion Storm": 6,
    "Protostar Formation": 6,
    "Nebula Navigation Puzzle": 6,
    "Radiation Pulse": 6,
    "Pulsar Timing Signal": 6,
    "Accretion Disk Prospecting": 6,
    "Gravitational Lens Observation": 6,
    "Orbital Mechanics Challenge": 6,
    "Lagrange Point Discovery": 6,
    "Life Support Failure": 6,
    "Hull Breach": 8,
    "Engine Fire": 8,
    "Radiation Leak": 8,
    "Food Contamination": 8,
    "Crew Illness": 8,
    "Crew Dispute": 8,
    "Spaghettification Near-Miss": 8,
    "Neutron Star Proximity": 8,
    "Quantum Fluctuation": 8,
    "Signal from Home": 10,
    "Gravity Anomaly": 10,
    "Priority Salvage Rights": 10,
    "Fuel Cache Locations": 10,
    "Elite Crew Available": 10,
}


def apply_cooldown(state: GameState, event_title: str, event_type: str = "") -> None:
    """Set cooldown for an event after it fires.

    For hazard events, the cooldown scales with how many times the
    event has been triggered in the current session, making repeat
    hazard events less frequent.
    """
    base = EVENT_COOLDOWNS.get(event_title, 5)
    if event_type == "hazard":
        count = state.hazard_event_counts.get(event_title, 0)
        state.hazard_event_counts[event_title] = count + 1
        state.event_cooldowns[event_title] = base * (count + 1)
    else:
        state.event_cooldowns[event_title] = base


def decrement_cooldowns(state: GameState) -> None:
    """Decrement all active cooldowns by 1."""
    for event_id in list(state.event_cooldowns):
        state.event_cooldowns[event_id] -= 1
        if state.event_cooldowns[event_id] <= 0:
            del state.event_cooldowns[event_id]


def _get_eligible_templates(state: GameState, templates: list[dict]) -> list[dict]:
    """Filter event templates based on trigger conditions in the current game state.

    Checks phenomenon, biome, min_systems_visited, max_morale,
    unexplored_preference, and min_reputation conditions against the
    current system and ship state. Templates with no trigger conditions
    are always eligible.

    Fallback behavior: if every template that has ``trigger_conditions``
    is filtered out, the returned list contains *only* templates with
    **no** ``trigger_conditions``. Callers that further filter by
    event type (such as :func:`trigger_event`'s low-morale path, which
    keeps only ``crew``, ``crisis``, and ``narrative`` events) may end up
    with an empty list if the fallback templates do not include those
    types, causing the caller to return ``None``.

    :param state: The current game state.
    :type state: GameState
    :param templates: The full list of event templates.
    :type templates: list[dict]
    :returns: A filtered list of eligible templates. If no templates
        match any conditions, only templates with no trigger_conditions
        are returned as a fallback.
    :rtype: list[dict]
    """
    system = state.get_current_system()
    if not system:
        return templates

    eligible = []
    for t in templates:
        conditions = t.get("trigger_conditions", {})
        if not conditions:
            eligible.append(t)
            continue

        if "phenomenon" in conditions:
            if system.phenomenon != conditions["phenomenon"]:
                continue

        if "biomes" in conditions:
            body_biomes = {b.biome for b in system.bodies}
            if not any(biome in body_biomes for biome in conditions["biomes"]):
                continue

        if "min_systems_visited" in conditions:
            if state.systems_visited < conditions["min_systems_visited"]:
                continue

        if "max_morale" in conditions:
            if state.ship.morale > conditions["max_morale"]:
                continue

        if "unexplored_preference" in conditions:
            has_unexplored = any(not body.explored for body in system.bodies) if system.bodies else False
            if not has_unexplored:
                continue

        if "min_reputation" in conditions:
            rep_condition = conditions["min_reputation"]
            faction_id = rep_condition["faction_id"]
            required_rep = rep_condition["value"]
            if state.get_faction_reputation(faction_id) < required_rep:
                continue

        eligible.append(t)

    if not eligible:
        return [t for t in templates if not t.get("trigger_conditions")]
    return eligible


def _apply_cooldown_fallback(eligible: list[dict], state: GameState) -> list[dict]:
    """Apply cooldown fallback: prefer events not on cooldown; if all are on cooldown, pick the one(s) with the lowest cooldown, avoiding last_event_title if possible."""
    # Guard: if there are no eligible templates at all, return empty early.
    if not eligible:
        return []
    eligible_not_on_cd = [t for t in eligible if state.event_cooldowns.get(t["title"], 0) <= 0]
    if eligible_not_on_cd:
        return eligible_not_on_cd
    eligible = sorted(eligible, key=lambda t: state.event_cooldowns.get(t["title"], 0))
    min_cooldown = state.event_cooldowns.get(eligible[0]["title"], 0)
    eligible = [t for t in eligible if state.event_cooldowns.get(t["title"], 0) == min_cooldown]
    eligible_no_last = [t for t in eligible if t["title"] != state.last_event_title]
    if eligible_no_last:
        return eligible_no_last[:1]
    return eligible[:1]


def trigger_event(state: GameState, rng_override: Optional[random.Random] = None) -> Event | None:
    """Possibly trigger a procedural event based on the current game state.

    Events have a base 35% chance of triggering after a jump, scan, or
    exploration. If morale is low (<30), the probability roll is skipped
    entirely and the function attempts to force a ``crew``, ``crisis``, or
    ``narrative`` event. In this low-morale path, templates are first
    filtered by :func:`_get_eligible_templates` and then further narrowed
    to only those three event types. If no templates survive both filters
    (including when the :func:`_get_eligible_templates` fallback produces
    only templates without those types), ``None`` is returned.

    In the normal path, templates are filtered by trigger conditions and
    weighted by rarity (common=5, uncommon=2, rare=1). A cooldown prevents
    the same event title from appearing twice in a row.

    Event cooldowns are checked via ``state.event_cooldowns``. Events with
    active cooldowns are skipped. If all eligible events are on cooldown,
    the one with the lowest remaining cooldown is allowed as a fallback.

    :param state: The current game state.
    :type state: GameState
    :param rng_override: Optional pre-seeded :class:`random.Random`
        instance to use instead of creating one from state. Useful
        for deterministic testing of probabilistic branches.
    :type rng_override: Optional[random.Random]
    :returns: A new :class:`Event` if triggered, or ``None`` otherwise.
    :rtype: Event | None
    """
    system = state.get_current_system()
    if not system:
        return None

    if state.ship.morale < MORALE_LOW_THRESHOLD:
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)
        eligible = [t for t in eligible if t["type"] in ("crew", "crisis", "narrative")]

        if state.crisis_cooldown > 0:
            eligible = [t for t in eligible if t.get("category") != "crisis"]

        eligible = _apply_cooldown_fallback(eligible, state)

        eligible_no_last = [t for t in eligible if t["title"] != state.last_event_title]
        if eligible_no_last:
            eligible = eligible_no_last
        if not eligible:
            return None
        template = eligible[deterministic_hash(system.id, str(len(state.log_entries))) % len(eligible)]
        state.last_event_title = template["title"]
        apply_cooldown(state, template["title"], template["type"])
        if state.crisis_cooldown > 0:
            state.crisis_cooldown -= 1
        if template.get("category") == "crisis":
            state.crisis_cooldown = 3
        return _create_event(template, system.id)

    rng = rng_override or seeded_random(state.seed, "event_trigger", system.id, str(len(state.events)), str(len(state.log_entries)))

    if rng.random() < 0.35:
        eligible = _get_eligible_templates(state, EVENT_TEMPLATES)

        if state.crisis_cooldown > 0:
            eligible = [t for t in eligible if t.get("category") != "crisis"]

        eligible = _apply_cooldown_fallback(eligible, state)

        eligible_no_last = [t for t in eligible if t["title"] != state.last_event_title]
        if eligible_no_last:
            eligible = eligible_no_last
        if not eligible:
            return None

        rarity_weights = {"common": 5, "uncommon": 2, "rare": 1}
        weights = [rarity_weights.get(t.get("rarity", "common"), 1) for t in eligible]
        template = rng.choices(eligible, weights=weights, k=1)[0]
        state.last_event_title = template["title"]
        apply_cooldown(state, template["title"], template["type"])
        if state.crisis_cooldown > 0:
            state.crisis_cooldown -= 1
        if template.get("category") == "crisis":
            state.crisis_cooldown = 3
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
        category=template.get("category"),
        choices=choices,
        system_id=system_id,
    )


def _bonus_credits_morale(state: GameState) -> None:
    """Add 10 credits and 1 morale (capped at 100) as a reputation bonus."""
    state.ship.credits += 10
    state.ship.morale = min(100, state.ship.morale + 1)


def _bonus_credits(state: GameState) -> None:
    """Add 10 credits as a reputation bonus."""
    state.ship.credits += 10


def _bonus_morale(state: GameState) -> None:
    """Add 5 morale (capped at 100) as a reputation bonus."""
    state.ship.morale = min(100, state.ship.morale + 5)


# Only event types explicitly listed in this map receive faction reputation
# changes when resolved. Any event type not present (e.g. "narrative") is
# silently skipped — no reputation changes, no bonus, no log entry.
_EVENT_REP_MAP: dict[str, tuple[str, tuple[int, int], Callable]] = {
    "exploration": ("stellar_cartographers", (2, 8), _bonus_credits_morale),
    "discovery": ("stellar_cartographers", (2, 8), _bonus_credits_morale),
    "trade": ("void_traders", (2, 8), _bonus_credits),
    "encounter": ("free_pilots", (1, 6), _bonus_morale),
    "crisis": ("free_pilots", (1, 6), _bonus_morale),
    "crew": ("free_pilots", (1, 6), _bonus_morale),
    "hazard": ("free_pilots", (1, 6), _bonus_morale),
}


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
    state.add_log("event", f"Event '{event.title}' resolved: {choice.text}. {choice.outcome}", category="event", title=event.title)

    event_rng = seeded_random(state.seed, "event_reputation", event.id, str(choice_idx))

    rep_before = {}
    rep_after = {}

    if event.event_type in _EVENT_REP_MAP:
        faction_id, (rep_min, rep_max), bonus_fn = _EVENT_REP_MAP[event.event_type]
        rep_before[faction_id] = state.get_faction_reputation(faction_id)
        state.modify_faction_reputation(faction_id, event_rng.randint(rep_min, rep_max))
        rep_after[faction_id] = state.get_faction_reputation(faction_id)
        if rep_after[faction_id] >= 20:
            bonus_fn(state)
        if rep_before[faction_id] != rep_after[faction_id]:
            state.add_log("faction", f"{faction_id.replace('_', ' ').title()} reputation changed from {rep_before[faction_id]} to {rep_after[faction_id]}.", category="system", title="Reputation Change")

    extra_output = {
        "title": event.title,
        "chosen_text": choice.text,
        "outcome_text": choice.outcome,
        "effects": effects,
    }
    return True, choice.outcome, extra_output
