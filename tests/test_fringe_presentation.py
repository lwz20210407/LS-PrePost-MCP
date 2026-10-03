import inspect

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.fringe_presentation import result_name
from ls_prepost_mcp.gui_fringe import RENDER_ELEMENT_FIELDS
from ls_prepost_mcp.native_results import NODE_FIELDS
from ls_prepost_mcp.service import Service


def test_field_captions_are_plain_and_all_supported_quantities_have_names():
    assert result_name("von_mises") == "Von Mises stress"
    assert result_name("disp_magnitude") == "result displacement"
    for field in RENDER_ELEMENT_FIELDS | NODE_FIELDS:
        assert result_name(field)
        assert not any(suffix in result_name(field) for suffix in ("avg:", "ip:", "[", "]"))


@pytest.mark.parametrize("method", ["render_gui_field", "export_gui_animation", "render_snapshot"])
def test_media_defaults_are_minmax_and_invalid_average_never_contacts_native(tmp_path, method):
    assert inspect.signature(getattr(Service, method)).parameters["averaging"].default == "minmax"
    service = Service(Settings(tmp_path))
    arguments = ({"session_id": "missing", "entity_type": "solid", "field": "von_mises", "state": 1, "units": "MPa"}
                 if method == "render_gui_field" else {"session_id": "missing"} if method == "export_gui_animation"
                 else {"model": "missing"})
    with pytest.raises(ValueError, match="averaging"):
        getattr(service, method)(**arguments, averaging="invented")
    assert not list(tmp_path.iterdir())
