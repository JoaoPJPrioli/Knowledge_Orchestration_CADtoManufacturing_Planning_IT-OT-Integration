"""
Axis travel envelope used by the serialiser, the validator and the simulator.

This is the ONE place the envelope values live. They are code defaults, not
machine knowledge: knowledge/foundation/machines.owl declares no travel
limits (only bar and swing diameters), and SKLRepository.list_machines()
supplies no 'x_axis_travel' or 'z_axis_travel' capability, so for every
machine in this repository these defaults apply. A machine dictionary that
does carry those capabilities overrides the maxima.

X is the lathe X word as the serialiser writes it (diameter convention,
spindle centreline at 0); Z = 0 at the chuck face, positive towards the
tailstock.
"""
from typing import Dict, Optional

DEFAULT_TRAVEL_ENVELOPE_MM = {
    "x_min": 0.0,
    "x_max": 150.0,
    "z_min": 0.0,
    "z_max": 1000.0,
}


def travel_envelope(machine: Optional[Dict] = None) -> Dict[str, float]:
    """Envelope for a machine dictionary (SKLRepository.legacy_machines_dict()
    entry): the defaults above, with x_max/z_max overridden only when the
    dictionary declares x_axis_travel/z_axis_travel capabilities."""
    caps = (machine or {}).get("capabilities", {}) or {}
    env = dict(DEFAULT_TRAVEL_ENVELOPE_MM)
    if caps.get("x_axis_travel") is not None:
        env["x_max"] = float(caps["x_axis_travel"])
    if caps.get("z_axis_travel") is not None:
        env["z_max"] = float(caps["z_axis_travel"])
    return env


def excursions(x: float, z: float, env: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Amount by which (x, z) lies outside the envelope, per axis (empty
    when inside)."""
    env = env or DEFAULT_TRAVEL_ENVELOPE_MM
    out = {}
    if x < env["x_min"]:
        out["x"] = x - env["x_min"]
    elif x > env["x_max"]:
        out["x"] = x - env["x_max"]
    if z < env["z_min"]:
        out["z"] = z - env["z_min"]
    elif z > env["z_max"]:
        out["z"] = z - env["z_max"]
    return out
