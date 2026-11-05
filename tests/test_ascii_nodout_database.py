"""Q06 NODOUT named components keep the printed node and field identities."""
import csv
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service

TRANSLATION = "nodal point x-disp y-disp z-disp x-vel y-vel z-vel x-accl y-accl z-accl x-coor y-coor z-coor"
ROTATION = "nodal point x-rot y-rot z-rot x-rot vel y-rot vel z-rot vel x-rot acc y-rot acc z-rot acc"
COMPONENTS = [(f"{axis}_{quantity}", offset+i, f"{axis}-{raw}")
              for quantity, offset, raw in [("displacement", 0, "disp"), ("velocity", 3, "vel"),
                                             ("acceleration", 6, "accl")]
              for i, axis in enumerate("xyz")]


def row(node, values):
    return f"{node:10d}" + "".join(f"{value:12.5E}" for value in values) + "\n"


def table(time, step, kind, rows):
    return (f"n o d a l   p r i n t   o u t   f o r   t i m e  s t e p {step:7d} ( at time {time:.7E} )\n"
            + (TRANSLATION if kind == "translation" else ROTATION) + "\n"
            + "".join(row(node, values) for node, values in rows))


FIRST = [(90, [1, -2, 3, -4, 5, -6, 7, -8, 9, 101, 102, 103]),
         (10, [-11, 12, -13, 14, -15, 16, -17, 18, -19, 201, 202, 203])]
SECOND = [(10, [-21, 22, -23, 24, -25, 26, -27, 28, -29, 301, 302, 303]),
          (90, [31, -32, 33, -34, 35, -36, 37, -38, 39, 401, 402, 403])]
TEXT = ("Synthetic nodal result\nSolver version\n{BEGIN LEGEND}\n90\n10\n{END LEGEND}\n"
        + table(0, 1, "translation", FIRST) + table(0, 1, "rotation", [(90, [0]*9), (10, [0]*9)])
        + table(2, 42, "translation", SECOND) + table(2, 42, "rotation", [(10, [1]*9), (90, [2]*9)]))


@pytest.mark.parametrize("component,index,label", COMPONENTS)
def test_named_nodout_components_are_literal_translation_fields(tmp_path, component, index, label):
    source = tmp_path / "nodout"
    source.write_text(TEXT, encoding="utf8")
    result = Service(Settings(tmp_path)).extract_database(str(source), "nodout", component, "source_units",
                                                         time_units="source_time")
    assert result["status"] == "succeeded", result["error"]
    data = result["data"]
    assert result["backend"] == "ls-dyna-ascii"
    assert data["source_kind"] == "ascii" and data["source_format"] == "nodout"
    assert data["ids"] == [90, 10] and data["stored_columns"] == [0, 1]
    assert data["state_count"] == 2 and data["row_count"] == 4
    assert data["source_column_names"]["value"] == [label]
    with Path(result["artifacts"][0]["path"]).open(newline="", encoding="utf8") as stream:
        exported = list(csv.DictReader(stream))
    assert [float(r[component]) for r in exported] == [FIRST[0][1][index], FIRST[1][1][index],
                                                     SECOND[1][1][index], SECOND[0][1][index]]
