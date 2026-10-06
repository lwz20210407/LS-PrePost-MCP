"""Stage the exact stdlib-only bridge dependencies beside a copied bridge."""

import shutil
from pathlib import Path


def stage_bridge(directory):
    directory = Path(directory)
    source = Path(__file__).parent
    bridge = directory / "bridge.py"
    shutil.copyfile(source.parent / "embedded.py", bridge)
    for name in ("commands.py", "versions.py", "_version_resource.py"):
        shutil.copyfile(source / name, directory / ("native_" + name))
    return bridge
