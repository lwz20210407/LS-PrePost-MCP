"""P04 public Include-tree replay; never a solver/native or private-corpus claim."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from ls_prepost_mcp.domain.model import KeywordDeck, access
from ls_prepost_mcp.domain.model.includes import is_network
from ls_prepost_mcp.domain.model.node_sets import NodeSets
from ls_prepost_mcp.domain.model.operations import edit_deck
from tools.fetch_corpus import entries, load_registry, plain_path, resolve

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(case_id, corpus, output):
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("Commit the verifier/product first; evidence requires a clean checkout")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if is_network(str(corpus)) or is_network(str(output)):
        raise ValueError("Network corpus/output paths are not followed")
    corpus, output = plain_path(corpus).resolve(strict=True), output.resolve()
    if output.is_relative_to(ROOT) or output.is_relative_to(corpus) or output.exists():
        raise ValueError("Use a fresh external output directory outside the repository and original corpus")
    source = plain_path(resolve(entries(load_registry())[case_id], corpus))
    guard = access.root_guard((corpus, output))
    with access.confined(guard):
        deck = KeywordDeck.load(source)
        index = NodeSets(deck)
        ids = index.ids.tolist()
        if len(ids) < 2:
            raise ValueError("Public replay requires at least two nodes")
        before = {str(file.path): hashlib.sha256(file.original).hexdigest() for file in deck.files.values()}
        folders = {file.path.parent for file in deck.files.values()}
        listing = {folder: sorted(path.name for path in folder.iterdir()) for folder in folders}
        start = max(index.blocks, default=0) + 1
        low, high = ids[0] - 1, ids[min(10, len(ids)-1)] + 1
        # Independent bounded fixture oracle over known mesh IDs, not the production resolver.
        expected = [uid for uid in ids if low <= uid <= high]
        requests = [
            dict(op="create_set", kind="node", sid=start, ids=[expected[-1], expected[0]]),
            dict(op="create_set", kind="node", sid=start+1, representation="generate", ranges=[[low, high]], title="public ranges"),
            dict(op="create_set", kind="node", sid=start+2, representation="generate_increment",
                 ranges=[dict(begin=ids[0], end=ids[1], increment=ids[1]-ids[0])]),
            dict(op="create_set", kind="node", sid=start+3, representation="add", set_ids=[start+1, start, start+2]),
        ]
        result = edit_deck(str(source), requests, output_dir=str(output / "saved"))
        if result["status"] != "succeeded":
            raise ValueError("Public node-set replay failed: " + str(result.get("error")))
        saved = KeywordDeck.load(result["save"]["main"])
        resolved = NodeSets(saved)
        assert resolved.resolve(start) == [expected[-1], expected[0]]
        assert resolved.resolve(start+1) == resolved.resolve(start+3) == expected
        assert resolved.resolve(start+2) == ids[:2]
        assert resolved.definition(start+3).operands == (start+1, start, start+2)
        assert not saved.references(False).node_set_cycles
        assert all(digest(Path(path)) == sha for path, sha in before.items())
        assert {folder: sorted(path.name for path in folder.iterdir()) for folder in folders} == listing
    product_paths = ["src/ls_prepost_mcp/domain/model/" + name for name in (
        "node_sets.py", "sets.py", "selectors.py", "compare.py", "contact.py", "operations.py", "references.py", "loads.py", "_identity.py")]
    identities = [dict(path=path, git_blob_id=subprocess.check_output(
        ["git", "rev-parse", revision + ":" + path], cwd=ROOT, text=True).strip()) for path in product_paths]
    report = dict(status="passed", verification_level="L1", source_id=case_id,
        actual_git_revision=revision, working_tree_dirty=False, git_diff_sha256=hashlib.sha256(b"").hexdigest(),
        native_executed=False, solver_executed=False, original_files=len(before), original_bytes=sum(len(f.original) for f in deck.files.values()),
        node_count=len(ids), generated_members=len(expected), created_definitions=4,
        include_tree_bytes_unchanged=True, source_directory_lists_unchanged=True,
        original_source_sha256=sorted(before.values()), product_source_identity=identities,
        roles=["public_registered_Include_tree", "independent_ID_filter_oracle", "AST_save_reload"],
        limits=["Not native member expansion or P04 completion", "Two-point increment has no unverified holes"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="include_contact")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(args.case, args.corpus, args.output)
