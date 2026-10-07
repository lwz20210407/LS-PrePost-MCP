"""I05 source-attributed local reference index. Indexed text is never executable."""

import csv
import errno
import functools
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path

from .keyword_documentation import KeywordField, KeywordWithoutFields, fieldless_review

CATEGORIES = frozenset(("command", "api", "keyword", "user_guide", "recipe", "known_issue"))
PUBLIC_LICENSES = frozenset(("MIT", "Apache-2.0", "BSD-3-Clause", "CC0-1.0"))
REPOSITORY = Path(__file__).resolve().parents[2]
GLOSSARY = Path(__file__).with_name("data") / "search_glossary.json"
ENGLISH_STOPWORDS = frozenset((
    "a", "an", "the", "of", "to", "in", "on", "at", "for", "and", "or", "is", "are", "be", "it", "its",
    "how", "what", "which", "where", "why", "do", "does", "can", "i", "my", "with", "by", "from", "this", "that"))


def _cleanup_owned_temp(path, original):
    """Retain the primary failure if a Windows reader still holds our temp file."""
    try:
        path.unlink(missing_ok=True)
    except OSError as cleanup_error:
        message = "Index temporary file could not be removed; retained at {}: {}".format(path, cleanup_error)
        logging.getLogger(__name__).warning(message)
        if original is not None:
            original.add_note(message)


def publish_index(partial, path):
    """Publish complete bytes without overwriting any concurrently created index."""
    try:
        os.link(partial, path)
        return
    except OSError as exc:
        unsupported = exc.errno in {errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP}
        unsupported = unsupported or getattr(exc, "winerror", None) in (1, 50)
        if os.name != "nt" or not unsupported:
            raise
    # Windows rename refuses an existing destination, unlike POSIX rename.
    # Keep the copy in the destination directory and close it before publication.
    staged = path.with_name(path.name + "." + uuid.uuid4().hex + ".publish")
    created = False
    original = None
    try:
        with partial.open("rb") as source, staged.open("xb") as destination:
            created = True
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        # Antivirus/indexers can briefly hold a non-delete-sharing read handle.
        # Total backoff is 1.15 s; no replacement and no retry of other failures.
        delays = (0.05, 0.1, 0.2, 0.4, 0.4)
        for attempt in range(len(delays) + 1):
            try:
                os.rename(staged, path)
                break
            except PermissionError as exc:
                if getattr(exc, "winerror", None) not in (5, 32) or attempt == len(delays):
                    raise
                time.sleep(delays[attempt])
        created = False  # The temporary name is no longer owned after rename.
    except BaseException as exc:
        original = exc
        raise
    finally:
        if created:
            _cleanup_owned_temp(staged, original)


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


def fieldless_document(record):
    review = record.review or {}
    meaning = fieldless_review()["verdicts"].get(review.get("verdict"), "Not reviewed; field coverage is unknown.")
    text = " ".join(part for part in (
        record.entity_key + ": keyword_docs returned no named field.",
        "Provider card structure: " + record.provider_structure + " (" + ", ".join(record.card_kinds or ["none"]) + ").",
        "Review verdict: " + record.verdict + (" (" + review["basis"] + ")." if review.get("basis") else "."),
        meaning, review.get("note", "")) if part)
    return Document("keyword_docs:" + record.entity_key, "keyword", record.entity_key, text,
                    "keyword_docs://" + record.entity_key, "MIT", "public", record.version)


def build_index(destination, documents, fields=(), fieldless=()):
    """Publish a complete index atomically; interrupted partials cannot block rebuilds."""
    path = Path(destination).resolve()
    rows = list(documents)
    fieldless_map = {}
    for record in fieldless:
        if not isinstance(record, KeywordWithoutFields):
            raise ValueError("Field-less keywords must come from the keyword_docs adapter")
        if fieldless_map.get(record.entity_key, record) != record:
            raise ValueError("Provider returned conflicting field-less keyword records")
        fieldless_map[record.entity_key] = record
    fieldless_rows = {record.entity_key: fieldless_document(record) for record in fieldless_map.values()}
    rows.extend(fieldless_rows.values())
    field_map = {}
    for field in fields:
        if not isinstance(field, KeywordField):
            raise ValueError("Keyword fields must come from the keyword_docs adapter")
        # Repeated names on one card can occupy distinct columns (e.g. VAR).
        # Keep both occurrences; contradictory definitions at one slot still fail.
        locator = ("keyword_docs://" + field.entity_key + "/" + str(field.card) + "/" + str(field.option)
                   + "/" + field.field + "/" + str(field.offset) + ":" + str(field.width))
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
    created = False
    original = None
    try:
        with partial.open("xb"):
            created = True
        with closing(sqlite3.connect(partial)) as db, db:
            db.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, source_id TEXT, category TEXT, title TEXT, text TEXT, locator TEXT, license TEXT, visibility TEXT, version TEXT, line_start INTEGER, line_end INTEGER, sha256 TEXT)")
            db.execute("CREATE VIRTUAL TABLE search_terms USING fts5(id UNINDEXED, terms)")
            db.execute("CREATE TABLE keyword_fields (document_id TEXT PRIMARY KEY, entity_key TEXT, option TEXT, card TEXT, field TEXT, offset INTEGER, width INTEGER, help TEXT, links TEXT, manual_ref TEXT, solver_status TEXT, license TEXT, aliases TEXT)")
            db.execute("CREATE INDEX keyword_lookup ON keyword_fields(entity_key,field)")
            db.execute("CREATE TABLE keyword_without_fields (document_id TEXT PRIMARY KEY, entity_key TEXT UNIQUE, provider_structure TEXT, card_kinds TEXT, verdict TEXT, review TEXT)")
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
                record = fieldless_map.get(row.title)
                if record and fieldless_rows[row.title] is row:
                    db.execute("INSERT INTO keyword_without_fields VALUES (?,?,?,?,?,?)",
                               (ident, record.entity_key, record.provider_structure, json.dumps(record.card_kinds),
                                record.verdict, json.dumps(record.review)))
                field = field_map.get(row.locator)
                if field:
                    db.execute("INSERT INTO keyword_fields VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (ident, field.entity_key, field.option, json.dumps(field.card), field.field, field.offset, field.width,
                                field.help, json.dumps(field.links), json.dumps(field.manual_ref), json.dumps(field.solver_status), field.license, json.dumps(field.aliases)))
            counts = dict(db.execute("SELECT category, count(*) FROM documents GROUP BY category"))
        # Atomic no-overwrite publication also handles two concurrent builders.
        publish_index(partial, path)
    except BaseException as exc:
        original = exc
        raise
    finally:
        if created:
            _cleanup_owned_temp(partial, original)  # Only this invocation's UUID-named partial.
    return dict(schema_version=2, documents=len(seen), keyword_fields=len(field_map),
                keywords_without_fields=len(fieldless_map), categories=counts,
                private=any(row.visibility == "private" for row in rows))


@functools.lru_cache(maxsize=1)
def glossary():
    data = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    return {key: tuple(values) for key, values in data["terms"].items()}, frozenset(data["stopwords"])


def _quote(value):
    # Identifier-prefix behavior for underscored code names only.
    prefix = "*" if "_" in value and not value.startswith("zh_") else ""
    return '"' + value.replace('"', '""') + '"' + prefix


def _word_forms(word):
    """Exact English inflection alternatives; identifiers and short tokens stay literal."""
    if not word.isalpha() or len(word) < 3:
        return [word]
    stems = {word}
    for suffix, replacement in (("ies", "y"), ("es", ""), ("s", ""), ("ing", ""), ("ed", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stems.add(word[:-len(suffix)] + replacement)
    return sorted({form for stem in stems for form in (stem, stem + "s", stem + "es", stem + "ed", stem + "ing")})


def _word_expression(word):
    forms = _word_forms(word)
    return _quote(forms[0]) if len(forms) == 1 else "(" + " OR ".join(_quote(form) for form in forms) + ")"


def _phrase_expression(phrase):
    words = [word for word in re.findall(r"[a-z0-9]+", phrase.casefold()) if len(word) > 1]
    return " AND ".join(_word_expression(word) for word in words), words


def _chinese_expression(text):
    grams = [text[i:i + 2] for i in range(len(text) - 1)] or [text]
    return " AND ".join(_quote("zh_" + gram) for gram in grams)


def _segment(run, entries, stopwords):
    """Greedy longest glossary/stopword match; unmatched characters stay as raw text."""
    longest = max(map(len, (*entries, *stopwords)))
    pieces, rest, i = [], "", 0
    while i < len(run):
        for size in range(min(longest, len(run) - i), 0, -1):
            word = run[i:i + size]
            if word in entries or word in stopwords:
                break
        else:
            rest += run[i]
            i += 1
            continue
        if rest:
            pieces.append(("rest", rest))
            rest = ""
        pieces.append(("term" if word in entries else "stop", word))
        i += size
    if rest:
        pieces.append(("rest", rest))
    return pieces


def plan_query(query):
    """Translate a query into FTS expressions without executing or rewriting index content.

    Latin terms remain mandatory. Chinese text becomes optional concepts: general glossary
    terms (matched as Chinese or as their English phrases) and unmatched Chinese text.
    """
    entries, stopwords = glossary()
    latin = [value for value in terms(query) if not value.startswith("zh_")]
    content = [value for value in latin if value not in ENGLISH_STOPWORDS]
    latin = content or latin
    concepts, expansion, fallback, highlights = [], [], [], set(latin)
    for run in re.findall(r"[\u3400-\u9fff]+", query):
        fallback.extend(run[i:i + 2] for i in range(len(run) - 1))
        for kind, text in _segment(run, entries, stopwords):
            if kind == "term":
                english = [_phrase_expression(phrase) for phrase in entries[text]]
                options = [_chinese_expression(text)] + [expression for expression, _ in english if expression]
                concepts.append("(" + " OR ".join("(" + option + ")" for option in options) + ")")
                expansion.append(dict(term=text, english=list(entries[text])))
                highlights.add(text)
                highlights.update(word for _, words in english for word in words)
            elif kind == "rest" and len(text) > 1:
                concepts.append("(" + " OR ".join(_quote("zh_" + text[i:i + 2]) for i in range(len(text) - 1)) + ")")
                highlights.add(text)
    if not concepts and fallback:
        concepts = ["(" + " OR ".join(_quote("zh_" + gram) for gram in dict.fromkeys(fallback)) + ")"]
    if not concepts:
        runs = re.findall(r"[\u3400-\u9fff]", query)
        concepts = ["(" + " OR ".join(_quote("zh_" + char) for char in dict.fromkeys(runs)) + ")"] if runs else []
    entities = [match.upper() for match in re.findall(r"\*([A-Za-z][A-Za-z0-9_/-]*)", query)]
    return dict(latin=" AND ".join(_word_expression(value) for value in latin), concepts=concepts,
                expansion=expansion, entities=["*" + entity for entity in dict.fromkeys(entities)],
                highlights=sorted(highlights, key=len, reverse=True))


def _snippet(text, query, highlights, width=600):
    folded = text.casefold()
    position = folded.find(query.casefold())
    if position >= 0:
        begin = max(0, position - 100)
        return text[begin:begin + width]
    hits = []
    for term in highlights:
        start = folded.find(term)
        while start >= 0 and len(hits) < 2000:
            hits.append((start, term))
            start = folded.find(term, start + len(term))
    if not hits:
        return text[:width]
    hits.sort()
    best, best_count, j = 0, 0, 0
    for i, (start, _) in enumerate(hits):
        while j < len(hits) and hits[j][0] - start <= width - 100:
            j += 1
        count = len({term for _, term in hits[i:j]})
        if count > best_count:
            best, best_count = start, count
    begin = max(0, best - 100)
    return text[begin:begin + width]


def search_index(path, query, *, category=None, limit=10, include_private=False, keyword_filter=None):
    if not isinstance(query, str) or not query.strip() or len(query) > 1000 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Provide a bounded query and limit 1..50")
    if category is not None and category not in CATEGORIES:
        raise ValueError("Unknown reference category")
    if type(include_private) is not bool:
        raise ValueError("include_private must be Boolean")
    if keyword_filter is not None:
        if (not isinstance(keyword_filter, tuple) or len(keyword_filter) != 2 or category != "keyword"
                or not isinstance(keyword_filter[0], str) or not re.fullmatch(r"\*[A-Z0-9_/-]+", keyword_filter[0])
                or keyword_filter[1] is not None and not isinstance(keyword_filter[1], str)):
            raise ValueError("Structured keyword lookup requires a keyword prefix and optional field")
    if not terms(query):
        return []
    plan = plan_query(query)
    latin_expression = plan["latin"]
    chinese_expression = " OR ".join(plan["concepts"])
    if not latin_expression and not chinese_expression:
        return []
    mixed = bool(latin_expression and chinese_expression)
    expression = ("(" + latin_expression + ") OR (" + chinese_expression + ")"
                  if mixed else latin_expression or chinese_expression)
    uri = Path(path).resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        if db.execute("SELECT schema_version FROM metadata").fetchone()[0] != 2:
            raise ValueError("Unsupported knowledge index schema")
        if keyword_filter is None:
            sql = "SELECT documents.*, bm25(search_terms) AS rank"
            params = []
            if mixed:
                sql += (", CASE WHEN documents.id IN (SELECT id FROM search_terms WHERE search_terms MATCH ?) THEN 0 "
                        "WHEN documents.id IN (SELECT id FROM search_terms WHERE search_terms MATCH ?) THEN 1 "
                        "ELSE 2 END AS query_priority")
                params += ["(" + latin_expression + ") AND (" + chinese_expression + ")", latin_expression]
            else:
                sql += ", 0 AS query_priority"
            # An explicitly named *KEYWORD outranks concept coverage; bm25 only breaks ties.
            coverage = " + ".join("(documents.id IN (SELECT id FROM search_terms WHERE search_terms MATCH ?))"
                                  for _ in plan["concepts"]) or "0"
            params += plan["concepts"]
            sql += ", " + coverage + " AS coverage"
            entity = " OR ".join("upper(documents.title)=? OR substr(upper(documents.title),1,?)=?"
                                 for _ in plan["entities"])
            sql += ", " + ("CASE WHEN " + entity + " THEN 0 ELSE 1 END" if entity else "1") + " AS entity_rank"
            for key in plan["entities"]:
                params += [key, len(key) + 1, key + " "]
            sql += " FROM search_terms JOIN documents ON documents.id=search_terms.id WHERE search_terms MATCH ?"
            params.append(expression)
            order = "query_priority, entity_rank, coverage DESC, rank, documents.id"
            order_params = []
        else:
            prefix, field_name = keyword_filter
            # Literal prefix range: '_' is a keyword character, not LIKE's
            # single-character wildcard. Filter before LIMIT so prose cannot
            # crowd an explicitly requested field out of the candidate set.
            # CROSS JOIN fixes the outer loop to fields on existing schema-v2
            # indexes; otherwise SQLite scans/joins all documents first.
            sql = ("SELECT documents.*, 0.0 AS rank, 0 AS query_priority FROM keyword_fields AS k "
                   "CROSS JOIN documents ON documents.id=k.document_id "
                   "WHERE k.entity_key>=? AND k.entity_key<?")
            params = [prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)]
            if field_name is not None:
                sql += (" AND (lower(k.field)=? OR EXISTS (SELECT 1 FROM json_each(k.aliases) AS a "
                        "WHERE a.type='text' AND lower(a.value)=?))")
                params.extend([field_name.casefold(), field_name.casefold()])
            order = ("CASE WHEN k.entity_key=? THEN 0 ELSE 1 END, k.entity_key, "
                     "CASE WHEN json_type(k.card)='integer' THEN 0 ELSE 1 END, "
                     "CAST(k.card AS INTEGER), k.card, coalesce(k.option,''), k.offset, k.width, k.field, documents.id")
            order_params = [prefix]
        if category:
            sql += " AND category=?"
            params.append(category)
        if not include_private:
            sql += " AND visibility='public'"
        sql += " ORDER BY " + order + " LIMIT ?"
        rows = db.execute(sql, [*params, *order_params, limit]).fetchall()
        fields = {row["id"]: db.execute("SELECT * FROM keyword_fields WHERE document_id=?", (row["id"],)).fetchone() for row in rows}
    results = []
    for row in rows:
        data = dict(row)
        priority = data.pop("query_priority")
        for key in ("coverage", "entity_rank"):
            data.pop(key, None)
        data["query_match"] = (("both", "code_only", "text_only")[priority] if mixed
                               else "code_only" if latin_expression else "text_only")
        text = data.pop("text")
        data["snippet"] = _snippet(text, query, plan["highlights"])
        data["query_expansion"] = plan["expansion"]
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
