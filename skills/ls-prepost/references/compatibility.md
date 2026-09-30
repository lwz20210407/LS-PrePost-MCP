# Build and failure handling

Target builds: 4.8, 4.10, 4.13. Do not assume a shared embedded Python ABI, command alias set, integration-point enum, or output format behavior. The MCP process and embedded interpreter are separate environments.

Probe the selected executable. Missing Python configuration is not a successful probe. `setpythonhome` is an installation configuration operation that persists; do not silently execute it while reading a model. SCL is available as a separate probe path.

The runner owns one new process, a unique cwd, bounded timeout and task-local logs. Do not kill another user's LS-PrePost session. Access violations, absent responses, malformed images/CSV or wrong job IDs mean failure.

Windows error 740 can come from a per-application RUNASADMIN compatibility setting. Diagnose the actual setting before recommending elevation. Persistent user configuration changes require scope from the user's request and a recovery record; they are not an ordinary MCP modeling operation.

Initial d3plot loading failures were addressed by directory/basename handling and a staged SCL path. The 4.10 embedded vector interface still failed numeric cross-checks, so that older ABI is blocked for vectors; independent readers and tested 4.13 native vectors remain separate choices. Do not certify native tasks from CI mocks or a successful external-reader result.
