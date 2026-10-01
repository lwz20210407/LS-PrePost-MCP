"""Opt-in private large-model pages and native field acceptance; never run a solver."""

import argparse
import csv
import math
import re
import time
import uuid
from pathlib import Path

from run_result_selection_acceptance import hashes

from ls_prepost_mcp.config import Settings, scl_command_path
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.native_results import STRESS_KEYS, field_script
from ls_prepost_mcp.service import Service
from ls_prepost_mcp.stress import native_mises_matches, stress_metrics


def accept(workspace, executable, keyword, result):
    keyword, result = Path(keyword).resolve(strict=True), Path(result).resolve(strict=True)
    family = [result] + sorted(p for p in result.parent.iterdir()
                               if p.is_file() and re.fullmatch(re.escape(result.name) + r"\d+", p.name))
    originals = [keyword] + family
    identities = hashes(originals)
    root = Path(workspace).resolve() / ("native-mesh-pages-" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    service = Service(Settings(root, Path(executable), allowed_roots=(keyword.parent, result.parent), timeout=240))
    session = service.start_gui_session()
    sid = session["session_id"]
    atomic_json(root / "session.json", session)
    started = time.monotonic()
    summary = dict(status="failed", source_unchanged=False)
    try:
        service.show_gui_session(sid, maximize=True)
        baseline = {}
        for kind, source in (("keyword", keyword), ("d3plot", result)):
            opened = service.open_in_gui_session(sid, str(source), kind)
            atomic_json(root / (kind + "-open.json"), opened)
            assert opened["status"] == "succeeded", opened.get("error")
            counts = opened["data"]["counts"]
            assert max(counts["nodes"], counts["elements"]) > 20000
            for entity, count in (("node", counts["nodes"]), ("solid", counts["elements"])):
                # Fixture is solid-only. The page's domain total checks this.
                for offset in sorted({0, count // 2, max(0, count - 3)}):
                    page = service.inspect_gui_mesh(sid, entity_type=entity, offset=offset, limit=3)
                    atomic_json(root / ("%s-%s-%d.json" % (kind, entity, offset)), page)
                    assert page["status"] == "succeeded", page.get("error")
                    data = page["data"]
                    assert data["total"] == count and data["returned"] == min(3, count - offset)
                    rows = data["nodes" if entity == "node" else "elements"]
                    key = (entity, offset)
                    if kind == "keyword":
                        baseline[key] = rows
                    elif entity == "solid":
                        assert rows == baseline[key], "Keyword/result connectivity mismatch"
                    else:
                        for a, b in zip(rows, baseline[key], strict=True):
                            assert a[0] == b[0]
                            assert all(math.isclose(x, y, rel_tol=2e-6, abs_tol=1e-6)
                                       for x, y in zip(a[1:], b[1:], strict=True))
        service.set_gui_display(sid, view="isometric", center=True, capture=False)
        state = counts["states"]
        field = service.render_gui_field(sid, "solid", "von_mises", state, "model_stress")
        atomic_json(root / "field.json", field)
        assert field["status"] == "succeeded", field.get("error")
        with Path(field["artifacts"][1]["path"]).open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == counts["elements"] and max(float(row["von_mises"]) for row in rows) > 0
        chosen = sorted({int(rows[0]["entity_id"]), int(rows[-1]["entity_id"]),
                         int(max(rows, key=lambda row: float(row["von_mises"]))["entity_id"])})
        script, output = root / "independent.scl", root / "independent.csv"
        script.write_text(field_script("solid", chosen, [state], STRESS_KEYS + ["von_mises"], "0", output), encoding="utf-8")
        manager = service._session_manager()
        with manager.lock(sid):
            check = manager.dispatch(sid, "inspect_model", {}, native_commands=["runscript " + scl_command_path(script)])
        assert check["status"] == "succeeded", check.get("error")
        lookup = {int(row["entity_id"]): float(row["von_mises"]) for row in rows}
        with output.open(newline="") as stream:
            checked = list(csv.DictReader(stream))
        assert len(checked) == len(chosen)
        for row in checked:
            components = [float(row[k]) for k in STRESS_KEYS]
            value = float(row["von_mises"])
            assert native_mises_matches(components, stress_metrics(components)["von_mises"], value)
            assert math.isclose(lookup[int(row["entity_id"])], value, rel_tol=2e-6, abs_tol=0)
        summary.update(status="succeeded", counts=counts, pages_checked=12, field_rows=len(rows),
                       whole_mesh_JSON_used=False, elapsed_seconds=time.monotonic() - started)
    finally:
        summary["source_unchanged"] = identities == hashes(originals)
        atomic_json(root / "acceptance.json", summary)
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    assert summary["source_unchanged"]
    print(str(root), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "executable", "keyword", "result"):
        parser.add_argument("--" + name, required=True)
    accept(**vars(parser.parse_args()))
