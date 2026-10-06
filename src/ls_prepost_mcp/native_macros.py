"""Bounded native *macro blocks compiled for the existing reviewed cfile route.

This is not the native interactive picker or a general command interpreter.
Unresolved picks, expression defaults and interactive pauses fail preparation.
"""

import math
import re

NAME = r"[A-Za-z][A-Za-z0-9_]{0,63}"
REFERENCE = re.compile(r"&(?:\{(" + NAME + r")\}|(" + NAME + r"))(?:\(([nep])\))?")
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def syntax_error(line, message):
    return ValueError("line {}: {}".format(line, message))


def comment(line):
    stripped = line.strip()
    return not stripped or stripped.startswith('$') or stripped.lower() == 'c' or stripped.lower().startswith('c ')


def parse_blocks(code):
    blocks, current, start = {}, None, None
    for number, line in enumerate(code.splitlines(), 1):
        stripped = line.strip()
        if comment(line):
            if current is not None:
                blocks[current]['lines'].append(line)
            continue
        if ';' in line or '{{' in line or '}}' in line:
            raise syntax_error(number, 'Bound native macros require one command per line and native & parameters')
        begin = re.fullmatch(r"\*macro\s+begin\s+(.+)", stripped, re.I)
        if begin:
            name = begin[1].strip()
            if current is not None or name in blocks or len(name) > 120 or any(c in name for c in '\x00\r\n'):
                raise syntax_error(number, 'Nested, duplicate or invalid native macro block')
            current, start = name, number
            blocks[name] = dict(lines=[], first_line=start)
        elif re.fullmatch(r"\*macro\s+end", stripped, re.I):
            if current is None:
                raise syntax_error(number, 'Native macro end without begin')
            blocks[current]['last_line'] = number
            current = None
        elif stripped.lower().startswith('*macro') or current is None:
            raise syntax_error(number, 'Unexpected directive or executable text outside a native macro block')
        else:
            blocks[current]['lines'].append(line)
    if current is not None or not blocks:
        raise syntax_error(start or 1, 'Expected complete *macro begin/name/end block(s)')
    return blocks


def compile_macro(code, parameters, macro_name=None):
    """Bind finite numeric values; emit native-editable macro and explicit cfile."""
    from .programs import numeric_parameters

    numeric_parameters(parameters)
    blocks = parse_blocks(code)
    if macro_name is None:
        if len(blocks) != 1:
            raise ValueError('Multiple native macros: select macro_name explicitly: ' + ', '.join(blocks))
        macro_name = next(iter(blocks))
    if macro_name not in blocks:
        raise ValueError('Unknown native macro_name')
    block, defaults, picks, names, body = blocks[macro_name], {}, {}, set(), []
    saw_command, reference_lines = False, {}
    for number, line in enumerate(block['lines'], block['first_line'] + 1):
        if comment(line):
            body.append(line)
            continue
        stripped = line.strip()
        if re.match(r"parameter(?:\s|$)", stripped, re.I):
            match = re.fullmatch(r"parameter\s+(" + NAME + r")\s+(\S+)", stripped, re.I)
            if not match or not NUMBER.fullmatch(match[2]) or saw_command:
                raise syntax_error(number, 'Native macro defaults must be literal numbers before commands; expressions/reassignment need explicit native review')
            key, raw = match[1], match[2]
            if key in defaults:
                raise syntax_error(number, 'Duplicate native parameter default: ' + key)
            value = int(raw) if re.fullmatch(r'[+-]?\d+', raw) else float(raw)
            if not math.isfinite(value):
                raise syntax_error(number, 'Native macro default must be finite')
            defaults[key] = value
            names.add(key)
            continue
        if re.match(r'interactive(?:\s|$)', stripped, re.I):
            raise syntax_error(number, 'Interactive native macro requires a pause/resume controller; not a bound cfile')
        saw_command = True
        for match in REFERENCE.finditer(line):
            if match.end() < len(line) and line[match.end()] == '(':
                raise syntax_error(number, 'Unsupported native pick suffix')
            key, pick = match[1] or match[2], match[3]
            reference_lines.setdefault(key, number)
            names.add(key)
            if pick:
                if key in picks and picks[key] != pick:
                    raise syntax_error(number, 'Conflicting native pick domains: ' + key)
                picks[key] = pick
        if '&' in REFERENCE.sub('', line):
            raise syntax_error(number, 'Unsupported native parameter reference syntax')
        body.append(line)
    if len(names) > 100 or not saw_command:
        raise syntax_error(block['first_line'], 'Native macro requires commands and at most 100 numeric parameters')
    if parameters.keys() - names:
        raise ValueError('Unknown native macro parameters: ' + ', '.join(sorted(parameters.keys()-names)))
    values = {**defaults, **parameters}
    missing = names - values.keys()
    if missing:
        raise syntax_error(min(reference_lines[key] for key in missing), 'Missing native macro parameters/picks: ' + ', '.join(sorted(missing)))
    for key in picks:
        if type(values[key]) is not int or values[key] <= 0:
            raise syntax_error(reference_lines[key], 'Picked node/element/part parameters require positive integer user IDs: ' + key)
    # Native Macro/Exec sets parameters before dispatching its resolved commands.
    # Retain those definitions for explicitly declared child cfiles as well.
    definitions = ''.join('parameter ' + key + ' ' + repr(value) + '\n' for key, value in sorted(values.items()))
    commands = definitions + '\n'.join(line if comment(line) else REFERENCE.sub(
        lambda m: repr(values[m[1] or m[2]]), line) for line in body) + '\n'
    native = '*macro begin ' + macro_name + '\n'
    native += definitions
    native += '\n'.join(body) + '\n*macro end\n'
    metadata = dict(name=macro_name, available_macros=list(blocks), parameters=values,
                    pick_domains={key:dict(n='node', e='element', p='part')[value] for key, value in picks.items()},
                    first_line=block['first_line'], last_line=block['last_line'],
                    scope='Numeric native macro binding to cfile; user IDs are not existence-checked; no interactive pick, toolbar, shortcut or pause/resume certification')
    return commands, native, metadata
