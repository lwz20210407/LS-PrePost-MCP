"""Verified command grammar shared by host and embedded Python 3.6+.

Builders preserve native user IDs, zero-based buffers and one-based states.
They validate syntax; the caller still verifies native selection/field results.
"""

import math

TARGETS = frozenset(("node", "element", "shell", "solid", "beam", "tshell", "part"))


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


def bind_output_paths(command, names, directory):
    """Bind exact declared filename tokens; preserve all other command bytes."""
    import re

    names = set(names)
    def replace(match):
        token = match.group(0)
        name = token[1:-1] if token.startswith('"') else token
        if name not in names:
            return token
        if any(char in name for char in '/\\\r\n"') or name in (".", ".."):
            raise ValueError("Declared output must be a plain filename")
        separator = "\\" if "\\" in directory else "/"
        return '"' + directory.rstrip("/\\") + separator + name + '"'
    return re.sub(r'"[^"\r\n]*"|[^\s"]+', replace, command)
