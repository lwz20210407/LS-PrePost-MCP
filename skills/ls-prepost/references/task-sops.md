# General task SOPs

The product is general LS-PrePost automation. Impact, material tests, structural and other analyses are optional cases; do not assume Hopkinson bars, a particular material law, or a fixed engineering acceptance threshold.

## Preprocessing: inspect, select, edit, verify, reopen

1. Identify the model/build, units, include structure and current owned GUI. Inspect entity IDs/counts and supported native scope before editing.
2. Make an explicit selection and checkpoint. Use supported mesh transforms, duplicate-node merge, normal reversal or renumbering; operation-specific size limits still apply. Never infer automatic normal alignment from the existence of reversal.
3. Check requested geometry and untouched entities, then run requested native quality/reference checks with explicit thresholds. Failed checks stop dependent edits/saves according to workflow gates.
4. Save a new output and reopen it natively. Complex Include preservation and contact repair are separate incomplete capabilities; no silent flattening or guessed contact correction.

## Postprocessing: source, scope, quantity, extraction, output

1. Resolve keyword/result family, native build/backend, user IDs, physical times/states, units, layer/integration point, coordinate frame and desired display averaging.
2. Distinguish visible entities from physical alive/deleted entities. Where validity is unavailable, disclose the limitation rather than claim erosion-filtered extrema.
3. Extract native fields/histories and validate completeness and numeric contracts. Apply unit conversion, relative displacement, force–displacement/stress–strain and energy checks only with defined geometry, signs and terms.
4. Cloud plots preserve the model title and native result name: no automatic unit/layer/entity/average suffixes. Default display averaging is `minmax`; `nodal`/`none` require explicit requests. Raw entity CSV is not a table of averaged display samples. Keep interpretation metadata in JSON.
5. Export validated curves/PNG/movie with explicit ranges and timelines. Do not automatically filter curves or declare a model invalid using generic 5%/2% energy ratios. Report checks and missing terms separately from execution success.

## Automation: record, parameterize, preflight, independent cases

1. Record verified managed actions and bind their result/artifact dependencies. Do not treat arbitrary GUI mouse actions as semantically captured.
2. Parameterize model/selection/state/geometry/thresholds explicitly. Preview the whole workflow before starting cases.
3. Run independent case directories from explicit baselines; respect bounded case counts and never replay an uncertain mutation. Locked/dead GUI contexts do not silently become batch jobs.
4. Validate each case and summarize comparable scalar/CSV outputs, failed checks and versions. Keep user models, extracted values, images and native evidence private.

Use existing references for exact API contracts. In compact MCP mode, discover and describe an operation before calling it; preserve explicit execution context and the same SOP.
