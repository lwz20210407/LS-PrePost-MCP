"""G04 target tool ``query_entities``: unified entity identify for nodes, elements, and parts.

Supports querying:
- Nodes: user ID, reference & deformed coordinates, connected elements, belonging parts,
  and state result values (displacements, velocities).
- Elements (solid, shell, beam, tshell): user ID, element type, connectivity (node IDs),
  node coordinates and centroid, belonging part ID/name, material info, alive state,
  and state result values (Cauchy stress components, stress invariants, effective plastic strain).
- Parts: user part ID, title/name, material/section references, element counts and IDs,
  unique node counts and IDs, bounding box and centroid, and state results summary.

Reuses domain.results.lasso_backend, domain.results.invariants, and domain.model.operations.
Returns strict JobResult/v1 conforming to I02 contracts.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from .core.contracts import JobResult
from .domain.model.operations import inspect_deck
from .domain.results import invariants as inv
from .domain.results import lasso_backend as lb

STRESS_COMPONENTS = ("sxx", "syy", "szz", "sxy", "syz", "szx")
BACKEND_LASSO = "lasso"
BACKEND_KEYWORD = "keyword-engine"

QUANTITY_ALIASES: dict[str, str] = {
    "mises": "von_mises",
    "vm": "von_mises",
    "eps": "effective_plastic_strain",
    "plastic_strain": "effective_plastic_strain",
    "disp": "displacement",
    "velo": "velocity",
    "coords": "coordinates",
}


def _jsonable(value: object) -> object:
    """Plain JSON values: numpy scalars and arrays converted, NaN/Inf serialized as string, None preserved."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _result(operation: str, status: str, backend: str, data: dict[str, Any], **fields: object) -> dict[str, Any]:
    return JobResult(
        operation=operation,
        status=status,
        backend=backend,
        data=_jsonable(data),
        **fields,
    ).model_dump(mode="json")


def _is_d3plot_path(path: Path) -> bool:
    name = path.name.lower()
    if "d3plot" in name:
        return True
    if path.suffix.lower() in (".k", ".key", ".dyn", ".inc"):
        return False
    # If no suffix or unknown, check if lasso can read it
    return True


def _parse_keyword_mesh(deck_path: Path) -> dict[str, Any]:
    """Parse *NODE, *ELEMENT_*, and *PART blocks from a keyword file."""
    nodes: dict[int, list[float]] = {}
    elements: list[dict[str, Any]] = []

    current_keyword: str | None = None
    with deck_path.open("r", encoding="latin1", errors="replace") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("$"):
                continue
            if raw.startswith("*"):
                current_keyword = raw.split(",")[0].split()[0].upper()
                continue
            if current_keyword == "*NODE":
                tokens = line.split(",") if "," in line else line.split()
                if len(tokens) >= 4:
                    try:
                        nid = int(tokens[0])
                        x = float(tokens[1])
                        y = float(tokens[2])
                        z = float(tokens[3])
                        nodes[nid] = [x, y, z]
                    except ValueError:
                        pass
            elif current_keyword == "*ELEMENT_SOLID":
                tokens = line.split(",") if "," in line else line.split()
                if len(tokens) >= 10:
                    try:
                        eid = int(tokens[0])
                        pid = int(tokens[1])
                        node_ids = [int(p) for p in tokens[2:10]]
                        elements.append({"type": "solid", "id": eid, "part_id": pid, "nodes": node_ids})
                    except ValueError:
                        pass
            elif current_keyword == "*ELEMENT_SHELL":
                tokens = line.split(",") if "," in line else line.split()
                if len(tokens) >= 6:
                    try:
                        eid = int(tokens[0])
                        pid = int(tokens[1])
                        node_ids = [int(p) for p in tokens[2:6]]
                        elements.append({"type": "shell", "id": eid, "part_id": pid, "nodes": node_ids})
                    except ValueError:
                        pass
            elif current_keyword == "*ELEMENT_BEAM":
                tokens = line.split(",") if "," in line else line.split()
                if len(tokens) >= 4:
                    try:
                        eid = int(tokens[0])
                        pid = int(tokens[1])
                        node_ids = [int(p) for p in tokens[2:4]]
                        elements.append({"type": "beam", "id": eid, "part_id": pid, "nodes": node_ids})
                    except ValueError:
                        pass
            elif current_keyword == "*ELEMENT_TSHELL":
                tokens = line.split(",") if "," in line else line.split()
                if len(tokens) >= 10:
                    try:
                        eid = int(tokens[0])
                        pid = int(tokens[1])
                        node_ids = [int(p) for p in tokens[2:10]]
                        elements.append({"type": "tshell", "id": eid, "part_id": pid, "nodes": node_ids})
                    except ValueError:
                        pass

    # Inspect deck for parts and materials metadata
    deck_overview = inspect_deck(str(deck_path))
    parts_meta: dict[int, dict[str, Any]] = {}
    for p in deck_overview.get("parts", []):
        pid = p.get("pid")
        if pid is not None:
            parts_meta[int(pid)] = {
                "name": p.get("heading"),
                "secid": p.get("secid"),
                "mid": p.get("mid"),
            }
    mat_titles: dict[int, str] = {}
    for m in deck_overview.get("materials", []):
        mid = m.get("mid")
        if mid is not None:
            mat_titles[int(mid)] = m.get("title") or m.get("keyword", "")

    return {
        "nodes": nodes,
        "elements": elements,
        "parts_meta": parts_meta,
        "mat_titles": mat_titles,
    }


class EntityIdentifyTools:
    """M2 target tool ``query_entities`` (G04): unified entity identify queries for nodes, elements, and parts."""

    def query_entities(
        self,
        model: str,
        entity_type: str,
        entity_ids: list[int] | int | None = None,
        state: int | None = None,
        quantity: str | None = None,
        component: str | None = None,
        part_ids: list[int] | int | None = None,
        offset: int = 0,
        limit: int = 100,
        file_type: str = "auto",
        backend: str = "auto",
    ) -> dict[str, Any]:
        """Identify node, element, or part entities and query their attributes and state results.

        Tasks: G04 (FEM > Element Tools > Identify).
        - Nodes: ID, reference & deformed coordinates, connected elements, belonging parts,
          state displacement/velocity.
        - Elements (solid, shell, beam, tshell): ID, type, connectivity, centroid,
          belonging part, material, and state results (Cauchy stress components, von Mises,
          effective plastic strain). Results are verified equivalent to Q03 extract_field.
        - Parts: ID, name/title, material reference, element count/breakdown, node count,
          bounding box, centroid, and active/deleted element count at state.

        Backend: 'auto', 'lasso' (for d3plot), 'keyword-engine' (for keyword files).
        Returns strict JobResult/v1.
        """
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Model path must be a non-empty string")
        if str(model).strip().startswith(("\\\\", "//")):
            raise ValueError(f"Network path {model!r} is not followed")

        # Resolve path safely using Settings
        source: Path
        if hasattr(self, "settings") and self.settings is not None:
            source = self.settings.input_path(model)
        else:
            source = Path(model).resolve(strict=True)

        norm_type = entity_type.strip().lower() if isinstance(entity_type, str) else ""
        if norm_type in ("nodes", "node"):
            target_domain = "node"
        elif norm_type in ("elements", "element"):
            target_domain = "element"
        elif norm_type in ("solid", "shell", "beam", "tshell"):
            target_domain = norm_type
        elif norm_type in ("parts", "part"):
            target_domain = "part"
        else:
            raise ValueError(
                f"Unsupported entity_type {entity_type!r}; allowed: 'node', 'element', 'part', 'solid', 'shell', 'beam', 'tshell'"
            )

        # Normalize entity_ids filter
        requested_ids: list[int] | None = None
        if entity_ids is not None:
            if isinstance(entity_ids, int):
                requested_ids = [entity_ids]
            elif isinstance(entity_ids, (list, tuple)):
                requested_ids = [int(x) for x in entity_ids]
            else:
                raise ValueError("entity_ids must be an integer, list of integers, or None")
            if any(x <= 0 for x in requested_ids):
                raise ValueError("entity_ids must be positive user IDs")

        # Normalize part_ids filter
        requested_parts: list[int] | None = None
        if part_ids is not None:
            if isinstance(part_ids, int):
                requested_parts = [part_ids]
            elif isinstance(part_ids, (list, tuple)):
                requested_parts = [int(p) for p in part_ids]
            else:
                raise ValueError("part_ids must be an integer or list of integers")

        # Normalize quantity
        norm_qty = quantity.strip().lower() if isinstance(quantity, str) and quantity.strip() else None
        if norm_qty:
            norm_qty = QUANTITY_ALIASES.get(norm_qty, norm_qty)

        # Normalize component
        norm_comp = component.strip().lower() if isinstance(component, str) and component.strip() else None

        # Determine backend / file format
        is_d3plot = (file_type.lower() == "d3plot") or (file_type == "auto" and _is_d3plot_path(source))

        if is_d3plot:
            return self._query_d3plot(
                source=source,
                target_domain=target_domain,
                requested_ids=requested_ids,
                requested_parts=requested_parts,
                state=state,
                quantity=norm_qty,
                component=norm_comp,
                offset=offset,
                limit=limit,
            )
        else:
            return self._query_keyword(
                source=source,
                target_domain=target_domain,
                requested_ids=requested_ids,
                requested_parts=requested_parts,
                state=state,
                quantity=norm_qty,
                component=norm_comp,
                offset=offset,
                limit=limit,
            )

    def _query_d3plot(
        self,
        source: Path,
        target_domain: str,
        requested_ids: list[int] | None,
        requested_parts: list[int] | None,
        state: int | None,
        quantity: str | None,
        component: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        """Identify entities from a LASSO-readable d3plot database."""
        arrays = lb._arrays(source)
        times = lb._times(arrays)
        n_states = int(times.size)

        # Validate 1-based state
        s_idx: int | None = None
        if state is not None:
            if not isinstance(state, int) or state < 1 or state > n_states:
                raise ValueError(f"State must be 1..{n_states}, got {state!r}")
            s_idx = state - 1

        state_time = float(times[s_idx]) if (s_idx is not None and s_idx < n_states) else None

        part_ids_arr = np.asarray(lb._part_ids(arrays), dtype=int).reshape(-1)
        part_titles_raw = lb._texts(arrays["part_titles"]) if "part_titles" in arrays else []
        part_title_map = {
            int(pid): part_titles_raw[i] if i < len(part_titles_raw) else None
            for i, pid in enumerate(part_ids_arr)
        }

        # Check companion keyword deck for material and section information
        companion_k_meta: dict[int, dict[str, Any]] = {}
        companion_mat_titles: dict[int, str] = {}
        for candidate_k in source.parent.glob("*.k"):
            try:
                k_data = _parse_keyword_mesh(candidate_k)
                companion_k_meta.update(k_data["parts_meta"])
                companion_mat_titles.update(k_data["mat_titles"])
                break
            except Exception:
                pass

        # Load node registry and initial coordinates
        if "node_ids" not in arrays or "node_coordinates" not in arrays:
            raise ValueError("d3plot database is missing essential node_ids or node_coordinates")
        node_ids = np.asarray(arrays["node_ids"], dtype=int).reshape(-1)
        node_lookup = {int(uid): i for i, uid in enumerate(node_ids)}
        node_coords = np.asarray(arrays["node_coordinates"], dtype=float)

        node_disp = np.asarray(arrays["node_displacement"], dtype=float) if "node_displacement" in arrays else None
        node_velo = np.asarray(arrays["node_velocity"], dtype=float) if "node_velocity" in arrays else None

        # Build element indexes across all families
        # family -> {ids, conn_indexes, part_indexes, stress, eps, alive}
        elements_by_family: dict[str, dict[str, Any]] = {}
        for family, (ids_key, alive_key, part_idx_key, history_key, stress_key, eps_key) in lb.FAMILIES.items():
            if ids_key not in arrays:
                continue
            f_ids = np.asarray(arrays[ids_key], dtype=int).reshape(-1)
            if not f_ids.size:
                continue
            conn_key = f"element_{family}_node_indexes"
            f_conn = np.asarray(arrays[conn_key], dtype=int) if conn_key in arrays else None
            f_part_idx = np.asarray(arrays[part_idx_key], dtype=int).reshape(-1) if part_idx_key in arrays else None
            f_stress = np.asarray(arrays[stress_key], dtype=float) if stress_key and stress_key in arrays else None
            f_eps = np.asarray(arrays[eps_key], dtype=float) if eps_key and eps_key in arrays else None
            f_alive = np.asarray(arrays[alive_key]) if alive_key in arrays else None
            elements_by_family[family] = {
                "ids": f_ids,
                "conn": f_conn,
                "part_idx": f_part_idx,
                "stress": f_stress,
                "eps": f_eps,
                "alive": f_alive,
            }

        # Build inverted node -> connected elements and parts map
        node_to_elements: dict[int, list[dict[str, Any]]] = {int(nid): [] for nid in node_ids}
        node_to_parts: dict[int, set[int]] = {int(nid): set() for nid in node_ids}

        for family, f_data in elements_by_family.items():
            f_ids = f_data["ids"]
            f_conn = f_data["conn"]
            f_pidx = f_data["part_idx"]
            if f_conn is None:
                continue
            for e_idx in range(len(f_ids)):
                eid = int(f_ids[e_idx])
                elem_part_id = int(part_ids_arr[f_pidx[e_idx]]) if f_pidx is not None else None
                node_sub_idxs = f_conn[e_idx]
                for nsub in node_sub_idxs:
                    if 0 <= nsub < len(node_ids):
                        nuid = int(node_ids[nsub])
                        node_to_elements[nuid].append({"type": family, "id": eid})
                        if elem_part_id is not None:
                            node_to_parts[nuid].add(elem_part_id)

        # -------------------------------------------------------------
        # DOMAIN: NODE
        # -------------------------------------------------------------
        if target_domain == "node":
            if requested_ids is not None:
                missing = [w for w in requested_ids if w not in node_lookup]
                if missing:
                    raise ValueError(f"Node ID(s) {missing[:10]} not found in model")
                selected_node_ids = requested_ids
            else:
                selected_node_ids = [int(x) for x in node_ids]

            # Optional filter by part_ids
            if requested_parts is not None:
                parts_set = set(requested_parts)
                selected_node_ids = [
                    nid for nid in selected_node_ids if node_to_parts[nid] & parts_set
                ]

            total_count = len(selected_node_ids)
            paged_ids = selected_node_ids[offset : offset + limit] if requested_ids is None else selected_node_ids

            entities_out = []
            for nid in paged_ids:
                n_idx = node_lookup[nid]
                ref_coord = [float(c) for c in node_coords[n_idx]]
                pids_list = sorted(node_to_parts[nid])
                pnames_list = [part_title_map.get(pid) for pid in pids_list]

                entity_dict: dict[str, Any] = {
                    "id": nid,
                    "coordinates": {"reference": ref_coord},
                    "part_ids": pids_list,
                    "part_names": pnames_list,
                    "connectivity": {
                        "connected_elements": node_to_elements[nid],
                        "element_count": len(node_to_elements[nid]),
                    },
                }

                if s_idx is not None:
                    # Deformed coordinates & displacement
                    def_coord = (
                        [float(c) for c in node_disp[s_idx, n_idx]]
                        if node_disp is not None
                        else None
                    )
                    entity_dict["coordinates"]["deformed"] = def_coord
                    disp_vec = (
                        [def_coord[k] - ref_coord[k] for k in range(3)]
                        if def_coord is not None
                        else None
                    )
                    disp_mag = (
                        float(math.sqrt(sum(d**2 for d in disp_vec)))
                        if disp_vec is not None
                        else None
                    )
                    velo_vec = (
                        [float(v) for v in node_velo[s_idx, n_idx]]
                        if node_velo is not None
                        else None
                    )
                    velo_mag = (
                        float(math.sqrt(sum(v**2 for v in velo_vec)))
                        if velo_vec is not None
                        else None
                    )

                    res_dict: dict[str, Any] = {
                        "state": state,
                        "state_1based": state,
                        "time": state_time,
                        "displacement": disp_vec,
                        "displacement_magnitude": disp_mag,
                    }
                    if velo_vec is not None:
                        res_dict["velocity"] = velo_vec
                        res_dict["velocity_magnitude"] = velo_mag

                    if quantity in ("displacement", "disp"):
                        if component in ("x", "y", "z") and disp_vec:
                            axis = {"x": 0, "y": 1, "z": 2}[component]
                            res_dict["quantity"] = f"displacement_{component}"
                            res_dict["value"] = disp_vec[axis]
                        elif component == "magnitude" or component is None:
                            res_dict["quantity"] = "displacement_magnitude"
                            res_dict["value"] = disp_mag
                        else:
                            res_dict["quantity"] = "displacement"
                            res_dict["value"] = disp_vec
                    elif quantity in ("velocity", "velo"):
                        if component in ("x", "y", "z") and velo_vec:
                            axis = {"x": 0, "y": 1, "z": 2}[component]
                            res_dict["quantity"] = f"velocity_{component}"
                            res_dict["value"] = velo_vec[axis]
                        elif component == "magnitude" or component is None:
                            res_dict["quantity"] = "velocity_magnitude"
                            res_dict["value"] = velo_mag
                        else:
                            res_dict["quantity"] = "velocity"
                            res_dict["value"] = velo_vec

                    entity_dict["results"] = res_dict

                entities_out.append(entity_dict)

            payload: dict[str, Any] = {
                "model": str(source),
                "entity_type": "node",
                "count": len(entities_out),
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "state": state,
                "entities": entities_out,
            }
            if len(entities_out) == 1:
                payload["entity"] = entities_out[0]
            return _result("query_entities", "succeeded", BACKEND_LASSO, payload, scope="d3plot database nodes")

        # -------------------------------------------------------------
        # DOMAIN: ELEMENT (or specific family)
        # -------------------------------------------------------------
        if target_domain in ("element", "solid", "shell", "beam", "tshell"):
            family_filter = None if target_domain == "element" else target_domain
            all_elements_meta: list[dict[str, Any]] = []

            for fam, f_data in elements_by_family.items():
                if family_filter is not None and fam != family_filter:
                    continue
                f_ids = f_data["ids"]
                f_conn = f_data["conn"]
                f_pidx = f_data["part_idx"]
                f_stress = f_data["stress"]
                f_eps = f_data["eps"]
                f_alive = f_data["alive"]

                for e_idx in range(len(f_ids)):
                    eid = int(f_ids[e_idx])
                    part_id = int(part_ids_arr[f_pidx[e_idx]]) if f_pidx is not None else None
                    if requested_parts is not None and part_id not in requested_parts:
                        continue

                    node_subs = f_conn[e_idx].tolist() if f_conn is not None else []
                    conn_node_ids = [int(node_ids[nsub]) for nsub in node_subs if 0 <= nsub < len(node_ids)]
                    elem_coords = [
                        [float(c) for c in node_coords[nsub]]
                        for nsub in node_subs
                        if 0 <= nsub < len(node_ids)
                    ]
                    centroid = (
                        [float(sum(col) / len(elem_coords)) for col in zip(*elem_coords)]
                        if elem_coords
                        else None
                    )

                    all_elements_meta.append({
                        "id": eid,
                        "family": fam,
                        "e_idx": e_idx,
                        "part_id": part_id,
                        "part_name": part_title_map.get(part_id) if part_id is not None else None,
                        "connected_node_ids": conn_node_ids,
                        "node_coordinates": elem_coords,
                        "centroid": centroid,
                        "f_data": f_data,
                    })

            # Filter by requested_ids
            if requested_ids is not None:
                elem_map = {item["id"]: item for item in all_elements_meta}
                missing = [w for w in requested_ids if w not in elem_map]
                if missing:
                    raise ValueError(f"Element ID(s) {missing[:10]} not found in model")
                selected_items = [elem_map[w] for w in requested_ids]
            else:
                selected_items = all_elements_meta

            total_count = len(selected_items)
            paged_items = selected_items[offset : offset + limit] if requested_ids is None else selected_items

            entities_out = []
            for item in paged_items:
                eid = item["id"]
                fam = item["family"]
                e_idx = item["e_idx"]
                pid = item["part_id"]
                pname = item["part_name"]
                conn_nodes = item["connected_node_ids"]
                centroid = item["centroid"]
                node_coords_list = item["node_coordinates"]
                f_data = item["f_data"]

                # Material resolution: cross-reference companion keyword deck if available, else explicit None with note
                mat_id = companion_k_meta.get(pid, {}).get("mid") if pid is not None else None
                mat_title = companion_mat_titles.get(mat_id) if mat_id is not None else None
                material_info = {
                    "material_id": mat_id,
                    "material_title": mat_title,
                    "note": None
                    if mat_id is not None
                    else "Material card details unavailable in d3plot database; cross-reference keyword deck for material properties",
                }

                entity_dict = {
                    "id": eid,
                    "element_type": fam,
                    "connectivity": {"node_ids": conn_nodes},
                    "coordinates": {
                        "centroid": centroid,
                        "node_coordinates": node_coords_list,
                    },
                    "part_id": pid,
                    "part_name": pname,
                    "material": material_info,
                }

                if s_idx is not None:
                    f_alive = f_data["alive"]
                    is_alive = bool(f_alive[s_idx, e_idx]) if f_alive is not None else True
                    entity_dict["is_alive"] = is_alive

                    f_stress = f_data["stress"]
                    f_eps = f_data["eps"]

                    res_dict: dict[str, Any] = {
                        "state": state,
                        "state_1based": state,
                        "time": state_time,
                        "is_alive": is_alive,
                    }

                    stress_comp_dict: dict[str, float] | None = None
                    vm_val: float | None = None
                    if f_stress is not None:
                        st = f_stress[s_idx, e_idx]
                        if st.ndim == 2:  # points x 6 -> average over integration points
                            st = st.mean(axis=0)
                        stress_comp_dict = {comp: float(st[i]) for i, comp in enumerate(STRESS_COMPONENTS)}
                        res_dict["stress"] = stress_comp_dict

                        # Invariants calculation (reusing domain.results.invariants for exact Q03/Q04 equivalence)
                        flat_st = st.reshape(1, 6)
                        invars = inv.invariants(flat_st)
                        vm_val = float(invars["von_mises"][0])
                        res_dict["von_mises"] = vm_val
                        res_dict["pressure"] = float(invars["pressure"][0])
                        res_dict["mean_stress"] = float(invars["mean_stress"][0])
                        res_dict["triaxiality"] = float(invars["triaxiality"][0])

                    eps_val: float | None = None
                    if f_eps is not None:
                        ep = f_eps[s_idx, e_idx]
                        if ep.ndim >= 1:
                            ep = ep.mean()
                        eps_val = float(ep)
                        res_dict["effective_plastic_strain"] = eps_val

                    # If specific quantity was requested
                    if quantity:
                        if quantity == "von_mises":
                            res_dict["quantity"] = "von_mises"
                            res_dict["value"] = vm_val
                        elif quantity == "effective_plastic_strain":
                            res_dict["quantity"] = "effective_plastic_strain"
                            res_dict["value"] = eps_val
                        elif quantity in STRESS_COMPONENTS and stress_comp_dict:
                            res_dict["quantity"] = quantity
                            res_dict["value"] = stress_comp_dict.get(quantity)
                        elif quantity in inv.QUANTITIES and f_stress is not None:
                            inv_val = float(invars[quantity][0])
                            res_dict["quantity"] = quantity
                            res_dict["value"] = inv_val

                    entity_dict["results"] = res_dict

                entities_out.append(entity_dict)

            payload = {
                "model": str(source),
                "entity_type": target_domain,
                "count": len(entities_out),
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "state": state,
                "entities": entities_out,
            }
            if len(entities_out) == 1:
                payload["entity"] = entities_out[0]
            return _result("query_entities", "succeeded", BACKEND_LASSO, payload, scope="d3plot database elements")

        # -------------------------------------------------------------
        # DOMAIN: PART
        # -------------------------------------------------------------
        if target_domain == "part":
            part_ids_list = [int(p) for p in part_ids_arr]
            if requested_ids is not None:
                missing = [w for w in requested_ids if w not in part_ids_list]
                if missing:
                    raise ValueError(f"Part ID(s) {missing[:10]} not found in model")
                selected_part_ids = requested_ids
            else:
                selected_part_ids = part_ids_list

            total_count = len(selected_part_ids)
            paged_part_ids = selected_part_ids[offset : offset + limit] if requested_ids is None else selected_part_ids

            entities_out = []
            for pid in paged_part_ids:
                p_idx = part_ids_list.index(pid)
                pname = part_titles_raw[p_idx] if p_idx < len(part_titles_raw) else None

                # Collect all elements and member nodes belonging to this part
                elem_ids_in_part: list[int] = []
                elem_types_breakdown: dict[str, int] = {}
                member_node_ids_set: set[int] = set()

                alive_count = 0
                deleted_count = 0

                for fam, f_data in elements_by_family.items():
                    f_ids = f_data["ids"]
                    f_conn = f_data["conn"]
                    f_pidx = f_data["part_idx"]
                    f_alive = f_data["alive"]
                    if f_pidx is None:
                        continue
                    in_part_mask = f_pidx == p_idx
                    if not np.any(in_part_mask):
                        continue
                    matching_ids = [int(f_ids[idx]) for idx in np.where(in_part_mask)[0]]
                    elem_ids_in_part.extend(matching_ids)
                    elem_types_breakdown[fam] = len(matching_ids)

                    if f_conn is not None:
                        for idx in np.where(in_part_mask)[0]:
                            for nsub in f_conn[idx]:
                                if 0 <= nsub < len(node_ids):
                                    member_node_ids_set.add(int(node_ids[nsub]))

                    if s_idx is not None and f_alive is not None:
                        for idx in np.where(in_part_mask)[0]:
                            if bool(f_alive[s_idx, idx]):
                                alive_count += 1
                            else:
                                deleted_count += 1

                # Calculate bounding box from member nodes
                member_coords = [
                    node_coords[node_lookup[nid]]
                    for nid in member_node_ids_set
                    if nid in node_lookup
                ]
                if member_coords:
                    coords_arr = np.asarray(member_coords, dtype=float)
                    bbox = {
                        "min": [float(c) for c in coords_arr.min(axis=0)],
                        "max": [float(c) for c in coords_arr.max(axis=0)],
                    }
                    centroid = [float(c) for c in coords_arr.mean(axis=0)]
                else:
                    bbox = None
                    centroid = None

                mat_id = companion_k_meta.get(pid, {}).get("mid")
                mat_title = companion_mat_titles.get(mat_id) if mat_id is not None else None
                material_info = {
                    "material_id": mat_id,
                    "material_title": mat_title,
                    "note": None
                    if mat_id is not None
                    else "Material card details unavailable in d3plot database; cross-reference keyword deck for material properties",
                }

                entity_dict = {
                    "id": pid,
                    "name": pname,
                    "material": material_info,
                    "elements": {
                        "count": len(elem_ids_in_part),
                        "types": elem_types_breakdown,
                        "element_ids": elem_ids_in_part,
                    },
                    "nodes": {
                        "count": len(member_node_ids_set),
                        "node_ids": sorted(member_node_ids_set),
                    },
                    "coordinates": {
                        "bounding_box": bbox,
                        "centroid": centroid,
                    },
                }

                if s_idx is not None:
                    entity_dict["results"] = {
                        "state": state,
                        "state_1based": state,
                        "time": state_time,
                        "active_element_count": alive_count,
                        "deleted_element_count": deleted_count,
                    }

                entities_out.append(entity_dict)

            payload = {
                "model": str(source),
                "entity_type": "part",
                "count": len(entities_out),
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "state": state,
                "entities": entities_out,
            }
            if len(entities_out) == 1:
                payload["entity"] = entities_out[0]
            return _result("query_entities", "succeeded", BACKEND_LASSO, payload, scope="d3plot database parts")

        raise ValueError(f"Unsupported query domain {target_domain!r}")

    def _query_keyword(
        self,
        source: Path,
        target_domain: str,
        requested_ids: list[int] | None,
        requested_parts: list[int] | None,
        state: int | None,
        quantity: str | None,
        component: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        """Identify entities from a Keyword deck (*.k, *.key)."""
        k_data = _parse_keyword_mesh(source)
        nodes = k_data["nodes"]
        elements = k_data["elements"]
        parts_meta = k_data["parts_meta"]
        mat_titles = k_data["mat_titles"]

        # Build node -> connected elements and parts
        node_to_elements: dict[int, list[dict[str, Any]]] = {nid: [] for nid in nodes}
        node_to_parts: dict[int, set[int]] = {nid: set() for nid in nodes}

        for el in elements:
            eid = el["id"]
            pid = el["part_id"]
            for nid in el["nodes"]:
                if nid in node_to_elements:
                    node_to_elements[nid].append({"type": el["type"], "id": eid})
                    node_to_parts[nid].add(pid)

        # -------------------------------------------------------------
        # DOMAIN: NODE
        # -------------------------------------------------------------
        if target_domain == "node":
            if requested_ids is not None:
                missing = [w for w in requested_ids if w not in nodes]
                if missing:
                    raise ValueError(f"Node ID(s) {missing[:10]} not found in keyword deck")
                selected_node_ids = requested_ids
            else:
                selected_node_ids = sorted(nodes)

            if requested_parts is not None:
                parts_set = set(requested_parts)
                selected_node_ids = [
                    nid for nid in selected_node_ids if node_to_parts[nid] & parts_set
                ]

            total_count = len(selected_node_ids)
            paged_ids = selected_node_ids[offset : offset + limit] if requested_ids is None else selected_node_ids

            entities_out = []
            for nid in paged_ids:
                ref_coord = nodes[nid]
                pids_list = sorted(node_to_parts[nid])
                pnames_list = [parts_meta.get(pid, {}).get("name") for pid in pids_list]

                entity_dict: dict[str, Any] = {
                    "id": nid,
                    "coordinates": {"reference": ref_coord, "deformed": None},
                    "part_ids": pids_list,
                    "part_names": pnames_list,
                    "connectivity": {
                        "connected_elements": node_to_elements[nid],
                        "element_count": len(node_to_elements[nid]),
                    },
                    "results": None
                    if state is None
                    else {"note": "Keyword deck does not contain simulation state results; use d3plot for state results"},
                }
                entities_out.append(entity_dict)

            payload = {
                "model": str(source),
                "entity_type": "node",
                "count": len(entities_out),
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "entities": entities_out,
            }
            if len(entities_out) == 1:
                payload["entity"] = entities_out[0]
            return _result("query_entities", "succeeded", BACKEND_KEYWORD, payload, scope="keyword deck nodes")

        # -------------------------------------------------------------
        # DOMAIN: ELEMENT
        # -------------------------------------------------------------
        if target_domain in ("element", "solid", "shell", "beam", "tshell"):
            family_filter = None if target_domain == "element" else target_domain
            selected_elements = [
                el for el in elements if family_filter is None or el["type"] == family_filter
            ]
            if requested_parts is not None:
                selected_elements = [el for el in selected_elements if el["part_id"] in requested_parts]

            if requested_ids is not None:
                el_map = {el["id"]: el for el in selected_elements}
                missing = [w for w in requested_ids if w not in el_map]
                if missing:
                    raise ValueError(f"Element ID(s) {missing[:10]} not found in keyword deck")
                selected_elements = [el_map[w] for w in requested_ids]

            total_count = len(selected_elements)
            paged_elements = selected_elements[offset : offset + limit] if requested_ids is None else selected_elements

            entities_out = []
            for el in paged_elements:
                eid = el["id"]
                fam = el["type"]
                pid = el["part_id"]
                conn_nodes = el["nodes"]
                elem_coords = [nodes[n] for n in conn_nodes if n in nodes]
                centroid = (
                    [float(sum(col) / len(elem_coords)) for col in zip(*elem_coords)]
                    if elem_coords
                    else None
                )

                pmeta = parts_meta.get(pid, {})
                mat_id = pmeta.get("mid")
                mat_title = mat_titles.get(mat_id) if mat_id is not None else None

                entity_dict = {
                    "id": eid,
                    "element_type": fam,
                    "connectivity": {"node_ids": conn_nodes},
                    "coordinates": {
                        "centroid": centroid,
                        "node_coordinates": elem_coords,
                    },
                    "part_id": pid,
                    "part_name": pmeta.get("name"),
                    "material": {
                        "material_id": mat_id,
                        "material_title": mat_title,
                        "section_id": pmeta.get("secid"),
                    },
                    "results": None
                    if state is None
                    else {"note": "Keyword deck does not contain simulation state results; use d3plot for state results"},
                }
                entities_out.append(entity_dict)

            payload = {
                "model": str(source),
                "entity_type": target_domain,
                "count": len(entities_out),
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "entities": entities_out,
            }
            if len(entities_out) == 1:
                payload["entity"] = entities_out[0]
            return _result("query_entities", "succeeded", BACKEND_KEYWORD, payload, scope="keyword deck elements")

        # -------------------------------------------------------------
        # DOMAIN: PART
        # -------------------------------------------------------------
        if target_domain == "part":
            all_pids = sorted(parts_meta.keys() | {el["part_id"] for el in elements})
            if requested_ids is not None:
                missing = [w for w in requested_ids if w not in all_pids]
                if missing:
                    raise ValueError(f"Part ID(s) {missing[:10]} not found in keyword deck")
                selected_pids = requested_ids
            else:
                selected_pids = all_pids

            total_count = len(selected_pids)
            paged_pids = selected_pids[offset : offset + limit] if requested_ids is None else selected_pids

            entities_out = []
            for pid in paged_pids:
                pmeta = parts_meta.get(pid, {})
                mat_id = pmeta.get("mid")
                mat_title = mat_titles.get(mat_id) if mat_id is not None else None

                elem_ids_in_part = [el["id"] for el in elements if el["part_id"] == pid]
                types_breakdown: dict[str, int] = {}
                member_nodes: set[int] = set()
                for el in elements:
                    if el["part_id"] == pid:
                        types_breakdown[el["type"]] = types_breakdown.get(el["type"], 0) + 1
                        member_nodes.update(el["nodes"])

                member_coords = [nodes[n] for n in member_nodes if n in nodes]
                if member_coords:
                    coords_arr = np.asarray(member_coords, dtype=float)
                    bbox = {
                        "min": [float(c) for c in coords_arr.min(axis=0)],
                        "max": [float(c) for c in coords_arr.max(axis=0)],
                    }
                    centroid = [float(c) for c in coords_arr.mean(axis=0)]
                else:
                    bbox = None
                    centroid = None

                entity_dict = {
                    "id": pid,
                    "name": pmeta.get("name"),
                    "material": {
                        "material_id": mat_id,
                        "material_title": mat_title,
                        "section_id": pmeta.get("secid"),
                    },
                    "elements": {
                        "count": len(elem_ids_in_part),
                        "types": types_breakdown,
                        "element_ids": elem_ids_in_part,
                    },
                    "nodes": {
                        "count": len(member_nodes),
                        "node_ids": sorted(member_nodes),
                    },
                    "coordinates": {
                        "bounding_box": bbox,
                        "centroid": centroid,
                    },
                    "results": None
                    if state is None
                    else {"note": "Keyword deck does not contain simulation state results; use d3plot for state results"},
                }
                entities_out.append(entity_dict)

            payload = {
                "model": str(source),
                "entity_type": "part",
                "count": len(entities_out),
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "entities": entities_out,
            }
            if len(entities_out) == 1:
                payload["entity"] = entities_out[0]
            return _result("query_entities", "succeeded", BACKEND_KEYWORD, payload, scope="keyword deck parts")

        raise ValueError(f"Unsupported query domain {target_domain!r}")


__all__ = ["EntityIdentifyTools"]
