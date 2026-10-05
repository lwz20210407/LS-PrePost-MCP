"""Native result captions and explicit rendering averages; no generated title suffixes."""
from .native import commands as nc

AVERAGES = {"none": "none", "nodal": "nodal", "minmax": "minmax"}

# Observed in 4.13 Fcomp Stress/Ndv/Strain/Misc lists. Derived mean stress,
# geometric area/volume have plain quantity names, never invented native labels.
NAMES = {
    "von_mises": "Von Mises stress", "effective_plastic_strain": "effective plastic strain",
    "pressure": "pressure", "mean_stress": "mean stress",
    "disp_magnitude": "result displacement", "internal_energy_density": "internal energy density",
    "thickness": "shell thickness", "area": "area", "volume": "volume",
    "stress_1stprincipal": "1st-principal stress", "stress_2ndprincipal": "2nd-principal stress",
    "stress_3rdprincipal": "3rd-principal stress",
}
for component in ("x", "y", "z", "xy", "yz", "zx"):
    NAMES["stress_"+component] = component+"-stress"
    NAMES["strain_"+component] = component+"-strain"
for component in "xyz":
    NAMES["disp_"+component] = component+"-displacement"
    NAMES["velo_"+component] = component+"-velocity"
    NAMES["accel_"+component] = component+"-acceleration"
    NAMES["state_node_"+component] = component+"-coordinate"


def averaging_command(averaging):
    if not isinstance(averaging, str) or averaging not in AVERAGES:
        raise ValueError("averaging must be minmax, nodal or none")
    return nc.averaging(AVERAGES[averaging])


def result_name(field):
    try:
        return NAMES[field]
    except KeyError as exc:
        raise ValueError("No verified result name for field") from exc
