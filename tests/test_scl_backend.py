from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.service import Service


def test_scl_uses_owned_copies_and_requires_counts(tmp_path, monkeypatch):
    original = tmp_path / "source"
    original.mkdir()
    (original / "d3plot").write_bytes(b"geometry")
    (original / "d3plot01").write_bytes(b"state")
    (original / "d3plot_notes.txt").write_text("unrelated")
    exe = tmp_path / "fake-executable"
    exe.touch()
    def fake(executable, cfile, directory, **kwargs):
        assert (directory / "d3plot").read_bytes() == b"geometry"
        assert (directory / "d3plot01").read_bytes() == b"state"
        assert not (directory / "d3plot_notes.txt").exists()
        return {"returncode": 0, "timed_out": False}
    monkeypatch.setattr("ls_prepost_mcp.scl_backend.execute", fake)
    result = Service(Settings(tmp_path, exe)).inspect_d3plot_scl(str(original / "d3plot"))
    assert result["status"] == "failed"
    assert (original / "d3plot").read_bytes() == b"geometry"
