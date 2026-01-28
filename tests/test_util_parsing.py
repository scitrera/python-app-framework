"""
Tests for scitrera_app_framework.util.parsing module.
"""
import pytest
from scitrera_app_framework.util.parsing import ext_parse_bool, ext_parse_csv, ext_parse_csv_set


class TestExtParseBool:
    """Tests for ext_parse_bool function."""

    @pytest.mark.parametrize("value,expected", [
        # Boolean passthrough
        (True, True),
        (False, False),
        # True values
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("t", True),
        ("T", True),
        ("yes", True),
        ("Yes", True),
        ("YES", True),
        ("y", True),
        ("Y", True),
        ("1", True),
        # False values
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("f", False),
        ("F", False),
        ("no", False),
        ("No", False),
        ("NO", False),
        ("n", False),
        ("N", False),
        ("0", False),
        # Empty/None values
        ("", False),
        (None, False),
        (0, False),
    ])
    def test_parse_bool_values(self, value, expected):
        assert ext_parse_bool(value) == expected

    def test_parse_bool_mixed_case(self):
        assert ext_parse_bool("TrUe") is True
        assert ext_parse_bool("YeS") is True
        assert ext_parse_bool("FaLsE") is False

    def test_parse_bool_with_extra_chars(self):
        # Contains 't', 'y', or '1'
        assert ext_parse_bool("truthy") is True
        assert ext_parse_bool("yep") is True
        assert ext_parse_bool("enabled1") is True
        # Does not contain 't', 'y', or '1'
        assert ext_parse_bool("nope") is False


class TestExtParseCsv:
    """Tests for ext_parse_csv function."""

    def test_simple_csv(self):
        result = ext_parse_csv("a,b,c")
        assert result == ["a", "b", "c"]

    def test_csv_with_whitespace(self):
        result = ext_parse_csv("a, b , c ")
        assert result == ["a", "b", "c"]

    def test_empty_string(self):
        result = ext_parse_csv("")
        assert result == []

    def test_none_value(self):
        result = ext_parse_csv(None)
        assert result == []

    def test_single_value(self):
        result = ext_parse_csv("single")
        assert result == ["single"]

    def test_list_passthrough(self):
        input_list = ["a", "b", "c"]
        result = ext_parse_csv(input_list)
        assert result == ["a", "b", "c"]

    def test_list_with_whitespace(self):
        input_list = [" a ", " b ", " c "]
        result = ext_parse_csv(input_list)
        assert result == ["a", "b", "c"]

    def test_empty_parts_filtered(self):
        result = ext_parse_csv("a,,b,c")
        # Completely empty parts are not filtered, just whitespace-stripped
        # The actual behavior depends on implementation
        assert "a" in result
        assert "b" in result
        assert "c" in result

    def test_list_with_empty_parts(self):
        result = ext_parse_csv(["a", "", "b", None, "c"])
        # None is falsy but might cause issues - let's see what the function does
        assert "a" in result
        assert "b" in result
        assert "c" in result


class TestExtParseCsvSet:
    """Tests for ext_parse_csv_set function."""

    def test_returns_set(self):
        result = ext_parse_csv_set("a,b,c")
        assert isinstance(result, set)
        assert result == {"a", "b", "c"}

    def test_removes_duplicates(self):
        result = ext_parse_csv_set("a,b,a,c,b")
        assert result == {"a", "b", "c"}

    def test_empty_string(self):
        result = ext_parse_csv_set("")
        assert result == set()

    def test_none_value(self):
        result = ext_parse_csv_set(None)
        assert result == set()
