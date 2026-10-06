"""Verified command grammar shared by host and embedded Python 3.6+.

Builders preserve native user IDs, zero-based buffers and one-based states.
They validate syntax; the caller still verifies native selection/field results.
"""

import math
import os
import re

TARGETS = frozenset(("node", "element", "shell", "solid", "beam", "tshell", "part"))
CFILE_ENCODING = "utf-8"
SCL_ENCODING = "utf-8"


def quoted_path(path, style="posix"):
    if not isinstance(path, (str, os.PathLike)):
        raise ValueError("Native path must be text or path-like")
    value = os.fspath(path)
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or c in '\";' for c in value):
        raise ValueError("Native path contains unsupported quotes, separators or control characters")
    choice(style, ("posix", "native"), "path style")
    return '"' + (value.replace("\\", "/") if style == "posix" else value) + '"'


def open_model(path, kind="keyword", openc=False, style="posix"):
    choice(kind, ("keyword", "d3plot"), "model kind")
    if type(openc) is not bool:
        raise ValueError("openc must be Boolean")
    return ("openc " if openc else "open ") + kind + " " + quoted_path(path, style)


def print_png(path, mode="opaque", window="OGL1x1", style="posix"):
    choice(mode, ("opaque", "nogamma"), "PNG mode")
    if not isinstance(window, str) or not re.fullmatch(r"(?:OGL\d+x\d+|PlotWindow-\d+)", window):
        raise ValueError("Unsupported native print window")
    return "print png " + quoted_path(path, style) + ' ' + mode + ' enlisted "' + window + '"'


def movie(path, width, height, fps, style="native"):
    integer(width, "movie width", 1, 8192)
    integer(height, "movie height", 1, 8192)
    integer(fps, "movie fps", 1, 240)
    return "movie MP4/H264 {}x{} {} {}".format(width, height, quoted_path(path, style), fps)


def run_script(path, language="python", style=None):
    choice(language, ("python", "scl", "cfile"), "script language")
    style = ("native" if language == "scl" else "posix") if style is None else style
    if language == "cfile":
        return "openc command " + quoted_path(path, style) + " nodialog"
    return ("runpython " if language == "python" else "runscript ") + quoted_path(path, style)


def save_keyword(path, style="posix"):
    return "save keyword " + quoted_path(path, style)


def import_keyword(path, style="posix"):
    return "import keyword " + quoted_path(path, style)


def open_xydata(path, style="posix"):
    return "open xydata " + quoted_path(path, style)


def save_xypair(path, plot_id=1, style="posix"):
    integer(plot_id, "plot window", 1, 2147483647)
    return "xyplot {} savefile xypair {} 1 all".format(plot_id, quoted_path(path, style))


def modelcheck_report(path, style="posix"):
    return "modelcheck writetofile " + quoted_path(path, style)


def write_scl(path, source):
    if not isinstance(source, str):
        raise ValueError("SCL source must be text")
    # Normalize generated source on every host; UTF-8 is emitted without a BOM.
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "w", encoding=SCL_ENCODING, newline="\n") as stream:
        stream.write(source)


def write_cfile(path, commands):
    text = commands if isinstance(commands, str) else "\n".join(commands) + "\n"
    with open(path, "w", encoding=CFILE_ENCODING, newline="\n") as stream:
        stream.write(text)


def integer(value, name, minimum=1, maximum=2000000000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("{} must be an integer in {}..{}".format(name, minimum, maximum))
    return value


def choice(value, allowed, name):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError("Unsupported " + name)
    return value


def selection(action):
    return "genselect " + choice(action, ("clear", "whole", "adjacent", "reverse"), "selection action")


def selection_target(target):
    return "genselect target " + choice(target, TARGETS, "selection target")


def selection_add(target, identifier, source=None):
    choice(target, TARGETS, "selection target")
    source = target if source is None else source
    choice(source, (target, "part"), "selection source")
    return "genselect {} add {} {}".format(target, source, integer(identifier, "user ID"))


def selection_buffer(action, index):
    choice(action, ("save", "load"), "buffer action")
    return "genselect {} {}".format(action, integer(index, "buffer index", 0, 9))


def selection_transfer(value):
    return "genselect transfer " + str(integer(value, "selection transfer", 0, 1))


def selection_propagation(enabled, adaptive=False):
    if type(enabled) is not bool or type(adaptive) is not bool:
        raise ValueError("Propagation flags must be Boolean")
    return "genselect propagate " + ("adaptive " if adaptive else "") + ("on" if enabled else "off")


def selection_surface(enabled):
    if type(enabled) is not bool:
        raise ValueError("Surface flag must be Boolean")
    return "genselect 3dsurf " + ("on" if enabled else "off")


def feature_angle(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 180:
        raise ValueError("Feature angle must be finite in 0..180")
    return "genselect propagate featang " + repr(value)


def animation(action, value=None):
    choice(action, ("stop", "start", "forward", "backward", "cycle", "first", "last", "incr"), "animation action")
    if action in ("first", "last", "incr"):
        return "anim {} {}".format(action, integer(value, "animation state/increment"))
    if value is not None:
        raise ValueError("Animation action takes no numeric argument")
    return "anim " + action


def state(index):
    return "state " + str(integer(index, "state"))


def fringe(code):
    return "fringe " + str(integer(code, "fringe code", 1, 9999))


def plot_fringe():
    return "pfringe"


def averaging(value):
    return "range avgfrng " + choice(value, ("none", "nodal", "minmax"), "averaging")


def reverse_signs(enabled):
    if type(enabled) is not bool:
        raise ValueError("Reverse-signs flag must be Boolean")
    return "range reversesigns " + ("on" if enabled else "off")


def fringe_bounds(low, high):
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (low, high)) or low >= high:
        raise ValueError("Fringe bounds must be ordered finite numbers")
    return "range userdef {:.17g} {:.17g};".format(low, high)


VIEWS = {"isometric": "isometric x", "top": "top", "bottom": "bottom", "front": "front",
         "back": "back", "left": "left", "right": "right"}
