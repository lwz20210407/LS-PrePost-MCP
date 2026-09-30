"""Use locally installed keyword filters/templates without redistributing vendor files."""

import ast
import fnmatch
import hashlib
import math
import operator
import os
import re
from pathlib import Path

from .jobs import atomic_json, check_artifact, fingerprint


def catalog(settings):
    configured = os.environ.get("LSPP_TEMPLATE_ROOT")
    root = Path(configured if configured else settings.native_executable().parent / "templates").resolve()
    records = []
    for category, folder, pattern in [
        ("filter", "kwfilter", "*.txt"),
        ("template", "kwtemplate", "template.k"),
    ]:
        for p in sorted((root / folder).rglob(pattern)):
            resolved = p.resolve()
            if not resolved.is_relative_to(root) or not resolved.is_file():
                continue
            relative = p.relative_to(root).as_posix()
            ident = category + "-" + hashlib.sha256(relative.encode()).hexdigest()[:16]
            records.append(
                dict(
                    id=ident,
                    kind=category,
                    name=p.stem if category == "filter" else p.parent.name,
                    relative_path=relative,
                    path=str(resolved),
                    bytes=p.stat().st_size,
                )
            )
    return records


def asset(settings, ident, kind=None):
    found = [r for r in catalog(settings) if r["id"] == ident and (kind is None or r["kind"] == kind)]
    if len(found) != 1:
        raise ValueError("Unknown installation resource ID; list_installation_assets first")
    return found[0], Path(found[0]["path"])


def declarations(text):
    values = []
    active = None
    label = ""
    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("*"):
            active = stripped.split(",")[0].upper()
            label = ""
            continue
        if active not in ("*PARAMETER_EXPRESSION", "*PARAMETER"):
            continue
        if stripped.lower().startswith("$text:"):
            label = stripped.partition(":")[2].strip()
            continue
        if not stripped or stripped.startswith("$"):
            continue
        if "," in line:
            name, _, expression = line.partition(",")
        else:
            name, expression = line[:10], line[10:]
        name = name.strip()
        if not re.fullmatch(r"[RISris][A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("Unsupported parameter declaration at line " + str(index + 1))
        values.append(
            dict(
                name=name[1:].upper(),
                type=name[0].upper(),
                expression=expression.strip(),
                label=label,
                line=index + 1,
            )
        )
        label = ""
    names = [p["name"] for p in values]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate parameter names require an explicit scope resolver")
    return values


FUNCTIONS = {
    name.upper(): getattr(math, name)
    for name in ("sin", "cos", "tan", "asin", "acos", "atan", "sqrt", "exp", "log", "log10", "floor", "ceil")
}
FUNCTIONS.update(ABS=abs, MIN=min, MAX=max)
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}


def evaluate_parameters(items, overrides):
    by_name = {p["name"]: p for p in items}
    replacements = {str(k).upper(): v for k, v in overrides.items()}
    if not set(replacements) <= set(by_name):
        raise ValueError("Unknown template parameters: " + str(sorted(set(replacements) - set(by_name))))
    resolved = {}
    visiting = set()

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Name):
            return resolve(node.id.upper())
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return evaluate(node.operand) * (1 if isinstance(node.op, ast.UAdd) else -1)
        if isinstance(node, ast.BinOp):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Pow):
                if abs(right) > 100 or abs(left) > 1e100:
                    raise ValueError("Parameter exponent exceeds limits")
                return left**right
            if type(node.op) in OPERATORS:
                return OPERATORS[type(node.op)](left, right)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id.upper() in FUNCTIONS
            and not node.keywords
            and len(node.args) <= 10
        ):
            return FUNCTIONS[node.func.id.upper()](*[evaluate(x) for x in node.args])
        raise ValueError("Unsupported parameter expression; no Python evaluation is performed")

    def resolve(name):
        if name in resolved:
            return resolved[name]
        if name in visiting:
            raise ValueError("Cyclic parameter dependency: " + name)
        if name not in by_name:
            raise ValueError("Unresolved external parameter: " + name)
        visiting.add(name)
        item = by_name[name]
        value = replacements.get(name)
        if name not in replacements:
            if item["type"] == "S":
                value = item["expression"].strip("\"'")
            else:
                expression = item["expression"].replace("^", "**").strip()
                tree = ast.parse(expression, mode="eval")
                if len(list(ast.walk(tree))) > 200:
                    raise ValueError("Expression too complex")
                value = evaluate(tree.body)
        if item["type"] == "S":
            if not isinstance(value, str) or len(value) > 70 or any(c in value for c in "\r\n\x00"):
                raise ValueError("Invalid string parameter")
        elif type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Numeric parameter must be finite")
        elif item["type"] == "I":
            if value != int(value):
                raise ValueError("Integer parameter is not integral: " + name)
            value = int(value)
        resolved[name] = value
        visiting.remove(name)
        return value

    for name in by_name:
        resolve(name)
    return resolved


def render_template(text, overrides):
    items = declarations(text)
    values = evaluate_parameters(items, overrides)
    lines = text.splitlines()
    for p in items:
        value = values[p["name"]]
        rendered = str(value) if isinstance(value, (str, int)) else format(value, ".15g")
        lines[p["line"] - 1] = (p["type"] + p["name"]).ljust(10) + rendered
    return "\n".join(lines) + "\n", items, values


def keyword_blocks(text):
    result = []
    current = []
    for line in text.splitlines():
        if line.lstrip().startswith("*"):
            if current:
                result.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        result.append(current)
    return result


def header(block):
    return block[0].strip().split(",")[0].split()[0].upper()


def merge_template(model_text, template_text):
    base = keyword_blocks(model_text)
    extra = keyword_blocks(template_text)
    replacements = {
        header(b)
        for b in extra
        if header(b).startswith("*CONTROL_")
        or (header(b).startswith("*DATABASE_") and "HISTORY" not in header(b))
    }
    body = [b for b in base if header(b) not in replacements and header(b) not in ("*KEYWORD", "*END")]
    body += [b for b in extra if header(b) not in ("*KEYWORD", "*END", "*TITLE")]
    return "*KEYWORD\n" + "\n".join("\n".join(b) for b in body) + "\n*END\n", sorted(replacements)


class InstallationTools:
    def list_installation_assets(self) -> dict:
        """Discover every installed kwfilter and kwtemplate package; no vendor files are copied into this repository."""
        records = catalog(self.settings)
        return dict(
            filters=[r for r in records if r["kind"] == "filter"],
            templates=[r for r in records if r["kind"] == "template"],
        )

    def describe_installed_template(self, template_id: str) -> dict:
        """Read parameter names, labels, expressions, evaluated defaults and keyword dependencies from an installed template."""
        record, path = asset(self.settings, template_id, "template")
        text = path.read_text(encoding="utf-8-sig", errors="strict")
        params = declarations(text)
        info = path.parent / "info.txt"
        return dict(
            resource=record,
            source=fingerprint(path),
            parameters=params,
            defaults=evaluate_parameters(params, {}),
            keywords=sorted({header(b) for b in keyword_blocks(text)}),
            usage=info.read_text(encoding="utf-8-sig", errors="replace") if info.exists() else "",
            unit_policy="Inspect supplied usage/units; no implicit unit conversion",
        )

    def apply_keyword_filter(self, model: str, filter_id: str) -> dict:
        """Apply an installed keyword filter to a deck inventory, preserving the model. Returns matching block indices and headers, not a destructively filtered model."""
        record, path = asset(self.settings, filter_id, "filter")
        patterns = [
            s.strip().upper()
            for s in path.read_text(encoding="utf-8-sig").splitlines()
            if s.strip().startswith("*")
        ]
        source = self.settings.input_path(model)
        matches = []
        for i, block in enumerate(keyword_blocks(source.read_text(encoding="utf-8-sig", errors="replace"))):
            name = header(block)
            canonical = re.sub(r"_(TITLE|ID)$", "", name)
            if any(fnmatch.fnmatchcase(name, p) or fnmatch.fnmatchcase(canonical, p) for p in patterns):
                matches.append(dict(block_index=i, keyword=name))
        return dict(
            resource=record,
            source=fingerprint(source),
            patterns=patterns,
            matches=matches,
            model_modified=False,
            semantics="Keyword-category selection; not an engineering validity filter",
        )

    def instantiate_installed_template(
        self,
        template_id: str,
        parameters: dict,
        units: str,
        model: str | None = None,
        native_check: bool = True,
    ) -> dict:
        """Evaluate template parameters safely and write a new deck. Optional model merge replaces matching CONTROL/DATABASE singleton blocks. Native mesh reopen is explicit; fragments remain fragments."""
        record, path = asset(self.settings, template_id, "template")
        source = self.settings.input_path(model) if model else None
        if source:
            self.settings.check_keyword_includes(source)
        text = path.read_text(encoding="utf-8-sig")
        rendered, params, values = render_template(text, parameters)
        replaced = []
        if source:
            base = source.read_text(encoding="utf-8-sig")
            if "*INCLUDE" in base.upper() or "*PARAMETER" in base.upper():
                raise ValueError("Merge model must first be flattened and parameter-resolved")
            rendered, replaced = merge_template(base, rendered)

        def work(directory):
            output = directory / "model.k"
            output.write_text(rendered, encoding="utf8")
            data = dict(
                resource=record,
                parameters=values,
                parameter_declarations=params,
                replaced_keywords=replaced,
                source_hash=fingerprint(path),
                solver_validated=False,
                native_mesh_verified=False,
                verification_scope="Parameter evaluation and native input loading only; no per-card, impact, SALE mesh generation or solver validation",
            )
            has_nodes = any(header(b) == "*NODE" for b in keyword_blocks(rendered))
            if native_check and has_nodes:
                opened = self.inspect_model(str(output))
                data["native_job_id"] = opened["job_id"]
                if opened["status"] != "succeeded":
                    raise ValueError("Native template reopen failed: " + str(opened.get("error")))
                if opened["data"]["counts"].get("nodes", 0) <= 0:
                    raise ValueError("Native template reopen did not load nodes")
                data.update(native_mesh_verified=True, native_counts=opened["data"]["counts"])
            elif native_check:
                data["native_check_note"] = (
                    "Template is a control/structured-mesh fragment with no explicit NODE block; supply a model for mesh reopen"
                )
            atomic_json(directory / "parameters.json", values)
            return data, [check_artifact(output, "keyword")]

        return self._post_job(
            "instantiate_installed_template",
            dict(
                template_id=template_id,
                parameters=parameters,
                units=units,
                model=model,
                native_check=native_check,
            ),
            [path] + ([source] if source else []),
            work,
        )
