"""Unit tests for type aliases module.

Tests type definitions and constraints for JSON serialization.
"""

from __future__ import annotations

from session_buddy.types import JsonDict, JsonValue


class TestJsonValueType:
    """Test JsonValue type definition."""

    def test_jsonvalue_accepts_none(self) -> None:
        """Test that None is a valid JsonValue."""
        value: JsonValue = None
        assert value is None

    def test_jsonvalue_accepts_bool(self) -> None:
        """Test that bool is a valid JsonValue."""
        value: JsonValue = True
        assert value is True
        value = False
        assert value is False

    def test_jsonvalue_accepts_int(self) -> None:
        """Test that int is a valid JsonValue."""
        value: JsonValue = 42
        assert value == 42
        value = -100
        assert value == -100

    def test_jsonvalue_accepts_float(self) -> None:
        """Test that float is a valid JsonValue."""
        value: JsonValue = 3.14
        assert value == 3.14
        value = -2.5
        assert value == -2.5

    def test_jsonvalue_accepts_str(self) -> None:
        """Test that str is a valid JsonValue."""
        value: JsonValue = "hello"
        assert value == "hello"
        value = ""
        assert value == ""

    def test_jsonvalue_accepts_list(self) -> None:
        """Test that list is a valid JsonValue."""
        value: JsonValue = [1, "two", 3.0, None, True]
        assert isinstance(value, list)
        assert len(value) == 5

    def test_jsonvalue_accepts_dict(self) -> None:
        """Test that dict is a valid JsonValue."""
        value: JsonValue = {"key": "value", "nested": {"inner": 42}}
        assert isinstance(value, dict)
        assert value["key"] == "value"

    def test_jsonvalue_accepts_empty_collections(self) -> None:
        """Test that empty collections are valid JsonValue."""
        empty_list: JsonValue = []
        empty_dict: JsonValue = {}
        assert empty_list == []
        assert empty_dict == {}

    def test_jsonvalue_accepts_nested_structure(self) -> None:
        """Test that deeply nested structures are valid JsonValue."""
        nested: JsonValue = {
            "level1": {
                "level2": {
                    "level3": [1, 2, {"level4": "deep"}],
                }
            }
        }
        assert isinstance(nested, dict)

    def test_jsonvalue_mixed_list(self) -> None:
        """Test list with mixed types."""
        mixed_list: JsonValue = [1, "string", 3.14, None, True, {"key": "val"}]
        assert isinstance(mixed_list, list)
        assert len(mixed_list) == 6

    def test_jsonvalue_numeric_values(self) -> None:
        """Test various numeric values."""
        values: list[JsonValue] = [0, 1, -1, 100, 3.14, -2.5, 1e10, 1.0]
        for val in values:
            assert isinstance(val, (int, float))


class TestJsonDictType:
    """Test JsonDict type definition."""

    def test_jsondict_empty_dict(self) -> None:
        """Test that empty dict is a valid JsonDict."""
        d: JsonDict = {}
        assert d == {}

    def test_jsondict_string_keys(self) -> None:
        """Test that JsonDict requires string keys."""
        d: JsonDict = {"key1": "value1", "key2": 42}
        assert d["key1"] == "value1"
        assert d["key2"] == 42

    def test_jsondict_various_value_types(self) -> None:
        """Test JsonDict with various value types."""
        d: JsonDict = {
            "null": None,
            "bool": True,
            "int": 42,
            "float": 3.14,
            "str": "hello",
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        }
        assert len(d) == 7
        assert d["null"] is None
        assert d["bool"] is True

    def test_jsondict_string_keys_only(self) -> None:
        """Test that JsonDict uses only string keys (type constraint)."""
        d: JsonDict = {}
        d["key"] = "value"
        assert "key" in d

    def test_jsondict_nested_values(self) -> None:
        """Test JsonDict with nested dict values."""
        d: JsonDict = {
            "outer": {
                "middle": {"inner": "value"},
            }
        }
        assert isinstance(d["outer"], dict)

    def test_jsondict_list_values(self) -> None:
        """Test JsonDict with list values."""
        d: JsonDict = {
            "numbers": [1, 2, 3],
            "strings": ["a", "b", "c"],
            "mixed": [1, "two", 3.0, None],
        }
        assert len(d["numbers"]) == 3
        assert len(d["strings"]) == 3

    def test_jsondict_deep_nesting(self) -> None:
        """Test JsonDict with deeply nested structures."""
        d: JsonDict = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": [1, 2, {"level5": "deep"}],
                    },
                },
            },
        }
        assert isinstance(d["level1"], dict)

    def test_jsondict_numeric_values(self) -> None:
        """Test JsonDict with numeric values."""
        d: JsonDict = {
            "zero": 0,
            "positive": 42,
            "negative": -100,
            "float_positive": 3.14,
            "float_negative": -2.5,
        }
        assert d["zero"] == 0
        assert d["positive"] == 42

    def test_jsondict_empty_nested_collections(self) -> None:
        """Test JsonDict with empty nested collections."""
        d: JsonDict = {
            "empty_list": [],
            "empty_dict": {},
            "mixed": [[], {}],
        }
        assert d["empty_list"] == []
        assert d["empty_dict"] == {}

    def test_jsondict_special_string_values(self) -> None:
        """Test JsonDict with special string values."""
        d: JsonDict = {
            "empty_string": "",
            "spaces": "   ",
            "unicode": "🚀",
            "quotes": 'He said "hello"',
            "newlines": "line1\nline2",
        }
        assert d["empty_string"] == ""
        assert d["unicode"] == "🚀"


class TestTypeAliasesUsage:
    """Test usage patterns of type aliases."""

    def test_can_use_jsonvalue_as_return_type(self) -> None:
        """Test using JsonValue as a return type annotation."""

        def get_value() -> JsonValue:
            return {"key": "value"}

        result = get_value()
        assert isinstance(result, dict)

    def test_can_use_jsondict_as_return_type(self) -> None:
        """Test using JsonDict as a return type annotation."""

        def get_dict() -> JsonDict:
            return {"key": 42}

        result = get_dict()
        assert isinstance(result, dict)

    def test_can_use_jsonvalue_as_parameter(self) -> None:
        """Test using JsonValue as a parameter type annotation."""

        def process_value(val: JsonValue) -> bool:
            return val is not None

        assert process_value(42) is True
        assert process_value(None) is False

    def test_can_use_jsondict_as_parameter(self) -> None:
        """Test using JsonDict as a parameter type annotation."""

        def merge_dicts(d1: JsonDict, d2: JsonDict) -> JsonDict:
            result: JsonDict = {**d1, **d2}
            return result

        d1: JsonDict = {"a": 1}
        d2: JsonDict = {"b": 2}
        result = merge_dicts(d1, d2)
        assert result == {"a": 1, "b": 2}

    def test_jsonvalue_list_type(self) -> None:
        """Test list of JsonValue."""
        values: list[JsonValue] = [1, "two", 3.0, None, True, {"nested": "value"}]
        assert len(values) == 6

    def test_jsondict_optional(self) -> None:
        """Test optional JsonDict."""
        optional_dict: JsonDict | None = None
        assert optional_dict is None
        optional_dict = {"key": "value"}
        assert optional_dict["key"] == "value"
