import hashlib
import struct

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.gui_visibility import flags, transitions
from ls_prepost_mcp.service import Service


def binary(tmp_path, records):
    data = b"".join(struct.pack("!BqB", *record) for record in records)
    (tmp_path/"visibility.bin").write_bytes(data)
    return dict(counts=dict(elements=len(records)), visibility_binary=dict(format="native_display_active_v1",
        file="visibility.bin", record_format="!BqB", count=len(records), byte_count=len(data), sha256=hashlib.sha256(data).hexdigest()))


def test_binary_visibility_preserves_identity_and_rejects_corruption(tmp_path):
    metadata = binary(tmp_path, [(3, 9000001, 1), (2, 5, 0)])
    assert flags(metadata, tmp_path) == {("solid", 9000001): True, ("shell", 5): False}
    (tmp_path/"visibility.bin").write_bytes(bytes(20))
    with pytest.raises(ValueError):
        flags(metadata, tmp_path)
    for records in ([(3, 1, 1), (3, 1, 0)], [(3, 1, 2)], [(4, 1, 1)]):
        with pytest.raises(ValueError):
            flags(binary(tmp_path, records), tmp_path)
    metadata = binary(tmp_path, [(3, 1, 1)])
    metadata["visibility_binary"]["sha256"] = "wrong"
    with pytest.raises(ValueError, match="hash"):
        flags(metadata, tmp_path)


def execute_mask_commands(commands, old):
    values, selected = dict(old), set()
    for command in commands:
        words = command.split()
        if command == "genselect clear":
            selected.clear()
        elif words[:3] == ["genselect", "target", "element"]:
            continue
        elif len(words) == 5 and words[:3] == ["genselect", "element", "add"]:
            selected.add(int(words[-1]))
        elif command == "blank selection":
            values.update({key: False for key in values if key[1] in selected})
        elif words[0] in ("blank", "unblank"):
            for key in values:
                if key[0] == "solid":
                    values[key] = not values[key] if words[1] == "reverse" else words[0] == "unblank"
        else:
            raise AssertionError(command)
    return values


def test_all_small_boolean_transitions_preserve_other_domains():
    # Exhaustively prove the reset/complement optimizer for heterogeneous masks.
    for a in range(16):
        for b in range(16):
            old = {("solid", i+1): bool(a & (1 << i)) for i in range(4)}
            old[("shell", 10)] = False
            desired = dict(old, **{})
            desired.update({("solid", i+1): bool(b & (1 << i)) for i in range(4)})
            assert execute_mask_commands(transitions("solid", old, desired), old) == desired


def test_tiny_isolation_in_large_domain_has_bounded_native_command_count():
    old = {("solid", i+1): True for i in range(100001)}
    desired = {key: key[1] in (5, 50000, 99999) for key in old}
    commands = transitions("solid", old, desired)
    assert len(commands) < 15
    assert execute_mask_commands(commands, old) == desired


@pytest.mark.parametrize("kind,mode,ids", [("node", "hide", [1]), ("solid", "bad", []), ("solid", "hide", [True]), ("solid", "restore_last", [1])])
def test_unsupported_visibility_never_launches(tmp_path, kind, mode, ids):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).set_gui_entity_visibility("missing", kind, mode, ids)
    assert not list(tmp_path.iterdir())
