# Review02 I06 evidence and workflow hygiene

The existing check_doc_links CI step now rejects individual JSON files over 512 KiB under docs/decisions/evidence before parsing them; normal JSON/Markdown link validation remains active. New and touched review records use compact JSON and explicit historical/current tables. This does not claim every old report has been reformatted.

The remote evidence reporter nested pytest now allows 120 seconds rather than 30. A fake subprocess checks the configured bound without sleeping; the real nested report test still verifies failed native lanes stay evidence_only.

Baseline 0563045: two new regressions failed (oversized JSON was accepted; timeout was 30) and one missing-link control passed. Corrected related tests: 18 passed. [evidence.json](evidence.json) records the baseline stdout hash. No native/solver run is claimed.

README now says public development repository; COORDINATION follows review02 and the paused multi-AI rules. The historical AGENTS collaboration section is unchanged. This change does not modify task scope, acceptance or completion status.

| Record | 当前有效 / 已被取代 |
|---|---|
| Baseline failure output hash | Historical regression evidence |
| Size/link and subprocess configuration checks | Current for the submitted implementation |
