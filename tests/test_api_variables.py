"""
Tests for scitrera_app_framework.api.variables module.
"""
import os
import pytest
from scitrera_app_framework.api.variables import (
    Variables, EnvPlacement, NOT_SET, NO_MATCH, is_epp, EnvironProxy
)


class TestIsEpp:
    """Tests for is_epp function."""

    def test_valid_epp_keys(self):
        assert is_epp("=|test|") is True
        assert is_epp("=|some_variable|") is True
        assert is_epp("=|x|") is True

    def test_invalid_epp_keys(self):
        assert is_epp("test") is False
        assert is_epp("=|test") is False
        assert is_epp("test|") is False
        assert is_epp("") is False
        assert is_epp("=||") is False  # Too short (4 chars minimum)

    def test_non_string_keys(self):
        assert is_epp(None) is False
        assert is_epp(123) is False
        assert is_epp(["=|test|"]) is False


class TestEnvironProxy:
    """Tests for EnvironProxy class."""

    def test_getitem_uppercase(self):
        os.environ["TEST_VAR_PROXY"] = "test_value"
        try:
            proxy = EnvironProxy()
            assert proxy["test_var_proxy"] == "test_value"
            assert proxy["TEST_VAR_PROXY"] == "test_value"
        finally:
            del os.environ["TEST_VAR_PROXY"]

    def test_contains_uppercase(self):
        os.environ["TEST_VAR_PROXY2"] = "value"
        try:
            proxy = EnvironProxy()
            assert "test_var_proxy2" in proxy
            assert "TEST_VAR_PROXY2" in proxy
            assert "nonexistent" not in proxy
        finally:
            del os.environ["TEST_VAR_PROXY2"]


class TestVariablesBasic:
    """Basic tests for Variables class."""

    def test_create_empty_variables(self):
        v = Variables()
        assert v is not None

    def test_set_and_get(self):
        v = Variables()
        v.set("key1", "value1")
        assert v.get("key1") == "value1"

    def test_getitem_syntax(self):
        v = Variables()
        v["key1"] = "value1"
        assert v["key1"] == "value1"

    def test_getattr_syntax(self):
        v = Variables()
        v.set("mykey", "myvalue")
        assert v.mykey == "myvalue"

    def test_get_nonexistent_returns_none(self):
        v = Variables()
        assert v.get("nonexistent") is None

    def test_get_with_default(self):
        v = Variables()
        assert v.get("nonexistent", default="default_val") == "default_val"

    def test_contains(self):
        v = Variables()
        v.set("exists", "value")
        assert "exists" in v
        # Note: nonexistent keys might still be "in" if they're in environment

    def test_keys(self):
        v = Variables()
        v.set("key1", "value1")
        v.set("key2", "value2")
        keys = v.keys()
        assert "key1" in keys
        assert "key2" in keys
        # Returns a copy
        assert keys is not v._keys


class TestVariablesEnviron:
    """Tests for Variables.environ method."""

    def test_environ_with_env_var(self):
        os.environ["TEST_SAF_VAR"] = "from_env"
        try:
            v = Variables()
            result = v.environ("TEST_SAF_VAR")
            assert result == "from_env"
        finally:
            del os.environ["TEST_SAF_VAR"]

    def test_environ_with_default(self):
        v = Variables()
        # Ensure env var doesn't exist
        if "NONEXISTENT_VAR_XYZ" in os.environ:
            del os.environ["NONEXISTENT_VAR_XYZ"]

        result = v.environ("NONEXISTENT_VAR_XYZ", default="default_value")
        assert result == "default_value"

    def test_environ_with_type_fn(self):
        os.environ["TEST_INT_VAR"] = "42"
        try:
            v = Variables()
            result = v.environ("TEST_INT_VAR", type_fn=int)
            assert result == 42
            assert isinstance(result, int)
        finally:
            del os.environ["TEST_INT_VAR"]

    def test_environ_type_fn_applied_on_subsequent_gets(self):
        os.environ["TEST_BOOL_VAR"] = "true"
        try:
            v = Variables()
            from scitrera_app_framework.util.parsing import ext_parse_bool
            v.environ("TEST_BOOL_VAR", type_fn=ext_parse_bool)
            # Subsequent get should also apply type_fn
            assert v.get("TEST_BOOL_VAR") is True
        finally:
            del os.environ["TEST_BOOL_VAR"]

    def test_environ_registers_default(self):
        v = Variables()
        v.environ("MY_KEY", default="my_default")
        # Default should be registered
        assert v.get("MY_KEY") == "my_default"


class TestVariablesEnvPlacement:
    """Tests for Variables with different EnvPlacement options."""

    def test_env_placement_top(self):
        os.environ["PLACEMENT_TEST"] = "from_env"
        try:
            v = Variables(env_placement=EnvPlacement.TOP)
            v.set("PLACEMENT_TEST", "from_local")
            # Environment should take precedence
            assert v.get("PLACEMENT_TEST") == "from_env"
        finally:
            del os.environ["PLACEMENT_TEST"]

    def test_env_placement_bottom(self):
        os.environ["PLACEMENT_TEST2"] = "from_env"
        try:
            v = Variables(env_placement=EnvPlacement.BOTTOM)
            v.set("PLACEMENT_TEST2", "from_local")
            # Local should take precedence
            assert v.get("PLACEMENT_TEST2") == "from_local"
        finally:
            del os.environ["PLACEMENT_TEST2"]

    def test_env_placement_ignored(self):
        os.environ["PLACEMENT_TEST3"] = "from_env"
        try:
            v = Variables(env_placement=EnvPlacement.IGNORED)
            # Without setting local, should get None (env ignored)
            assert v.get("PLACEMENT_TEST3") is None
        finally:
            del os.environ["PLACEMENT_TEST3"]

    def test_env_placement_bottom2(self):
        os.environ["PLACEMENT_TEST4"] = "from_env"
        try:
            v = Variables(env_placement=EnvPlacement.BOTTOM2)
            # Default fallback should be after env
            v.set("PLACEMENT_TEST4", "from_local")
            assert v.get("PLACEMENT_TEST4") == "from_local"
        finally:
            del os.environ["PLACEMENT_TEST4"]


class TestVariablesSources:
    """Tests for Variables with additional sources."""

    def test_add_source(self):
        v = Variables()
        extra_source = {"extra_key": "extra_value"}
        v.add_source(extra_source)

        assert v.get("extra_key") == "extra_value"

    def test_source_priority(self):
        v = Variables()
        source1 = {"shared_key": "from_source1"}
        source2 = {"shared_key": "from_source2"}

        v.add_source(source1)
        v.add_source(source2)

        # First added source should have priority
        assert v.get("shared_key") == "from_source1"

    def test_local_overrides_sources(self):
        v = Variables()
        v.add_source({"key": "from_source"})
        v.set("key", "from_local")

        assert v.get("key") == "from_local"

    def test_sources_in_constructor(self):
        source1 = {"key1": "value1"}
        source2 = {"key2": "value2"}
        v = Variables(sources=[source1, source2])

        assert v.get("key1") == "value1"
        assert v.get("key2") == "value2"


class TestVariablesSetMethods:
    """Tests for Variables set methods."""

    def test_set_returns_value(self):
        v = Variables()
        result = v.set("key", "value")
        assert result == "value"

    def test_set_type_fn(self):
        v = Variables()
        v.set_type_fn("int_key", int)
        v.set("int_key", "123")
        assert v.get("int_key") == 123

    def test_set_default_value(self):
        v = Variables()
        v.set_default_value("default_key", "default_value")
        assert v.get("default_key") == "default_value"

    def test_set_type_default(self):
        v = Variables()
        v.set_type_default("typed_key", default="42", type_fn=int)
        assert v.get("typed_key") == 42

    def test_update_with_dict(self):
        v = Variables()
        v.update({"key1": "value1", "key2": "value2"})
        assert v.get("key1") == "value1"
        assert v.get("key2") == "value2"

    def test_update_with_kwargs(self):
        v = Variables()
        v.update(key1="value1", key2="value2")
        assert v.get("key1") == "value1"
        assert v.get("key2") == "value2"


class TestVariablesGetOrSet:
    """Tests for get_or_set methods."""

    def test_get_or_set_creates_value(self):
        v = Variables()
        result = v.get_or_set("new_key", lambda: "created_value")
        assert result == "created_value"
        assert v.get("new_key") == "created_value"

    def test_get_or_set_returns_existing(self):
        v = Variables()
        v.set("existing_key", "existing_value")
        call_count = 0

        def value_fn():
            nonlocal call_count
            call_count += 1
            return "new_value"

        result = v.get_or_set("existing_key", value_fn)
        assert result == "existing_value"
        assert call_count == 0  # value_fn should not be called

    def test_get_or_set_default(self):
        v = Variables()
        result = v.get_or_set_default("default_key", lambda: "default_val")
        assert result == "default_val"


class TestVariablesPrefixMethods:
    """Tests for prefix-based methods."""

    def test_get_by_prefix(self):
        v = Variables()
        v.set("APP_NAME", "test_app")
        v.set("APP_VERSION", "1.0")
        v.set("OTHER_KEY", "other")

        # We need to make sure the keys are tracked
        v.environ("APP_NAME", default="test_app")
        v.environ("APP_VERSION", default="1.0")

        result = v.get_by_prefix("APP")
        assert "name" in result
        assert "version" in result
        assert result["name"] == "test_app"
        assert result["version"] == "1.0"

    def test_get_by_prefix_no_drop(self):
        v = Variables()
        v.environ("PREFIX_KEY", default="value")

        result = v.get_by_prefix("PREFIX", drop_prefix=False, key_lower=False)
        assert "PREFIX_KEY" in result

    def test_import_from_env_by_prefix(self):
        os.environ["TESTPREFIX_ONE"] = "value1"
        os.environ["TESTPREFIX_TWO"] = "value2"
        try:
            v = Variables()
            result = v.import_from_env_by_prefix("TESTPREFIX")
            assert "one" in result
            assert "two" in result
            assert result["one"] == "value1"
            assert result["two"] == "value2"
        finally:
            del os.environ["TESTPREFIX_ONE"]
            del os.environ["TESTPREFIX_TWO"]

    def test_import_from_dict_by_prefix(self):
        v = Variables()
        source = {
            "MYPREFIX_A": "val_a",
            "MYPREFIX_B": "val_b",
            "OTHER_X": "val_x"
        }
        result = v.import_from_dict_by_prefix("MYPREFIX", source)
        assert "a" in result
        assert "b" in result
        assert "x" not in result


class TestVariablesExport:
    """Tests for export_all_variables."""

    def test_export_all_variables(self):
        v = Variables()
        v.set("key1", "value1")
        v.set("key2", "value2")
        v.environ("key1")  # Register key
        v.environ("key2")  # Register key

        exported = v.export_all_variables()
        assert "key1" in exported
        assert "key2" in exported
        assert exported["key1"] == "value1"

    def test_export_excludes_epp_by_default(self):
        v = Variables()
        v.set("=|internal|", "secret")
        v.set("normal_key", "value")
        v.environ("normal_key")

        exported = v.export_all_variables()
        assert "=|internal|" not in exported
        assert "normal_key" in exported

    def test_export_includes_epp_when_requested(self):
        v = Variables()
        v.set("=|internal|", "secret")
        # Need to track the key manually since epp keys aren't auto-tracked
        v._keys.add("=|internal|")

        exported = v.export_all_variables(exclude_epp=False)
        assert "=|internal|" in exported


class TestVariablesLocalProvider:
    """Tests for custom local_provider."""

    def test_custom_local_provider(self):
        custom_dict = {}

        def custom_provider():
            return custom_dict

        v = Variables(local_provider=custom_provider)
        v.set("key", "value")

        # Value should be in our custom dict
        assert custom_dict["key"] == "value"
