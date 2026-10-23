"""Review02 help must distinguish current tracked limits from historical acceptance dumps."""
import json
import re
import subprocess
from pathlib import Path


def current(pytestconfig):
    return (Path(pytestconfig.rootpath) / "docs/KNOWN_ISSUES.md").read_text(encoding="utf8")


def test_current_issues_do_not_duplicate_the_runtime_capability_catalog(pytestconfig):
    text = current(pytestconfig)
    assert "## 能力范围原文索引" not in text
    assert "## 已扫描源文件" not in text


def test_current_index_guidance_does_not_advertise_the_superseded_tokenizer(pytestconfig):
    section = current(pytestconfig).split("## I05：", 1)[-1]
    assert "identifier-parts-v2" in section
    assert "identifier-parts-v1 标记新构建口径" not in section


def test_each_current_issue_section_has_a_task_owner_reference(pytestconfig):
    import yaml

    root = Path(pytestconfig.rootpath)
    catalog = yaml.safe_load((root / "tasks.yaml").read_text(encoding="utf8"))
    ids = {item["id"] for key in ("tasks", "infrastructure") for item in catalog[key]}
    for section in re.split(r"(?m)^## ", current(pytestconfig))[1:]:
        assert "- 跟踪：" in section, section.splitlines()[0]
        line = next(line for line in section.splitlines() if line.startswith("- 跟踪："))
        linked = set(re.findall(r"\b(?:I|P|Q|A|G)\d{2}\b", line))
        assert linked and linked <= ids


def test_known_source_captures_each_bind_their_own_executed_git_revision(pytestconfig):
    import pytest

    root = Path(pytestconfig.rootpath)
    probe = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root, text=True, capture_output=True)
    if probe.returncode or probe.stdout.strip() == "true":
        pytest.skip("Known-source snapshot identities require full Git history")
    evidence = json.loads((root / "docs/decisions/evidence/i06-known-review02/evidence.json").read_text(encoding="utf8"))
    for capture in [evidence, *evidence.get("previous_captures", [])]:
        assert capture["working_tree_dirty"] is False
        for item in capture["source_identity"]:
            actual = subprocess.check_output(["git", "rev-parse", capture["actual_git_revision"]+":"+item["path"]], cwd=root, text=True).strip()
            assert actual == item["git_blob_id"]
