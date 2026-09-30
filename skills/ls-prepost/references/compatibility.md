# Build and failure handling

Target builds: 4.8, 4.10, 4.13. Do not assume a shared embedded Python ABI, command alias set, integration-point enum, or output format behavior. The MCP process and embedded interpreter are separate environments.

Probe the selected executable. Missing Python configuration is not a successful probe. `setpythonhome` is an installation configuration operation that persists; do not silently execute it while reading a model. SCL is available as a separate probe path.

The runner owns one new process, a unique cwd, bounded timeout and task-local logs. Do not kill another user's LS-PrePost session. Access violations, absent responses, malformed images/CSV or wrong job IDs mean failure.

Windows error 740 can come from a per-application RUNASADMIN compatibility setting. Diagnose the actual setting before recommending elevation. Persistent user configuration changes require scope from the user's request and a recovery record; they are not an ordinary MCP modeling operation.

Two local sample d3plot families triggered native-reader crashes during initial development. Do not certify native result tasks from CI mocks or from a successful LASSO read. New builds and other data require their own native tests.

