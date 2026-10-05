"""I05 source-attributed local reference index. Indexed text is never executable."""

import ast
import csv
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

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


def keyword_documents(package_root, version):
    """Read PyDYNA's MIT field declarations, without importing thousands of classes."""
    root = Path(package_root).resolve(strict=True)
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf8")
        if "SPDX-License-Identifier: MIT" not in source:
            continue
        tree = ast.parse(source)
        constants = {target.id: node for node in tree.body if isinstance(node, ast.Assign)
                     for target in node.targets if isinstance(target, ast.Name)}
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            names = {}
            for node in cls.body:
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                    names.update({t.id: node.value.value for t in node.targets if isinstance(t, ast.Name)})
            if not isinstance(names.get("keyword"), str):
                continue
            keyword = names["keyword"]
            subkeyword = names.get("subkeyword")
            if subkeyword and subkeyword != keyword:
                keyword += "_" + subkeyword
            fields = []
            definitions, visited = [cls], set()
            for definition in definitions:
                for node in ast.walk(definition):
                    if isinstance(node, ast.Name) and node.id in constants and node.id not in visited:
                        visited.add(node.id)
                        definitions.append(constants[node.id])
            for node in (child for definition in definitions for child in ast.walk(definition)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("Field", "FieldSchema"):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        values = [ast.unparse(arg) for arg in node.args[:5]]
                        fields.append("field " + " | ".join(values) + " (name, type, offset, width, default)")
            if fields:
                locator = "pydyna://" + version + "/" + path.relative_to(root).as_posix()
                text = "*" + keyword + "\n" + (ast.get_docstring(cls) or "") + "\n" + "\n".join(dict.fromkeys(fields))
                yield Document("pydyna:" + cls.name, "keyword", "*" + keyword + " / " + cls.name,
                               text, locator, "MIT", "public", version,
                               min(item.lineno for item in definitions), max(item.end_lineno for item in definitions))


def build_index(destination, documents):
    """Create a new index; never overwrite an earlier evidence/index file."""
    path = Path(destination).resolve()
    rows = list(documents)
    if not rows or any(not isinstance(row, Document) for row in rows):
        raise ValueError("Cannot build an empty knowledge index")
    if any(row.visibility == "private" for row in rows) and path.is_relative_to(REPOSITORY):
        raise ValueError("Private text and derived indexes must remain outside the repository")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb"):
        pass
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, source_id TEXT, category TEXT, title TEXT, text TEXT, locator TEXT, license TEXT, visibility TEXT, version TEXT, line_start INTEGER, line_end INTEGER, sha256 TEXT)")
        db.execute("CREATE VIRTUAL TABLE search_terms USING fts5(id UNINDEXED, terms)")
        db.execute("CREATE TABLE metadata (schema_version INTEGER)")
        db.execute("INSERT INTO metadata VALUES (1)")
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
        counts = dict(db.execute("SELECT category, count(*) FROM documents GROUP BY category"))
    return dict(documents=len(seen), categories=counts, private=any(row.visibility == "private" for row in rows))


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
    expression = " AND ".join('"' + value.replace('"', '""') + '"' for value in query_terms)
    uri = Path(path).resolve(strict=True).as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        if db.execute("SELECT schema_version FROM metadata").fetchone()[0] != 1:
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
    results = []
    for row in rows:
        data = dict(row)
        text = data.pop("text")
        position = text.casefold().find(query.casefold())
        begin = max(0, position - 100) if position >= 0 else 0
        data["snippet"] = text[begin:begin + 600]
        data.update(status="reference_unverified", executable=False, private=data["visibility"] == "private")
        results.append(data)
    return results
