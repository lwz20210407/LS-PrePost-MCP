# G03 / P09 host regression evidence (partial)

Actual clean integration source `2911adeec75a1f504976d66f8a7bdd999ca29d3a`, full snapshot `a3cd7ff84dc977b5af75577d34add6b70b6da65592f11aa711c3644f911c4c88`. The combined focused suite passed 110 tests; source was measured immediately before and after pytest and was equal. These are host checks, not native-panel or solver acceptance.

G03 counts the three real corners of supported Tri3 padding for both shared Selector spatial predicates and legacy box selection. The handwritten triangle has true center (1,1,0); the former padded mean (.75,1.5,0) must not select it. Raw connectivity, input bytes, reference IDs and quad behavior are retained. Original clean-main external reproduction was 1 failed / 1 quad control passed; the separate legacy reproduction was 3 failed / 1 quad-order control passed. Both histories retain their actual sources.

P09 reports plain BEAM N1-N2 length in model coordinates. Only explicitly written ordinary SECTION_BEAM formulations 1/2/4/5/11/12/13/14 receive objective zero-length errors. Special, unknown or implicit forms retain geometric observations and incomplete coverage. Missing/unread/ambiguous endpoints and non-finite lengths are distinguished; no default physical length threshold is introduced. TSHELL, orientation, section mechanics and native quality equivalence remain unassessed. The four original main failures are retained; the recovered original test file is capture-hash verified and does not represent another red execution.

SDK-absence simulation passed 11 and skipped 45 dependent cases, with zero Ansys dyna core modules loaded; this is not a full minimal environment. A separate small 15-node, 3-element shell/solid/tetra control yielded identical complete canonical quality reports against the original main both with and without caller thresholds. The default unused-node interpretation is unchanged.

Tasks remain partial. Native finite mesh and dependent source-refresh observations are published separately with their actual UUIDs. Internal review and CI do not replace the user-arranged independent review required for a done transition.
