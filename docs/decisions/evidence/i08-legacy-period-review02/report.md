# Review02 I08 portable compatibility metadata

The runtime already supplied v0.6 as its Python Operation default; raw operations.json omitted that field on 142 legacy records. They now explicitly record legacy_until=v0.6. The 21 T1/target rows retain null. Names, signatures, dispatch and the total 163 operations are unchanged.

The current v0.4 compatibility default stays full. Users can opt into LSPP_TOOL_PROFILE=compact (three discovery/description/execution entry points with the same implementations); switching the v0.5 default is a separate release decision, not an implicit removal of old aliases.

| Evidence | 当前有效 / 已被取代 |
|---|---|
| 0563045 raw metadata regression failed | Historical: inspect_result_validity relies on Python-only default |
| Related 11 tests passed on clean 7bd43ba | Current for recorded JSON blob |

[evidence.json](evidence.json) records the actual revision and baseline stdout hash. One earlier baseline harness attempt looked for data relative to the copied test file and failed to locate it; it is not counted. The corrected test locates the actual imported product registry on both versions. No native run or new feature completion is claimed.
