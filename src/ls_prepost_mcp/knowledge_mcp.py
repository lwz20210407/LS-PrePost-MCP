"""Protocol-boundary serialization of reference diagnostics, including zero hits."""
import json
from functools import wraps

from mcp.types import CallToolResult, TextContent

from .knowledge_results import ReferenceResults


def reference_tool(function):
    """Retain signatures and ordinary outputs; adapt list-backed reference results."""

    @wraps(function)
    def invoke(*args, **kwargs):
        result = function(*args, **kwargs)
        if not isinstance(result, ReferenceResults):
            return result
        # Preserve normal hit blocks. With zero hits, the only text block is
        # explicitly diagnostics; the structured result array remains empty.
        content = [TextContent(type="text", text=json.dumps(row, ensure_ascii=False, indent=2)) for row in result]
        if not result:
            content.append(TextContent(type="text", text=json.dumps(
                {"diagnostics": result.diagnostics}, ensure_ascii=False, indent=2)))
        return CallToolResult(content=content, structuredContent={
            "result": list(result), "diagnostics": result.diagnostics})

    return invoke
