from __future__ import annotations


def test_session_buddy_json_type_aliases() -> None:
    from session_buddy.types import JsonDict, JsonValue

    data: JsonDict = {"message": "ok", "count": 2, "nested": {"flag": True}}

    assert isinstance(data, dict)
    assert data["message"] == "ok"
    assert data["count"] == 2
    assert data["nested"] == {"flag": True}
    assert JsonValue is not None
