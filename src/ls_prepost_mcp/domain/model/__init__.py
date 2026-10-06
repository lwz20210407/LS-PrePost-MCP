"""Byte-preserving LS-DYNA keyword engine (tasks.yaml I07; backend of P01, P02, P03, P04, P06, P08, P09, P10, P11).

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
``geometry`` and ``sets.create_set``
    Node/element selection (box, sphere, plane, parts), exterior segments with outward
    normals, new ``*SET_*`` blocks. Element variants with the same connectivity (``_THICKNESS``,
    ``_ORTHO``, ...) are included; other variants raise :class:`Unsupported`, never vanish.
``operations.check_deck`` and ``quality.check_quality``
    Model check without LS-PrePost: missing/cyclic includes, parameter errors, dangling and
    duplicate IDs, inverted elements, quality distributions (scaled Jacobian, aspect ratio,
    warpage, angles), coincident nodes. Metrics are judged only against caller thresholds;
    element blocks that cannot be read are listed as unchecked.
``contact.check_penetration`` and ``operations.check_contacts``
    Initial penetration of slave nodes into master surfaces, per *CONTACT definition; closest
    feature with pseudonormal sign, shell thickness offsets; read-only.
``cases.generate_cases``
    Parameter-study decks, one directory per case, each compared with the base deck.
``mesh`` (transform / translate / rotate / reflect nodes, reverse elements, unify shell normals)
    Only selected rows change; mirrored elements are reordered back to positive orientation.
``renumber`` (renumber, renumber_range, merge_duplicate_nodes, delete_elements)
    IDs change in their definitions and in every referring field: hand rules plus the PyDYNA
    link metadata of :mod:`links`, set members and contact surfaces. Refused, with nothing
    changed, when a block that may refer to the kind cannot be read, a GENERATE range or a
    parameter expression is involved, or new IDs collide; verified by a second reference scan.

Guarantees
----------
* Untouched files are copied byte for byte; untouched lines are never rewritten; an edited
  field keeps the alignment of the old value; line endings and file encoding are kept.
* Every named-field layout from PyDYNA is self-checked against PyDYNA's own parse (tables:
  first and last 20 rows plus headers). Disagreement raises :class:`Unsupported` instead of
  writing to a guessed position; positional editing remains available.
* Because PyDYNA can be wrong in the same way as the layout, a block is also refused when a
  keyword-name option is unknown to PyDYNA or a line holds text outside the fields of its card
  (zero trailing fields excepted on multi-field cards).
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
