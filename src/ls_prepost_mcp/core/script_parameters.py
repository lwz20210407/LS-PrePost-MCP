"""Cfile interpolation preserves lines and keeps strings in quoted tokens."""

import math
import re

PLACEHOLDER = re.compile(r"\{\{([A-Za-z][A-Za-z0-9_]*)\}\}")


def render_cfile(source, parameters):
    if not isinstance(parameters, dict) or len(parameters) > 100:
        raise ValueError("Expected at most 100 named parameters")
    names = set(PLACEHOLDER.findall(source))
    if names != set(parameters):
        raise ValueError("Parameter names must exactly match placeholders")
    for key, value in parameters.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key):
            raise ValueError("Invalid parameter name")
        if type(value) is str:
            if not value or any(c in value for c in '\r\n\x00";') or "{{" in value or "}}" in value:
                raise ValueError("String parameters cannot contain command delimiters or placeholders")
        elif type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Parameters must be finite numbers or safe strings")
    def replace(match):
        value = parameters[match[1]]
        if isinstance(value, str):
            # Require the complete quoted argument, including no token suffix.
            if (source[max(0, match.start()-1):match.start()] != '"' or source[match.end():match.end()+1] != '"'
                    or match.start() > 1 and not source[match.start()-2].isspace()
                    or match.end()+1 < len(source) and not source[match.end()+1].isspace()):
                raise ValueError("String placeholder must occupy a complete double-quoted argument")
            return value
        return str(value)
    return PLACEHOLDER.sub(replace, source)


def cfile_diagnostics(source, log):
    """Locate errors from ordered native echo; never guess a missing line."""
    from .native_log import native_errors

    lines = source.splitlines()
    next_index, active, found = 0, None, []
    for echo in log.splitlines():
        text = echo.strip()
        if native_errors(echo):
            found.append(dict(line=active, message=text))
        elif text:
            for index in range(next_index, len(lines)):
                if lines[index].strip() == text:
                    active, next_index = index + 1, index + 1
                    break
    return found
