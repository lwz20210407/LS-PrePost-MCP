"""Parameter evaluation in reading order with global and ``_LOCAL`` scopes.

Assumption (documented, conservative): a ``*PARAMETER_LOCAL`` definition is visible in
the file that defines it and in the files that file includes (its descendants).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .blocks import Block
from .fields import FieldError, format_value, write_text
from .includes import identity
from .parameters import ParameterDef, evaluate_definition, parse_definitions

if TYPE_CHECKING:
    from .deck import Change, KeywordDeck


@dataclass
class ParameterRecord:
    definition: ParameterDef
    block: Block


@dataclass
class Scopes:
    records: list[ParameterRecord]
    global_scope: dict[str, object]
    local: dict[str, dict[str, object]]
    parents: dict[str, str]

    def ancestors(self, key: str) -> list[str]:
        chain = []
        while key in self.parents:
            key = self.parents[key]
            chain.append(key)
        return chain

    def visible(self, key: str) -> dict[str, object]:
        scope = dict(self.global_scope)
        for owner in reversed([key] + self.ancestors(key)):
            scope.update(self.local.get(owner, {}))
        return scope


def evaluate(deck: KeywordDeck) -> Scopes:
    """Evaluate every parameter definition; problems are appended to ``deck.warnings``."""
    scopes = Scopes([], {}, {}, deck._parents)
    for block in deck.iter_blocks():
        if not block.name.startswith("*PARAMETER"):
            continue
        key = identity(block.file.path)
        definitions, problems = parse_definitions(block.name, block.data())
        deck.warnings.extend(f"{deck._where(block)} {problem}" for problem in problems)
        for definition in definitions:
            evaluate_definition(definition, scopes.visible(key))
            target = scopes.local.setdefault(key, {}) if definition.local else scopes.global_scope
            if definition.key in target:
                deck.warnings.append(f"Parameter {definition.name!r} redefined at {deck._where(block)}")
            target[definition.key] = definition.value
            scopes.records.append(ParameterRecord(definition, block))
    for record in scopes.records:
        definition = record.definition
        if definition.error and "Undefined parameter" in definition.error:
            key = identity(record.block.file.path)
            evaluate_definition(definition, scopes.visible(key))
            if definition.error is None:
                target = scopes.local.setdefault(key, {}) if definition.local else scopes.global_scope
                target[definition.key] = definition.value
                deck.warnings.append(f"Parameter {definition.name!r} refers to a parameter defined later")
    for record in scopes.records:
        if record.definition.error:
            deck.warnings.append(f"Parameter {record.definition.name!r}: {record.definition.error}")
    return scopes


def set_parameter(deck: KeywordDeck, name: str, value: object, file: str | None = None) -> Change:
    """Change one ``*PARAMETER`` value (or ``*PARAMETER_EXPRESSION`` text) in place.

    All parameters are re-evaluated afterwards, so dependent expressions follow. The edit
    is reverted if the new definition does not evaluate.
    """
    key = name.lower()
    wanted = identity(Path(file)) if file else None
    records = [r for r in deck.parameters
               if r.definition.key == key and (wanted is None or identity(r.block.file.path) == wanted)]
    if not records:
        raise KeyError(f"No parameter {name!r}")
    if len(records) > 1:
        places = [deck._where(r.block) for r in records]
        raise FieldError(f"Parameter {name!r} is defined {len(records)} times ({places}); give file=")
    definition, block = records[0].definition, records[0].block
    slot = definition.value_slot
    if slot is None:
        raise FieldError(f"Parameter {name!r} has no editable value field")
    exact = True
    if definition.expression or definition.type == "character":
        text, align = str(value).strip(), "left"
        if slot.token is None and len(text) > slot.width:
            raise FieldError(f"{text!r} does not fit in {slot.width} characters")
    else:
        width = slot.width if slot.token is None else 40
        text, exact = format_value(value, width, "int" if definition.type == "integer" else "float")
        align = "right"
    before = block.lines[slot.line]
    block.lines[slot.line] = write_text(before, slot, text, align)
    change = deck._record(block, slot.line, f"parameter {definition.name}={text}", before, exact)
    updated = [r.definition for r in deck.parameters if r.definition.key == key and r.block is block]
    if not updated or updated[0].error:
        block.lines[slot.line] = before
        deck.changes.remove(change)
        deck._rebuild()
        problem = updated[0].error if updated else "definition disappeared"
        raise FieldError(f"New value for {name!r} does not evaluate: {problem}")
    return change
