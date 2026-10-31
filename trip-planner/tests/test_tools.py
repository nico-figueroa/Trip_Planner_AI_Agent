import pytest

from utils import tools


def test_execute_tool_dispatches_registered_function(monkeypatch):
    monkeypatch.setitem(
        tools.TOOL_REGISTRY,
        "geocode_city",
        lambda city: {"city": city},
    )

    assert tools.execute_tool("geocode_city", {"city": "Seattle"}) == {
        "city": "Seattle"
    }


def test_execute_tool_rejects_unknown_tool():
    with pytest.raises(ValueError, match="Unknown tool"):
        tools.execute_tool("not_registered", {})


def test_execute_tool_rejects_non_object_arguments():
    with pytest.raises(ValueError, match="JSON object"):
        tools.execute_tool("geocode_city", [])
