# Review02 P1-2: required checks control the job verdict

JobResult construction now derives failed from failed/invalid required checks, and unverified from missing required evidence in a claimed success. This is done before validation/freeze without changing the caller's dictionary. Existing error details survive as cause. Edit outputs with failed reload verification are retained for diagnosis with verification=unverified, and the job manifest matches the failed public result.

CheckResult.required is a strict boolean, default true. This is an additive field with conservative legacy behavior: old typed JSON without the field is treated as required. The new policy deliberately changes prior tests that expected result_info to succeed on native disagreement, and run_script to remain partial despite a failed required image check.

The repository audit found intentionally diagnostic quality reports in check_model, check_energy and the legacy GUI quality projection. These explicitly set required=false: execution of a diagnostic is distinct from its engineering verdict. They still participate in check_status and block default workflow gates. The existing explicit report_only mode remains available for diagnostic findings; it cannot bypass any required execution/output/native-agreement failure. The regression control verifies this distinction.

| Evidence | Baseline 0563045 | Fixed | 当前有效 / 已被取代 |
|---|---|---|---|
| Required failed/invalid/missing | 3 false successful jobs | 3 correct verdicts | Recorded product blobs |
| Public edit_keywords disconnected output | succeeded + verified artifact | failed + unverified artifact | Recorded product blobs |
| Diagnostic gate control | passed | passed | Recorded product blobs |
| Related contracts/workflow/result/model/energy/script suites | Historical expectations changed explicitly | 319 passed / 6 skipped | Recorded product blobs |

Clean execution revision: `a87f671cf99cdc4c6b87eaaa7a0d6292cb6797fe`. [evidence.json](evidence.json) binds four key product blobs and the policy test blob. Four new baseline regressions fail with actual status assertions (`succeeded` instead of `failed`/`unverified`); one diagnostic control passed. Two additional controls test input immutability/error retention and strict diagnostic flags. No native process was run for this fix.

```text
python -m pytest tests/test_required_checks_review02.py tests/test_core_contracts.py tests/test_workflow_gates.py tests/test_gui_solid_quality.py tests/test_batch_result_boundary.py tests/test_model_target_tools.py tests/test_result_overview.py tests/test_result_overview_validity.py tests/test_energy_tools.py tests/test_legacy_outcomes.py tests/test_script_command.py tests/test_field_metrics.py tests/test_tensor_field.py tests/test_curve_ops_tool.py tests/test_history_tools.py -q
```

Use PYTHONPATH=src plus repository root, the shared locked environment, PYTHONDONTWRITEBYTECODE=1 and OPENBLAS_NUM_THREADS=1. No task status is upgraded by this fix.

## CI follow-up

The initial exact PR head failed full CI on a benign repeated-Include warning and the view fixture missing the new required flag. This was not treated as infrastructure failure. Reload certification now uses the structured shared preflight ok verdict inside confinement, rather than treating every reload warning as an error. Missing files remain failed; repeated Includes remain warnings. The diagnostic warning text is retained. The strict view fixture includes required=true.

Final clean follow-up execution: `15540a968294806017d284de1310870396a17c4f`, 372 passed / 6 skipped across the related suites, including confinement and view tests. The earlier 319-case capture is retained as previous_capture with its original product identities. The final product identities are recorded separately; this is offline evidence, not a native pass.
