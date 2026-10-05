"""Observed capability policy, not a claim that an executable name is verified.

Keep compatible with embedded Python 3.6+. Runtime output validation remains
mandatory even for a supported profile; unknown installations are best effort.
"""

import re

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
MINIMUM_VECTOR_ABI = (3, 10)


def installation_version(executable):
    """Filename/directory hint only; never substitute for a native probe."""
    text = str(executable).replace("\\", "/")
    name = text.rsplit("/", 1)[-1]
    match = re.search(r"lsprepost[ _-]?(\d+\.\d+)", name, re.I)
    if match is None:
        match = re.search(r"LS-PrePost[^/]*?(\d+\.\d+)", text.rsplit("/", 1)[0], re.I)
    return match.group(1) if match else None


def profile(executable=None, version=None):
    if version is None:
        version = installation_version(executable or "")
    match = re.fullmatch(r"(\d+\.\d+)(?:\.\d+)*", version or "")
    key = match.group(1) if match else None
    data = CAPABILITIES.get(key, {"policy": "best_effort", "batch": True,
                                 "queue_model_identity": False, "evidence": "No verified profile"})
    return dict(data, version=key, version_source="configured_label" if executable is None else "path_hint",
                runtime_verified=False)


def require_installation(executable=None, version=None):
    result = profile(executable, version)
    if result["policy"] == "excluded":
        raise ValueError("LS-PrePost " + result["version"] + " is excluded by D3")
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
