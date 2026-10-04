import pytest

from ls_prepost_mcp.checkpoint_context import save_checkpoint_context
from ls_prepost_mcp.resident_models import (
    matching_resident_row,
    matching_row,
    owned_target,
    remember_model,
    source_candidates,
    verify_context,
)


def test_contexts_follow_managed_sources_without_retaining_row_ids():
    meta = dict(
        source="F:/original.k",
        staged_model="F:/job/a/model.k",
        model_kind="keyword",
        last_checkpoint="F:/checkpoint.k",
    )
    remember_model(meta)
    assert owned_target(meta, "f:\\job\\a\\model.k")["last_checkpoint"] == "F:/checkpoint.k"
    meta.update(staged_model="F:/job/b/d3plot", model_kind="d3plot", last_checkpoint=None)
    remember_model(meta)
    assert owned_target(meta, "F:/job/a/model.k")["model_kind"] == "keyword"
    assert owned_target(meta, "F:/job/b/d3plot")["last_checkpoint"] is None
    with pytest.raises(ValueError, match="managed"):
        owned_target(meta, "F:/unmanaged.k")


def test_matching_source_rejects_missing_and_duplicate_rows():
    rows = [dict(row_index=1, path="F:/a.k"), dict(row_index=2, path=None)]
    assert matching_row(rows, "f:\\a.k")["row_index"] == 1
    with pytest.raises(ValueError, match="ambiguous"):
        matching_row(rows, "F:/absent.k")
    with pytest.raises(ValueError, match="ambiguous"):
        matching_row(rows + [dict(row_index=3, path="f:/A.k")], "F:/a.k")


def test_context_verification_rejects_wrong_source_and_result_association():
    ctx = dict(staged_model="F:/job/a/model.k", model_kind="keyword")
    native = dict(model_directory="F:/job/a/model.k", counts=dict(nodes=0, elements=0, states=0))
    assert verify_context(ctx, native)["empty_model_verified"]
    with pytest.raises(ValueError, match="match"):
        verify_context(ctx, dict(native, model_directory="F:/job/b/model.k"))
    with pytest.raises(ValueError, match="multi-state"):
        verify_context(ctx, dict(native, counts=dict(nodes=8, elements=1, states=3)))


def test_saved_directory_alias_requires_owned_unchanged_checkpoint(tmp_path):
    folder = tmp_path / "saved"
    folder.mkdir()
    checkpoint = folder / "model.k"
    checkpoint.write_text("*KEYWORD\n*END\n")
    native = dict(model_directory=str(folder), counts=dict(nodes=0, elements=0, states=0))
    context = dict(
        staged_model=str(tmp_path / "original" / "model.k"),
        model_kind="keyword",
        last_checkpoint=str(checkpoint),
    )
    with pytest.raises(ValueError, match="file-bound"):
        verify_context(context, native, "owned-session")
    save_checkpoint_context(checkpoint, "owned-session", native, tmp_path)
    assert verify_context(context, native, "owned-session")["empty_model_verified"]
    remember_model(context)
    assert owned_target(context, str(checkpoint), "owned-session")["staged_model"] == context["staged_model"]
    row = dict(row_index=3, path=str(checkpoint))
    assert matching_resident_row([row], context, "owned-session") == row
    with pytest.raises(ValueError, match="ambiguous"):
        matching_resident_row(
            [row, dict(row_index=4, path=context["staged_model"])], context, "owned-session"
        )
    with pytest.raises(ValueError, match="foreign"):
        verify_context(context, native, "different-session")
    checkpoint.write_text("*KEYWORD\n*NODE\n1,0,0,0\n*END\n")
    with pytest.raises(ValueError, match="changed"):
        verify_context(context, native, "owned-session")


def test_reset_undo_checkpoint_is_not_identity_of_new_empty_model():
    context = dict(
        staged_model="F:/reset/initial.k",
        model_kind="keyword",
        reset_recovery_source="F:/reset/initial.k",
        reset_rollback_checkpoint="F:/old/model.k",
        last_checkpoint="F:/old/model.k",
        last_verified_source="F:/old/model.k",
    )
    assert source_candidates(context) == ["F:/reset/initial.k"]
    native = dict(model_directory="F:/old", counts=dict(nodes=8, elements=1, states=1))
    with pytest.raises(ValueError, match="match"):
        verify_context(context, native, "owned-session")
