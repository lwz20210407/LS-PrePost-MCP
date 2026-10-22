"""Explicit immutable dependency bundles for user-directed native programs."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath


def relative_name(name):
    if (not isinstance(name, str) or not name or len(name) > 180 or "\\" in name
            or any(ord(c) < 32 or c in '<>:"|?*' for c in name)):
        raise ValueError("Dependency name must be a portable relative file path")
    path = PurePosixPath(name)
    if path.is_absolute() or str(path) != name or any(part in (".", "..") for part in path.parts):
        raise ValueError("Dependency paths cannot escape or contain ambiguous components")
    for part in path.parts:
        if part.endswith((".", " ")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", part.split(".")[0]):
            raise ValueError("Dependency path contains a Windows reserved name")
    return name


def validate_names(names, outputs):
    from .programs import RESERVED

    occupied = set(RESERVED) | {"contract.json", "macro.json", "stdout.log", "stderr.log", "tmp",
                               "cwd.py", "gui-python.py", "before.json", "after.json", "native.log", "commands.json"}
    occupied.update(item["name"].casefold() for item in outputs)
    seen = set()
    for name in names:
        parts = relative_name(name).casefold().split("/")
        if parts[0] in occupied or parts[0].startswith("lspost.") or re.fullmatch(r"d3plot\d*", parts[0]):
            raise ValueError("Dependency conflicts with an output or reserved job file")
        folded = "/".join(parts)
        if any(folded == other or folded.startswith(other+"/") or other.startswith(folded+"/") for other in seen):
            raise ValueError("Duplicate or file/directory-conflicting dependencies")
        seen.add(folded)


def capture_dependencies(settings, dependencies, outputs):
    dependencies = dependencies or []
    if not isinstance(dependencies, list) or len(dependencies) > 100:
        raise ValueError("Declare at most100 dependency files")
    if any(not isinstance(item, dict) or set(item) != {"path", "name"} for item in dependencies):
        raise ValueError("Dependencies require explicit path and bundle-relative name")
    validate_names([item["name"] for item in dependencies], outputs)
    captured, total = [], 0
    for item in dependencies:
        source = settings.input_path(item["path"])
        if total + source.stat().st_size > 64*1024**2:
            raise ValueError("Dependency bundle exceeds64MiB; model/result inputs use separate staging")
        with source.open("rb") as stream:
            content = stream.read(64*1024**2-total+1)
        total += len(content)
        if total > 64*1024**2:
            raise ValueError("Dependency changed size during preparation")
        captured.append((dict(name=item["name"], source=str(source), size=len(content),
                              sha256=hashlib.sha256(content).hexdigest()), content))
    return captured


def identity(content, contract):
    source_hash = hashlib.sha256(content).hexdigest()
    if not contract.get("dependencies") and "python_parameters" not in contract:
        return source_hash  # Preserve existing single-file execution tokens.
    canonical = dict(source_sha256=source_hash, language=contract["language"],
                     files=[{k:item[k] for k in ("name", "size", "sha256")}
                            for item in sorted(contract.get("dependencies", []), key=lambda x:x["name"])],
                     outputs=contract["outputs"], expected_counts=contract["expected_counts"])
    if "python_parameters" in contract:
        canonical["python_parameters"] = contract["python_parameters"]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf8")).hexdigest()


def checked_dependencies(directory, contract):
    entries = contract.get("dependencies", [])
    if not isinstance(entries, list) or len(entries) > 100:
        raise ValueError("Invalid dependency manifest")
    validate_names([item["name"] for item in entries], contract["outputs"])
    result, total = [], 0
    for item in entries:
        path = (Path(directory) / item["name"]).resolve()
        if not path.is_relative_to(Path(directory).resolve()):
            raise ValueError("Dependency escaped the prepared bundle")
        total += path.stat().st_size
        if total > 64*1024**2:
            raise ValueError("Dependency bundle exceeds64MiB")
        content = path.read_bytes()
        if len(content) != item["size"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("Dependency changed since preparation: " + item["name"])
        result.append((item, content))
    return result


def write_dependencies(directory, captured):
    for item, content in captured:
        target = Path(directory) / item["name"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)


def validate_script_references(content, language, captured, *, filename_executable=None):
    """Check literal native script loads; Python imports/SCL semantics are not inferred."""
    entry = "program." + {"command":"cfile", "cfile":"cfile", "scl":"scl", "python":"py"}[language]
    files = {entry: content, **{item["name"]:data for item, data in captured}}
    expression = re.compile(r'^\s*((?:open|openc)\s+command|runpython|runscript|import\s+keyword|open\s+xydata)\s+(?:"([^"]+)"|([^;\s]+))', re.I)
    graph = {name:[] for name in files}
    pending = [entry] if language in ("command", "cfile") else []
    parsed = set()
    while pending:
        name = pending.pop()
        if name in parsed:
            continue
        parsed.add(name)
        for line in files[name].decode("utf-8-sig").splitlines():
            stripped = line.lstrip()
            if not stripped or stripped.startswith(("$", "#")) or stripped.split()[0].lower() == "c":
                continue
            segments, current, quoted = [], "", False
            for char in line:
                if char == '"':
                    quoted = not quoted
                if char == ";" and not quoted:
                    segments.append(current)
                    current = ""
                else:
                    current += char
            segments.append(current)
            for segment in segments:
                match = expression.match(segment)
                if not match:
                    continue
                target = (match[2] or match[3]).replace("\\", "/")
                operation = " ".join(match[1].lower().split())
                if operation in ("import keyword", "open xydata", "runscript") and filename_executable is not None:
                    # Absolute reader paths and embedded Python/SCL contents are
                    # outside this relative filename policy. Do not infer a
                    # reader from a dependency extension or rewrite user code.
                    if not PurePosixPath(target).is_absolute() and not re.match(r"^[A-Za-z]:", target):
                        from .native.versions import require_bundle_filename

                        require_bundle_filename(operation, target, filename_executable)
                if operation in ("import keyword", "open xydata"):
                    continue
                relative_name(target)
                if target not in files:
                    raise ValueError("Native script reference is not declared in the bundle: " + target)
                graph[name].append(target)
                if "command" in match[1].lower():
                    pending.append(target)

    visiting, depths = set(), {}
    def visit(name):
        if name in visiting:
            raise ValueError("Cyclic native script dependency")
        if name not in depths:
            visiting.add(name)
            depth = 1 + max((visit(target) for target in graph[name]), default=0)
            if depth > 16:
                raise ValueError("Over-depth native script dependency")
            visiting.remove(name)
            depths[name] = depth
        return depths[name]
    for name in graph:
        visit(name)
    return graph


def python_wrapper(directory, dependency_names, parameters=None):
    # Valid on the older embedded Python grammar. Isolate declared module names
    # and remove modules loaded from this job; leave SDK/stdlib modules intact.
    roots = sorted({(n.split("/")[0] if "/" in n else n[:-3]) for n in dependency_names if n.endswith(".py")})
    payload = json.dumps(parameters or {}, allow_nan=False)
    return "_root=" + repr(str(Path(directory).resolve())) + "\n_names=" + repr(roots) + "\n_parameters_json=" + repr(payload) + "\n" + """import os,sys,json,runpy,traceback
_path=list(sys.path)
_cwd=os.getcwd()
_initial=set(sys.modules)
_shadow={k:v for k,v in list(sys.modules.items()) if any(k==n or k.startswith(n+'.') for n in _names)}
for _key in _shadow:sys.modules.pop(_key,None)
_reply={'ok':False}
try:
    os.chdir(_root)
    sys.path.insert(0,_root)
    runpy.run_path(os.path.join(_root,'program.py'),run_name='__main__',init_globals={'PARAMETERS':json.loads(_parameters_json)})
    _reply['ok']=True
except BaseException as _exc:
    _reply.update(error=type(_exc).__name__+': '+str(_exc),traceback=traceback.format_exc())
finally:
    for _key,_module in list(sys.modules.items()):
        _file=getattr(_module,'__file__',None)
        _owned=False
        if isinstance(_file,str):
            try:_owned=os.path.commonpath([os.path.abspath(_file),_root])==_root
            except ValueError:pass
        if (_owned and _key not in _initial) or any(_key==n or _key.startswith(n+'.') for n in _names):sys.modules.pop(_key,None)
    sys.modules.update(_shadow)
    sys.path[:]=_path
    os.chdir(_cwd)
with open(os.path.join(_root,'python-result.json'),'w') as _fp:json.dump(_reply,_fp)
"""
