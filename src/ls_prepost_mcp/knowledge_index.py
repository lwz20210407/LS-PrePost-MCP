"""I05 source-attributed local reference index. Indexed text is never executable."""

import csv
import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path

from .keyword_documentation import KeywordField

CATEGORIES = frozenset(("command", "api", "keyword", "user_guide", "recipe", "known_issue"))
PUBLIC_LICENSES = frozenset(("MIT", "Apache-2.0", "BSD-3-Clause", "CC0-1.0"))
REPOSITORY = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Document:
    source_id: str
    category: str
    title: str
    text: str
    locator: str
    license: str
    visibility: str = "private"
    version: str = "unspecified"
    line_start: int = 1
    line_end: int = 1

    def __post_init__(self):
        if self.category not in CATEGORIES or self.visibility not in ("public", "private"):
            raise ValueError("Invalid knowledge category/visibility")
        if not all(isinstance(getattr(self, key), str) and getattr(self, key).strip()
                   for key in ("source_id", "title", "text", "locator", "license", "version")):
            raise ValueError("Knowledge records require text and explicit provenance")
        if self.visibility == "public" and self.license not in PUBLIC_LICENSES:
            raise ValueError("Uncleared/copyrighted references must remain private")
        if (type(self.line_start) is not int or type(self.line_end) is not int
                or not 1 <= self.line_start <= self.line_end):
            raise ValueError("Invalid source line range")


def terms(text):
    latin = re.findall(r"[a-z0-9_]+", text.casefold())
    result = list(latin)
    for word in latin:
        result.extend(word.split("_"))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        result.extend("zh_" + c for c in run)
        result.extend("zh_" + run[i:i + 2] for i in range(len(run) - 1))
    return list(dict.fromkeys(result))


def chunks(path, *, source_id, category, license, visibility="private", version="unspecified", locator=None,
           max_chars=3200):
    """Chunk local text with exact line provenance; external sources default private."""
    path = Path(path).resolve(strict=True)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    title, start, buffer, size = path.stem, 1, [], 0
    for number, line in enumerate(lines, 1):
        heading = re.match(r"^#{1,4}\s+(.+)", line)
        if buffer and (size + len(line) > max_chars or heading):
            text = "\n".join(buffer).strip()
            if text:
                yield Document(source_id, category, title, text, locator or str(path), license,
                               visibility, version, start, number - 1)
            buffer, size, start = [], 0, number
        if heading:
            title = heading[1]
        buffer.append(line)
        size += len(line) + 1
    if buffer and "\n".join(buffer).strip():
        yield Document(source_id, category, title, "\n".join(buffer).strip(), locator or str(path), license,
                       visibility, version, start, len(lines))


def repository_documents(root=REPOSITORY):
    root = Path(root)
    table = root / "src/ls_prepost_mcp/data/commands.tsv"
    with table.open(encoding="utf-8-sig", newline="") as stream:
        for number, row in enumerate(csv.DictReader(stream, delimiter="\t"), 2):
            title = " ".join((row["Command"], row["Variant"])).strip()
            yield Document("library-cfile-support", "command", title, " ".join(row.values()),
                           "repo://src/ls_prepost_mcp/data/commands.tsv", "Apache-2.0", "public", "catalog", number, number)
    from .native import commands as native_commands
    revision = "sha256:" + hashlib.sha256(Path(native_commands.__file__).read_bytes()).hexdigest()
    examples = (("save_keyword", native_commands.save_keyword("model.k"), "保存当前关键字模型"),
                ("print_png", native_commands.print_png("image.png"), "导出 PNG 图片"),
                ("open_model", native_commands.open_model("model.k"), "打开关键字模型"),
                ("run_script", native_commands.run_script("program.scl","scl"), "执行 SCL 文件"))
    for builder,example,description in examples:
        yield Document("native-command-builders", "command", example, description + "\n" + example +
                       "\nSource example only; consult recipe/version evidence before execution.",
                       "repo://src/ls_prepost_mcp/native/commands.py#" + builder, "MIT", "public", revision)
    for relative, category in (("docs/KNOWN_ISSUES.md", "known_issue"), ("docs/INSTALL.md", "user_guide")):
        yield from chunks(root / relative, source_id=relative, category=category, license="MIT", visibility="public",
                          locator="repo://" + relative)
    for path in sorted((root / "examples/workflows").glob("*.json")):
        relative = path.relative_to(root).as_posix()
        yield from chunks(path, source_id=relative, category="recipe", license="MIT", visibility="public",
                          locator="repo://" + relative, version="legacy_workflow_template")
    # A08's recipe documents are indexed automatically when introduced.
    for path in sorted((root / "src/ls_prepost_mcp/native/recipes").glob("**/recipe.yaml")):
        relative = path.relative_to(root).as_posix()
        yield from chunks(path, source_id=relative, category="recipe", license="MIT", visibility="public", locator="repo://" + relative)


def build_index(destination, documents, fields=()):
    """Publish a complete index atomically; interrupted partials cannot block rebuilds."""
    path = Path(destination).resolve()
    rows = list(documents)
    field_map = {}
    for field in fields:
        if not isinstance(field, KeywordField):
            raise ValueError("Keyword fields must come from the keyword_docs adapter")
        locator = "keyword_docs://" + field.entity_key + "/" + str(field.card) + "/" + str(field.option) + "/" + field.field
        if locator in field_map and field_map[locator] != field:
            raise ValueError("Provider returned conflicting field identities")
        text = field.help + "\n" + json.dumps(dict(aliases=field.aliases, links=field.links, manual_ref=field.manual_ref), ensure_ascii=False)
        row = Document("keyword_docs:" + field.entity_key, "keyword", field.entity_key + " " + field.field,
                       text, locator, field.license, field.visibility, field.version)
        rows.append(row)
        field_map[locator] = field
    if not rows or any(not isinstance(row, Document) for row in rows):
        raise ValueError("Cannot build an empty knowledge index")
    if any(row.visibility == "private" for row in rows) and path.is_relative_to(REPOSITORY):
        raise ValueError("Private text and derived indexes must remain outside the repository")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    partial = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    try:
        with partial.open("xb"):
            pass
        with closing(sqlite3.connect(partial)) as db, db:
            db.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, source_id TEXT, category TEXT, title TEXT, text TEXT, locator TEXT, license TEXT, visibility TEXT, version TEXT, line_start INTEGER, line_end INTEGER, sha256 TEXT)")
            db.execute("CREATE VIRTUAL TABLE search_terms USING fts5(id UNINDEXED, terms)")
            db.execute("CREATE TABLE keyword_fields (document_id TEXT PRIMARY KEY, entity_key TEXT, option TEXT, card TEXT, field TEXT, offset INTEGER, width INTEGER, help TEXT, links TEXT, manual_ref TEXT, solver_status TEXT, license TEXT, aliases TEXT)")
            db.execute("CREATE TABLE metadata (schema_version INTEGER)")
            db.execute("INSERT INTO metadata VALUES (2)")
            seen = set()
            for row in rows:
                data = asdict(row)
                identity = json.dumps(data, sort_keys=True, ensure_ascii=False)
                ident = hashlib.sha256(identity.encode()).hexdigest()
                if ident in seen:
                    continue
                seen.add(ident)
                digest = hashlib.sha256(row.text.encode()).hexdigest()
                db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (ident, *data.values(), digest))
                db.execute("INSERT INTO search_terms VALUES (?,?)", (ident, " ".join(terms(row.title + " " + row.text))))
                field = field_map.get(row.locator)
                if field:
                    db.execute("INSERT INTO keyword_fields VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (ident, field.entity_key, field.option, json.dumps(field.card), field.field, field.offset, field.width,
                                field.help, json.dumps(field.links), json.dumps(field.manual_ref), json.dumps(field.solver_status), field.license, json.dumps(field.aliases)))
            counts = dict(db.execute("SELECT category, count(*) FROM documents GROUP BY category"))
        # Atomic no-overwrite publication also handles two concurrent builders.
        os.link(partial, path)
    finally:
        partial.unlink(missing_ok=True)  # Only this invocation's UUID-named partial.
    return dict(schema_version=2, documents=len(seen), keyword_fields=len(field_map), categories=counts,
                private=any(row.visibility == "private" for row in rows))


def search_index(path, query, *, category=None, limit=10, include_private=False):
    if not isinstance(query, str) or not query.strip() or len(query) > 1000 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Provide a bounded query and limit 1..50")
    if category is not None and category not in CATEGORIES:
        raise ValueError("Unknown reference category")
    if type(include_private) is not bool:
        raise ValueError("include_private must be Boolean")
    query_terms = terms(query)
    if not query_terms:
        return []
    latin = [value for value in query_terms if not value.startswith("zh_")]
    chinese = [value for value in query_terms if value.startswith("zh_") and len(value) == 5]
    selected = latin or chinese or query_terms
    expression = (" AND " if latin else " OR ").join('"' + value.replace('"', '""') + '"' + ("*" if "_" in value and not value.startswith("zh_") else "") for value in selected)
    uri = Path(path).resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        if db.execute("SELECT schema_version FROM metadata").fetchone()[0] != 2:
            raise ValueError("Unsupported knowledge index schema")
        sql = "SELECT documents.*, bm25(search_terms) AS rank FROM search_terms JOIN documents ON documents.id=search_terms.id WHERE search_terms MATCH ?"
        params = [expression]
        if category:
            sql += " AND category=?"
            params.append(category)
        if not include_private:
            sql += " AND visibility='public'"
        sql += " ORDER BY rank, documents.id LIMIT ?"
        rows = db.execute(sql, [*params, limit]).fetchall()
        fields = {row["id"]: db.execute("SELECT * FROM keyword_fields WHERE document_id=?", (row["id"],)).fetchone() for row in rows}
    results = []
    for row in rows:
        data = dict(row)
        text = data.pop("text")
        position = text.casefold().find(query.casefold())
        if position < 0:
            for token in sorted((value for value in query_terms if not value.startswith("zh_")),key=len,reverse=True):
                position=text.casefold().find(token)
                if position >= 0:
                    break
        begin = max(0, position - 100) if position >= 0 else 0
        data["snippet"] = text[begin:begin + 600]
        data.update(status="reference_unverified", executable=False, private=data["visibility"] == "private")
        if data["category"] == "recipe":
            proof = recipe_verification(text)
            if proof:
                data["recipe_verification"] = proof
        if fields[data["id"]] is not None:
            data.pop("line_start")
            data.pop("line_end")  # Structured provider fields have card/columns, not invented source lines.
            field = dict(fields[data["id"]])
            field.pop("document_id")
            for key in ("card", "links", "manual_ref", "solver_status", "aliases"):
                field[key] = json.loads(field[key])
            data["keyword_field"] = field
        results.append(data)
    return results


def recipe_verification(text):
    """Extract attributed version/mode claims from indexed YAML, never execute it."""
    import yaml

    if len(text) > 1024 * 1024:
        return None
    try:
        recipe = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(recipe, dict):
        return None
    versions = recipe.get("versions_verified")
    if not isinstance(versions, list) or not all(isinstance(v, str) and v.strip() for v in versions):
        return None
    modes = recipe.get("execution_modes")
    scoped = {}
    if isinstance(modes, dict):
        for name, details in modes.items():
            by_version = details.get("by_version") if isinstance(details, dict) else None
            if name in ("c_nographics", "runc") and isinstance(by_version, dict):
                scoped[name] = {version: state for version, state in by_version.items()
                                if isinstance(version, str) and state in ("verified", "failed", "unverified")}
    case = recipe.get("l2_case")
    return dict(versions_verified=versions, execution_modes=scoped,
                l2_case=case if isinstance(case, str) and case.strip() else None)
