"""Byte-preserving LS-DYNA keyword engine (tasks.yaml I07; backend of P01, P02, P03, P10, P11).

Entry points
------------
``KeywordDeck.load(path)``
    Main deck plus every ``*INCLUDE`` (``_PATH``, ``_TRANSFORM``/``_AUTO_OFFSET`` file card,
    ``' +'`` name continuation). Missing, cyclic, repeated and ambiguous includes become
    ``deck.warnings``; nothing on disk is modified.
``deck.blocks(pattern)`` / ``deck.find(pattern, **fields)``
    Blocks (and table rows) in LS-DYNA reading order; ``*SECTION_SHELL`` matches its
    ``_TITLE``/``_ID`` variants, ``*MAT_*`` is a prefix match.
``deck.get / set / fields``
    Named fields with parameter provenance (``&name`` keeps the reference, ``value`` is
    resolved). Table keywords (``*NODE``, ``*PART``, ``*ELEMENT_*``, ...) need ``row=<key>``.
``deck.members / set_members``, ``deck.points / set_points``
    ``*SET_*_LIST`` / ``_ADD`` members and ``*DEFINE_CURVE`` points as whole lists.
``deck.set_parameter``, ``deck.insert``, ``deck.insert_card``, ``deck.delete``, ``deck.set_position``
    Parameter values, raw or field-built cards, guarded deletion, positional fallback.
``deck.references()``, ``deck.diff()``, ``deck.save_as(dir)``, ``deck.save_in_place()``
    Dangling/duplicate/unused IDs, unified diff, saving.
``operations.inspect_deck / read_fields / edit_deck`` and ``compare.compare_decks``
    JSON-friendly functions intended to back MCP tools; ``edit_deck`` is atomic.

Guarantees
----------
* Untouched files are copied byte for byte; untouched lines are never rewritten; an edited
  field keeps the alignment of the old value; line endings and file encoding are kept.
* Every named-field layout from PyDYNA is self-checked against PyDYNA's own parse (tables:
  first and last 20 rows plus headers). Disagreement raises :class:`Unsupported` instead of
  writing to a guessed position; positional editing remains available.
* Every write is read back; failures are reverted.

Formats: standard, long (``+`` or ``LONG=Y``), comma separated; i10 is positional only.

Measured on a private 84 MB deck (526,795 nodes, 492,903 solids): load 0.8 s, reference
check with mesh 12 s, element row edit 0.01 s after the first layout. The first PyDYNA
import costs 15-20 s per process: call :func:`warm_up` when a server starts.
"""
from .blocks import Block, SourceFile
from .deck import Change, FieldValue, IncludeRef, KeywordDeck
from .fields import FieldError
from .references import ReferencedError, ReferenceReport
from .schema import Layout, Unsupported, warm_up

__all__ = ["Block", "Change", "FieldError", "FieldValue", "IncludeRef", "KeywordDeck", "Layout", "ReferencedError", "ReferenceReport",
           "SourceFile", "Unsupported", "warm_up"]
