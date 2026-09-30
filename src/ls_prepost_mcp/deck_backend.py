"""Optional version-aligned PyDYNA keyword operations. Never invokes a solver."""
import importlib.metadata
import math
from collections import Counter
from pathlib import Path


def api():
    try:
        from ansys.dyna.core import Deck, keywords
    except ImportError as exc:
        raise RuntimeError("Install the pydyna extra for Deck operations") from exc
    return Deck, keywords


def inspect_deck(path: Path) -> dict:
    Deck, _ = api()
    deck = Deck()
    deck.import_file(str(path))
    counts = Counter()
    raw = 0
    for card in deck.keywords:
        if isinstance(card, str):
            raw += 1
        else:
            counts[str(card.keyword) + ("_" + str(card.subkeyword) if card.subkeyword else "")] += 1
    return {"backend": "pydyna", "version": importlib.metadata.version("ansys-dyna-core"),
            "keyword_counts": dict(counts), "unparsed_blocks": raw,
            "validation_scope": "Parser inventory, not solver/physical validation; includes are not expanded"}


def material_values(density: float, young_modulus: float, poisson_ratio: float) -> dict:
    ro, e, pr = float(density), float(young_modulus), float(poisson_ratio)
    if not all(math.isfinite(v) for v in (ro, e, pr)) or ro <= 0 or e <= 0 or not -1 < pr < .5:
        raise ValueError("Elastic material requires finite density>0, E>0, and -1<Poisson ratio<0.5")
    return {"ro": ro, "e": e, "pr": pr}


def create_material(output: Path, material_id: int, values: dict) -> dict:
    Deck, kw = api()
    deck = Deck()
    deck.append(kw.Mat001(mid=material_id, **values))
    deck.export_file(str(output))
    return verify_material(output, material_id, values)


def update_material(source: Path, output: Path, material_id: int, values: dict) -> dict:
    Deck, kw = api()
    # Rewriting an include-bearing parent into a new cwd would change resolution.
    # Refuse until include-tree copy/rewrite is implemented, instead of breaking it.
    if any(line.strip().upper().startswith("*INCLUDE") for line in source.read_text(errors="replace").splitlines()):
        raise ValueError("Material update currently requires a standalone deck without includes")
    deck = Deck()
    deck.import_file(str(source))
    candidates = [c for c in deck.get_kwds_by_type("MAT") if getattr(c, "mid", None) == material_id]
    if len(candidates) != 1:
        raise ValueError("Material ID must identify exactly one material")
    card = candidates[0]
    if not isinstance(card, (kw.Mat001, kw.MatElastic)):
        raise ValueError("This operation only modifies MAT_001/MAT_ELASTIC")
    for key, value in values.items():
        setattr(card, key, value)
    deck.export_file(str(output))
    return verify_material(output, material_id, values)


def verify_material(path: Path, material_id: int, values: dict) -> dict:
    Deck, _ = api()
    reloaded = Deck()
    reloaded.import_file(str(path))
    found = [c for c in reloaded.get_kwds_by_type("MAT") if getattr(c, "mid", None) == material_id]
    if len(found) != 1 or any(not math.isclose(float(getattr(found[0], k)), v, rel_tol=1e-6, abs_tol=1e-12)
                              for k, v in values.items()):
        raise ValueError("Material did not survive export/reimport verification")
    return {"backend": "pydyna", "material_id": material_id, "values": values, "reimport_verified": True,
            "version": importlib.metadata.version("ansys-dyna-core"), "solver_validated": False}

