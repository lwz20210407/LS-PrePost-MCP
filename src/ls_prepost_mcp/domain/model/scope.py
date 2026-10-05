"""Parameter evaluation in reading order with global and ``_LOCAL`` scopes.

Assumption (documented, conservative): a ``*PARAMETER_LOCAL`` definition is visible in
the file that defines it and in the files that file includes (its descendants).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .blocks import Block
from .includes import identity
from .parameters import ParameterDef, evaluate_definition, parse_definitions

if TYPE_CHECKING:
    from .deck import KeywordDeck


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
