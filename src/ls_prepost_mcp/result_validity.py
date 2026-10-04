"""Physical deletion masks keyed by domain, saved state and user ID, never GUI flags."""

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .post_backend import selected_database


def mask_name(domain):
    if domain not in ("shell", "solid", "tshell", "beam"):
        raise ValueError("Physical deletion filtering requires an element domain; nodal visibility is a different contract")
    return "element_" + domain + "_is_alive"


def validity_policy(value):
    if value not in ("raw", "alive"):
        raise ValueError("validity_policy must be raw or alive")
    return value


def validity_scope(policy):
    return ("Physical deletion filtering: LASSO2.0.4 MDLOPT2 table; positive material code=present,0=deleted; ID/state aligned"
            if validity_policy(policy) == "alive" else
            "Raw stored population; physical deletion filtering not requested; extrema are not alive-only")


@dataclass
class PhysicalValidity:
    domain: str
    user_ids: np.ndarray
    mask: np.ndarray
    state_rows: dict
    times: np.ndarray

    def __post_init__(self):
        mask_name(self.domain)
        self.user_ids = np.asarray(self.user_ids)
        self.mask = np.asarray(self.mask)
        self.times = np.asarray(self.times)
        if (self.user_ids.ndim != 1 or self.user_ids.dtype.kind not in "iu"
                or np.any(self.user_ids <= 0) or len(np.unique(self.user_ids)) != len(self.user_ids)):
            raise ValueError("Invalid physical-mask user-ID registry")
        if (self.mask.shape != (len(self.state_rows), len(self.user_ids))
                or self.times.shape != (len(self.state_rows),)
                or sorted(self.state_rows.values()) != list(range(len(self.state_rows)))
                or any(type(i) is not int for i in self.state_rows.values())
                or any(type(s) is not int or s < 1 for s in self.state_rows)
                or not np.isfinite(self.times).all()):
            raise ValueError("Physical-mask state/entity axes do not align")
        if (not np.isfinite(self.mask).all() or np.any(self.mask < 0)
                or np.any(self.mask != np.floor(self.mask))):
            raise ValueError("MDLOPT2 deletion table requires zero or positive integral material codes")
        self.active_codes = {state: [int(v) for v in np.unique(self.mask[row]) if v > 0][:20]
                             for state, row in self.state_rows.items()}
        self.mask = self.mask > 0
        self.lookup = {int(uid): i for i, uid in enumerate(self.user_ids)}

    def indices(self, user_ids):
        if len(set(user_ids)) != len(user_ids) or any(uid not in self.lookup for uid in user_ids):
            raise ValueError("Requested user IDs absent/duplicated in physical-mask registry")
        return np.asarray([self.lookup[uid] for uid in user_ids], dtype=np.int64)

    def alive(self, state, uid):
        return bool(self.mask[self.state_rows[state], self.lookup[uid]])

    def check_time(self, state, value):
        if not np.isclose(value, self.times[self.state_rows[state]], rtol=2e-7, atol=0):
            raise ValueError("Native and physical-mask saved-state times disagree")

    def describe(self, user_ids, states):
        indexes = self.indices(user_ids)
        rows = []
        for state in states:
            whole = self.mask[self.state_rows[state]]
            selected = whole[indexes]
            rows.append(dict(state=state, time=float(self.times[self.state_rows[state]]),
                             requested_count=len(user_ids), alive_count=int(selected.sum()),
                             deleted_count=int((~selected).sum()),
                             domain_alive_count=int(whole.sum()), domain_deleted_count=int((~whole).sum()),
                             active_material_code_sample=self.active_codes[state]))
        return dict(backend="lasso2.0.4_physical_deletion", mask_field=mask_name(self.domain),
                    domain=self.domain, id_kind="user", public_state_base=1, active_encoding="positive material code", deleted_value=0,
                    registered_count=len(self.user_ids), states=rows,
                    scope="Saved deletion flags only; not display Blank, material damage threshold, rigidity or variable availability")


def mask_from_database(db, mapping, domain):
    header = db.header
    if header.n_adapted_element_pairs:
        raise ValueError("Adaptive physical ID mapping needs a separate verified contract")
    field = mask_name(domain)
    if not header.has_element_deletion_data or field not in db.arrays:
        raise ValueError("Physical deletion mask unavailable for this domain; cannot infer alive status from display or missing records")
    key = "node_ids" if domain == "node" else "element_" + domain + "_ids"
    return PhysicalValidity(domain, db.arrays[key], db.arrays[field], mapping, db.arrays["timesteps"])


def load_physical_validity(path, states, domain):
    reject_adaptive_family(path)
    db, mapping = selected_database(path, states, [mask_name(domain)])
    return mask_from_database(db, mapping, domain)


def reject_adaptive_family(path):
    path = Path(path)
    pattern = re.compile(re.escape(path.name) + r"[a-z]{2}(?:\d+)?", re.IGNORECASE)
    if any(p.is_file() and pattern.fullmatch(p.name) for p in path.parent.iterdir()):
        raise ValueError("Adaptive mesh families need explicit epoch/ID mapping; select and validate one mesh epoch separately")


class ScalarStatistics:
    """Streaming retained-row extrema; ties choose the lowest state/user ID."""
    def __init__(self, fields):
        self.output = {field: dict(count=0, minimum=None, maximum=None) for field in fields}

    def add(self, row, id_column="entity_id"):
        for field, summary in self.output.items():
            if row[field] is None or row[field] == "":
                continue
            value = float(row[field])
            if not np.isfinite(value):
                raise ValueError("Nonfinite retained result: " + field)
            point = dict(value=value, state=int(row["state"]), entity_id=int(row[id_column]))
            summary["count"] += 1
            for key, sign in (("minimum", 1), ("maximum", -1)):
                old = summary[key]
                if old is None or (sign*value, point["state"], point["entity_id"]) < (sign*old["value"], old["state"], old["entity_id"]):
                    summary[key] = point


def scalar_statistics(rows, fields, id_column="entity_id"):
    stats = ScalarStatistics(fields)
    for row in rows:
        stats.add(row, id_column)
    return stats.output
