"""Observed capability policy, not a claim that an executable name is verified.

Keep compatible with embedded Python 3.6+. Runtime output validation remains
mandatory even for a supported profile; unknown installations are best effort.
"""

import os
import re

if __package__:
    from ._version_resource import read_version_resource
else:
    import importlib.util

    _folder = os.path.dirname(os.path.abspath(__file__))
    _helper = os.path.join(_folder, "native__version_resource.py")
    if not os.path.isfile(_helper):
        _helper = os.path.join(_folder, "_version_resource.py")
    _spec = importlib.util.spec_from_file_location("_lspp_version_resource", _helper)
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    read_version_resource = _module.read_version_resource

CAPABILITIES = {
    "4.13": {"policy": "primary", "batch": True, "queue_model_identity": True,
             "evidence": "I01: six native regression cases; KI-048 comparison"},
    "4.10": {"policy": "regression_subset", "batch": True, "queue_model_identity": False,
             "evidence": "I01: five batch callers passed; queue source identity rejected (KI-048)"},
    "4.8": {"policy": "best_effort", "batch": True, "queue_model_identity": False,
            "evidence": "Historical SCL subset; queue model identity unverified"},
    "4.11": {"policy": "excluded", "batch": False, "queue_model_identity": False,
             "evidence": "User decision D3"},
}
DEPENDENCIES = {"lasso-python": "2.0.4", "ansys-dpf-core": "0.16.1"}
DPF_SERVER_MINIMUM = "7.1"
MINIMUM_VECTOR_ABI = (3, 10)


def _path_version(executable):
    text = str(executable).replace("\\", "/")
    name = text.rsplit("/", 1)[-1]
    match = re.search(r"lsprepost[ _-]?(\d+\.\d+)", name, re.I)
    if match is None:
        match = re.search(r"LS-PrePost[^/]*?(\d+\.\d+)", text.rsplit("/", 1)[0], re.I)
    return match.group(1) if match else None


def _family(version):
    match = re.fullmatch(r"(\d+\.\d+)(?:\.\d+)*", (version or "").strip())
    return match.group(1) if match else None


def _is_lspp(resource):
    product = (resource or {}).get("product_name") or ""
    return "lsprepost" in product.lower().replace("-", "").replace(" ", "")


def _resource_family(resource):
    if not resource or resource.get("product_name") and not _is_lspp(resource):
        return None
    versions = [_family(resource.get(name)) for name in ("file_version", "product_version", "fixed_file_version")]
    if "4.11" in versions:
        return "4.11"
    return next((value for value in versions if value), None)


def installation_version(executable):
    """Resource family when identifiable, otherwise an unverified path hint."""
    resource = read_version_resource(executable)
    return _resource_family(resource) or _path_version(executable)


def profile(executable=None, version=None):
    resource = read_version_resource(executable) if executable is not None else None
    hint = _path_version(executable or "")
    resource_family = _resource_family(resource)
    detected = resource_family or hint
    requested = _family(version) if version is not None else None
    file_family = _family((resource or {}).get("file_version"))
    product_family = _family((resource or {}).get("product_version"))
    key = detected or requested
    data = CAPABILITIES.get(key, {"policy": "best_effort", "batch": True,
                                 "queue_model_identity": False, "evidence": "No verified profile"})
    source = "file_version_resource" if resource_family else "configured_label" if executable is None else "path_hint"
    return dict(data, version=key, version_source=source, runtime_verified=False,
                file_version=(resource or {}).get("file_version"), product_name=(resource or {}).get("product_name"),
                fixed_file_version=(resource or {}).get("fixed_file_version"),
                product_version=(resource or {}).get("product_version"),
                resource_conflict=len({_family(value) for name, value in (resource or {}).items()
                                       if name.endswith("version") and _family(value)}) > 1,
                resource_string_conflict=bool(file_family and product_family and file_family != product_family),
                requested_version=requested,
                configured_label_conflict=bool(requested is not None and detected and requested != detected),
                path_hint_version=hint, path_hint_conflict=bool(resource_family and hint and hint != detected))


def require_installation(executable=None, version=None):
    result = profile(executable, version)
    if result["product_name"] and not _is_lspp(result):
        raise ValueError("Executable version resource identifies a different product: " + result["product_name"])
    if result["policy"] == "excluded":
        raise ValueError("LS-PrePost " + result["version"] + " is excluded by D3")
    if result["resource_string_conflict"]:
        raise ValueError("Executable file/product version strings disagree")
    if result["configured_label_conflict"]:
        raise ValueError("Configured version label conflicts with detected executable family")
    return result


def require_capability(executable, capability):
    result = require_installation(executable)
    if capability not in ("batch", "queue_model_identity"):
        raise ValueError("Unknown native capability")
    if result[capability] is not True:
        raise ValueError("Native capability {} is unavailable for {}: {}".format(
            capability, result["version"] or "unknown installation", result["evidence"]))
    return result


def require_vector_abi(python_version):
    if tuple(python_version[:2]) < MINIMUM_VECTOR_ABI:
        raise RuntimeError(
            "Native vector arrays on the older embedded Python ABI did not pass numerical cross-checks. "
            "Use the explicit LASSO/LS-Reader tools or the verified 4.13 profile.")


def dependency_supported(name, actual):
    if name not in DEPENDENCIES:
        raise ValueError("Unknown dependency capability")
    return actual == DEPENDENCIES[name]
