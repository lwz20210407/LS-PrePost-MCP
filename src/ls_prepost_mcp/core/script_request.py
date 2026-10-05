"""Strict script requests; no I02 contract fields are changed."""

from typing import Literal

from pydantic import Field, StrictInt, model_validator

from .contracts import Contract, Ids, Text


class ScriptOutput(Contract):
    name: Text
    kind: Literal["keyword", "csv", "json", "text", "png", "npz"]


class ScriptDependency(Contract):
    path: Text
    name: Text


class ScriptRequest(Contract):
    language: Literal["command", "cfile", "scl", "python"]
    code: Text
    context: Literal["batch", "session"] = "batch"
    session_id: str | None = None
    model: str | None = None
    file_type: Literal["keyword", "d3plot"] = "keyword"
    outputs: list[ScriptOutput] = Field(default_factory=list)
    expected_counts: dict[str, StrictInt] = Field(default_factory=dict)
    capture_model: bool = False
    initial_node_ids: Ids | None = None
    parameters: dict = Field(default_factory=dict)
    dependencies: list[ScriptDependency] = Field(default_factory=list)

    @model_validator(mode="after")
    def execution_context(self):
        if self.context == "batch" and self.session_id is not None:
            raise ValueError("Batch context cannot consume a session_id")
        if self.context == "session" and (not self.session_id or self.model is not None):
            raise ValueError("Session context requires session_id and uses its current model")
        if self.initial_node_ids is not None and (len(self.initial_node_ids) > 10000 or len(set(self.initial_node_ids)) != len(self.initial_node_ids)):
            raise ValueError("Initial node selection requires at most 10000 unique user IDs")
        if len(self.code.encode("utf8")) > 1024 * 1024 or "\x00" in self.code:
            raise ValueError("Script requires nonempty source up to 1 MiB")
        if self.language == "python":
            if self.initial_node_ids is not None or self.capture_model:
                raise ValueError("Python declares its own selection and output commands")
            return self
        if self.dependencies:
            raise ValueError("Unified dependency bundles currently require Python")
        if self.language == "cfile":
            if self.initial_node_ids is not None or self.capture_model:
                raise ValueError("Cfile declares its own selection and output commands")
            return self
        if self.language == "scl":
            if self.parameters or self.initial_node_ids is not None or self.capture_model:
                raise ValueError("SCL declares its own data and outputs")
            return self
        if self.parameters:
            raise ValueError("Parameter interpolation is available for cfile")
        if any(c in self.code for c in "\r\n;"):
            raise ValueError("Command requires one nonempty native line")
        head = self.code.strip().split()[0].lower()
        if head in {"exit", "quit", "new", "system", "runpython", "runscript"}:
            raise ValueError("Use the dedicated lifecycle or script-language interface")
        if self.code.strip().lower().startswith("openc command"):
            raise ValueError("Use the cfile language for command streams")
        return self
