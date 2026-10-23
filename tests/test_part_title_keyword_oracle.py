"""Review02 P0-1: external keyword PART definitions, not a second zip of result title arrays."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from ls_prepost_mcp.domain.results import lasso_backend as lb
from tools.fetch_corpus import entries, load_registry, plain_path, resolve

CASES = [
    ("result.jascott4427__PILLARS-LSDyna.pillars_v2_airbag_open.keyfiles.100.30", "open_airbag_v136.k"),
    ("result.hu-shuhan__editOpeniGame.test.Format_Validation_Test.lsdyna.Bolt_B_Explicit", "mainboltbexpl.k"),
    ("result.saudbinayed__binout.LS-DYNA-sample", "plane_strain_impact.k"),
]


@pytest.mark.parametrize("corpus_id,keyword", CASES)
def test_real_result_titles_match_paired_keyword_parts(corpus_id, keyword):
    location = os.environ.get("LSPP_CORPUS_DIR")
    if not location:
        pytest.skip("Set LSPP_CORPUS_DIR for independent public PART/title verification")
    pytest.importorskip("lasso.dyna")
    pytest.importorskip("ansys.dyna.core")
    from ls_prepost_mcp.domain.model import KeywordDeck, access
    from ls_prepost_mcp.domain.model.includes import is_network

    root = plain_path(Path(location))
    directory = plain_path(resolve(entries(load_registry())[corpus_id], root))
    public_roots = (root / "public-results", root / "public-keyword")

    def public_path(path):
        candidate = Path(os.path.normpath(os.path.abspath(path)))
        if is_network(str(path)) or not any(candidate.is_relative_to(base) for base in public_roots):
            raise access.OutsideRoots("Oracle input is outside public corpus roots")
        if not any(candidate.resolve().is_relative_to(base) for base in public_roots):
            raise access.OutsideRoots("Oracle input link escapes public corpus roots")

    with access.confined(public_path):
        deck = KeywordDeck.load(directory / keyword)
    original = {p.path: hashlib.sha256(p.original).hexdigest() for p in deck.files.values()}
    source = directory / "d3plot"
    family = [
        source,
        *sorted(p for p in directory.iterdir() if p.name.startswith("d3plot") and p.name[6:].isdigit()),
    ]

    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    for path in family:
        public_path(path)
    source_hashes = {p: digest(p) for p in family}
    expected = {}
    for block in deck.iter_blocks():
        if block.name == "*PART":
            for pid in deck.layout(block).rows:
                expected[int(pid)] = deck.get(block, "heading", row=pid).value.strip()
        elif block.name == "*PART_CONTACT":
            expected[int(deck.get(block, "pid").value)] = deck.get(block, "title").value.strip()
    arrays = lb._arrays(directory / "d3plot", state_arrays=["timesteps"])
    actual, warnings = lb._part_titles(arrays)
    ids = [int(p) for p in arrays["part_ids"]]
    assert set(ids) <= set(expected), (
        "Paired keyword lacks the result's Parts; this is not a complete title oracle"
    )
    assert {uid: actual.get(uid) for uid in ids} == {uid: expected[uid] for uid in ids}
    assert not warnings
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == sha for path, sha in original.items())
    assert all(digest(path) == sha for path, sha in source_hashes.items())
    capture = os.environ.get("LSPP_TITLE_EVIDENCE_DIR")
    if capture:
        repo = Path(__file__).resolve().parents[1]
        output = Path(capture).resolve()
        assert not output.is_relative_to(repo)
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo)
        product_paths = [
            "src/ls_prepost_mcp/domain/results/lasso_backend.py",
            "src/ls_prepost_mcp/result_overview.py",
            "src/ls_prepost_mcp/domain/model/deck.py",
            "src/ls_prepost_mcp/domain/model/fields.py",
            "src/ls_prepost_mcp/domain/model/layouts.py",
        ]
        identities = [
            dict(
                path=path,
                git_blob_id=subprocess.check_output(
                    ["git", "rev-parse", revision + ":" + path], cwd=repo, text=True
                ).strip(),
            )
            for path in product_paths
        ]
        proof = dict(
            corpus_id=corpus_id,
            keyword=keyword,
            actual_git_revision=revision,
            working_tree_dirty=False,
            product_source_identity=identities,
            part_count=len(ids),
            part_ids=ids,
            title_mapping_source=lb._part_title_association(arrays)[2],
            oracle="KeywordDeck.get on PART.heading and PART_CONTACT.title; never result title-ID zip",
            titles_equal_keyword=True,
            keyword_tree_unchanged=True,
            result_family_unchanged=True,
            keyword_source_sha256={p.relative_to(root).as_posix(): sha for p, sha in original.items()},
            result_source_sha256={p.name: sha for p, sha in source_hashes.items()},
        )
        output.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(corpus_id.encode()).hexdigest()[:12] + ".json"
        with (output / name).open("x", encoding="utf8") as stream:
            json.dump(proof, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
