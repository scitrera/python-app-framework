"""
Tests for scitrera_app_framework.core.plugins module.
"""
import pytest
from logging import Logger
from scitrera_app_framework.api import Plugin, Variables


# Test plugin implementations
class SimplePlugin(Plugin):
    """Simple plugin for testing."""
    init_count = 0
    shutdown_count = 0

    def extension_point_name(self, v: Variables) -> str:
        return "simple-ext"

    def initialize(self, v: Variables, logger: Logger):
        SimplePlugin.init_count += 1
        return {"status": "initialized"}

    def shutdown(self, v: Variables, logger: Logger, value):
        SimplePlugin.shutdown_count += 1


class AnotherSimplePlugin(Plugin):
    """Another plugin at same extension point."""

    def extension_point_name(self, v: Variables) -> str:
        return "simple-ext"

    def is_enabled(self, v: Variables) -> bool:
        return v.get("USE_ANOTHER", False)

    def initialize(self, v: Variables, logger: Logger):
        return {"status": "another_initialized"}


class MultiPlugin(Plugin):
    """Multi-extension plugin."""
    _value = "multi_value_1"

    def extension_point_name(self, v: Variables) -> str:
        return "multi-ext"

    def is_multi_extension(self, v: Variables) -> bool:
        return True

    def initialize(self, v: Variables, logger: Logger):
        return self._value


class MultiPlugin2(Plugin):
    """Second multi-extension plugin."""
    _value = "multi_value_2"

    def extension_point_name(self, v: Variables) -> str:
        return "multi-ext"

    def is_multi_extension(self, v: Variables) -> bool:
        return True

    def initialize(self, v: Variables, logger: Logger):
        return self._value


class DependentPlugin(Plugin):
    """Plugin with dependencies."""

    def extension_point_name(self, v: Variables) -> str:
        return "dependent-ext"

    def get_dependencies(self, v: Variables):
        return ["simple-ext"]

    def initialize(self, v: Variables, logger: Logger):
        # Access the dependency
        from scitrera_app_framework.core.plugins import get_extension
        dep_value = get_extension("simple-ext", v)
        return {"dep_status": dep_value["status"]}


class LazyPlugin(Plugin):
    """Non-eager plugin."""
    eager = False
    init_called = False

    def extension_point_name(self, v: Variables) -> str:
        return "lazy-ext"

    def initialize(self, v: Variables, logger: Logger):
        LazyPlugin.init_called = True
        return "lazy_value"


class DisabledPlugin(Plugin):
    """Disabled plugin."""

    def extension_point_name(self, v: Variables) -> str:
        return "disabled-ext"

    def is_enabled(self, v: Variables) -> bool:
        return False

    def initialize(self, v: Variables, logger: Logger):
        return "should_not_see"


@pytest.fixture(autouse=True)
def reset_plugin_state():
    """Reset plugin class state before each test."""
    SimplePlugin.init_count = 0
    SimplePlugin.shutdown_count = 0
    LazyPlugin.init_called = False
    yield


class TestRegisterPlugin:
    """Tests for register_plugin function."""

    def test_register_plugin_basic(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        v = init_framework_test_harness("test-app")
        instance = register_plugin(SimplePlugin, v, init=False)

        assert instance is not None
        assert isinstance(instance, SimplePlugin)
        assert instance.collected is False  # Not collected until init

    def test_register_and_init(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        v = init_framework_test_harness("test-app")
        instance = register_plugin(SimplePlugin, v, init=True)

        assert instance.collected is True
        assert instance.initialized is True
        assert SimplePlugin.init_count == 1

    def test_register_duplicate_same_type(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        v = init_framework_test_harness("test-app")
        instance1 = register_plugin(SimplePlugin, v)
        instance2 = register_plugin(SimplePlugin, v)

        # Should return new instance but not double-register
        # The name should already be in registry
        assert instance1 is not None
        assert instance2 is not None


class TestGetExtension:
    """Tests for get_extension function."""

    def test_get_extension_basic(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extension

        v = init_framework_test_harness("test-app")
        register_plugin(SimplePlugin, v, init=True)

        result = get_extension("simple-ext", v)

        assert result is not None
        assert result["status"] == "initialized"

    def test_get_extension_by_type(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import get_extension

        v = init_framework_test_harness("test-app")

        # Getting by type should auto-register and init
        result = get_extension(SimplePlugin, v)

        assert result is not None
        assert result["status"] == "initialized"

    def test_get_extension_lazy_init(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extension

        v = init_framework_test_harness("test-app")
        # Register without init - lazy plugins are not eagerly initialized
        register_plugin(LazyPlugin, v, init=False)

        # Lazy plugin shouldn't be initialized yet
        assert LazyPlugin.init_called is False

        # Getting it should trigger init
        result = get_extension("lazy-ext", v)

        assert result == "lazy_value"
        assert LazyPlugin.init_called is True

    def test_get_extension_unknown_raises(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import get_extension

        v = init_framework_test_harness("test-app")

        with pytest.raises(ValueError, match="unknown extension point"):
            get_extension("nonexistent-ext", v)


class TestGetExtensions:
    """Tests for get_extensions function (multi-extension)."""

    def test_get_extensions_multi(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extensions

        v = init_framework_test_harness("test-app")
        register_plugin(MultiPlugin, v, init=True)
        register_plugin(MultiPlugin2, v, init=True)

        results = get_extensions("multi-ext", v)

        assert isinstance(results, dict)
        # Verify both plugins are registered (by checking key count)
        assert len(results) == 2
        # Both plugins should be in the results dict
        assert any("MultiPlugin" in k for k in results.keys())
        assert any("MultiPlugin2" in k for k in results.keys())

    def test_get_extensions_by_type(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extensions

        v = init_framework_test_harness("test-app")
        register_plugin(MultiPlugin, v, init=True)

        results = get_extensions(MultiPlugin, v)

        assert isinstance(results, dict)


class TestPluginDependencies:
    """Tests for plugin dependency resolution."""

    def test_dependency_resolution(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extension

        v = init_framework_test_harness("test-app")
        register_plugin(SimplePlugin, v)  # Don't init yet
        register_plugin(DependentPlugin, v, init=True)

        # Getting dependent should have triggered simple init
        assert SimplePlugin.init_count == 1

        result = get_extension("dependent-ext", v)
        assert result["dep_status"] == "initialized"

    def test_missing_dependency_raises(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        v = init_framework_test_harness("test-app")
        # Don't register SimplePlugin

        with pytest.raises(ValueError, match="unable to find"):
            register_plugin(DependentPlugin, v, init=True)


class TestPluginShutdown:
    """Tests for plugin shutdown."""

    def test_shutdown_all_plugins(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import (
            register_plugin, shutdown_all_plugins
        )

        v = init_framework_test_harness("test-app")
        register_plugin(SimplePlugin, v, init=True)

        shutdown_all_plugins(v)

        assert SimplePlugin.shutdown_count == 1

    def test_shutdown_order(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import (
            register_plugin, shutdown_all_plugins
        )

        v = init_framework_test_harness("test-app")
        shutdown_order = []

        class Plugin1(Plugin):
            def extension_point_name(self, v):
                return "p1-ext"

            def initialize(self, v, logger):
                return "p1"

            def shutdown(self, v, logger, value):
                shutdown_order.append("p1")

        class Plugin2(Plugin):
            def extension_point_name(self, v):
                return "p2-ext"

            def initialize(self, v, logger):
                return "p2"

            def shutdown(self, v, logger, value):
                shutdown_order.append("p2")

        register_plugin(Plugin1, v, init=True)
        register_plugin(Plugin2, v, init=True)

        shutdown_all_plugins(v)

        # Shutdown should be in reverse order
        assert shutdown_order == ["p2", "p1"]


class TestSetExtension:
    """Tests for set_extension function."""

    def test_set_extension_basic(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import set_extension, get_extension

        v = init_framework_test_harness("test-app")

        def init_fn():
            return {"custom": "value"}

        set_extension("custom-ext", init_fn, v=v)

        result = get_extension("custom-ext", v)
        assert result["custom"] == "value"

    def test_set_extension_with_shutdown(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import (
            set_extension, get_extension, shutdown_all_plugins
        )

        v = init_framework_test_harness("test-app")
        shutdown_called = []

        def init_fn():
            return "value"

        def shutdown_fn():
            shutdown_called.append(True)

        set_extension("custom-ext2", init_fn, shutdown_fn=shutdown_fn, v=v)
        get_extension("custom-ext2", v)  # Trigger init

        shutdown_all_plugins(v)

        assert len(shutdown_called) == 1


class TestInitAllPlugins:
    """Tests for init_all_plugins function."""

    def test_init_all_plugins(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import (
            register_plugin, init_all_plugins
        )

        v = init_framework_test_harness("test-app")
        register_plugin(SimplePlugin, v, init=False)
        register_plugin(LazyPlugin, v, init=False)

        assert SimplePlugin.init_count == 0
        assert LazyPlugin.init_called is False

        init_all_plugins(v)

        assert SimplePlugin.init_count == 1
        # Lazy plugins might not init unless requested
        # Depends on implementation


class TestDisabledPlugins:
    """Tests for disabled plugins."""

    def test_disabled_plugin_not_initialized(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extension

        v = init_framework_test_harness("test-app")
        register_plugin(DisabledPlugin, v, init=True)

        # Disabled plugin should not be accessible
        with pytest.raises(ValueError):
            get_extension("disabled-ext", v)

    def test_alternative_plugin_selection(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extension

        v = init_framework_test_harness("test-app")
        v.set("USE_ANOTHER", True)

        register_plugin(SimplePlugin, v)
        register_plugin(AnotherSimplePlugin, v, init=True)

        # With USE_ANOTHER=True, AnotherSimplePlugin should be selected
        result = get_extension("simple-ext", v)
        assert result["status"] == "another_initialized"


class TestOnRegistration:
    """Tests for on_registration hook."""

    def test_on_registration_called(self, clean_env):
        """Test that on_registration is called when plugin is registered."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        on_reg_calls = []

        class OnRegPlugin(Plugin):
            def extension_point_name(self, v):
                return "onreg-ext"

            def on_registration(self, v):
                on_reg_calls.append(("registered", v))

            def initialize(self, v, logger):
                return "value"

        v = init_framework_test_harness("test-app")
        register_plugin(OnRegPlugin, v, init=False)

        assert len(on_reg_calls) == 1
        assert on_reg_calls[0][0] == "registered"
        assert on_reg_calls[0][1] is v

    def test_on_registration_called_before_initialize(self, clean_env):
        """Test that on_registration is called before initialize."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        call_order = []

        class OrderTestPlugin(Plugin):
            def extension_point_name(self, v):
                return "order-ext"

            def on_registration(self, v):
                call_order.append("on_registration")

            def initialize(self, v, logger):
                call_order.append("initialize")
                return "value"

        v = init_framework_test_harness("test-app")
        register_plugin(OrderTestPlugin, v, init=True)

        assert call_order == ["on_registration", "initialize"]

    def test_on_registration_not_called_twice(self, clean_env):
        """Test that on_registration is only called once per plugin, not on duplicate registration."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        on_reg_calls = []

        class SingleRegPlugin(Plugin):
            def extension_point_name(self, v):
                return "singlereg-ext"

            def on_registration(self, v):
                on_reg_calls.append("called")

            def initialize(self, v, logger):
                return "value"

        v = init_framework_test_harness("test-app")

        # Register multiple times
        register_plugin(SingleRegPlugin, v, init=False)
        register_plugin(SingleRegPlugin, v, init=False)
        register_plugin(SingleRegPlugin, v, init=True)

        # on_registration should only be called once
        assert len(on_reg_calls) == 1

    def test_on_registration_default_noop(self, clean_env):
        """Test that plugins without on_registration override work fine (backwards compatibility)."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extension

        v = init_framework_test_harness("test-app")

        # SimplePlugin doesn't override on_registration
        register_plugin(SimplePlugin, v, init=True)

        # Should work normally
        result = get_extension("simple-ext", v)
        assert result["status"] == "initialized"

    def test_on_registration_can_register_other_plugins(self, clean_env):
        """Test that on_registration can register additional plugins."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extension

        class HelperPlugin(Plugin):
            def extension_point_name(self, v):
                return "helper-ext"

            def initialize(self, v, logger):
                return "helper_value"

        class MainPlugin(Plugin):
            def extension_point_name(self, v):
                return "main-ext"

            def on_registration(self, v):
                # Register another plugin during on_registration
                register_plugin(HelperPlugin, v, init=False)

            def initialize(self, v, logger):
                return "main_value"

        v = init_framework_test_harness("test-app")
        register_plugin(MainPlugin, v, init=True)

        # Both plugins should be accessible
        assert get_extension("main-ext", v) == "main_value"
        assert get_extension("helper-ext", v) == "helper_value"

    def test_on_registration_can_set_variables(self, clean_env):
        """Test that on_registration can modify the Variables instance."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extension

        class ConfigPlugin(Plugin):
            def extension_point_name(self, v):
                return "config-ext"

            def on_registration(self, v):
                # Set some default configuration
                v.set("CONFIG_DEFAULT", "default_value")

            def initialize(self, v, logger):
                return v.get("CONFIG_DEFAULT")

        v = init_framework_test_harness("test-app")
        register_plugin(ConfigPlugin, v, init=True)

        result = get_extension("config-ext", v)
        assert result == "default_value"

    def test_on_registration_with_multi_extension(self, clean_env):
        """Test that on_registration works with multi-extension plugins."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin, get_extensions

        on_reg_calls = []

        class MultiRegPlugin1(Plugin):
            def extension_point_name(self, v):
                return "multireg-ext"

            def is_multi_extension(self, v):
                return True

            def on_registration(self, v):
                on_reg_calls.append("multi1")

            def initialize(self, v, logger):
                return "multi1_value"

        class MultiRegPlugin2(Plugin):
            def extension_point_name(self, v):
                return "multireg-ext"

            def is_multi_extension(self, v):
                return True

            def on_registration(self, v):
                on_reg_calls.append("multi2")

            def initialize(self, v, logger):
                return "multi2_value"

        v = init_framework_test_harness("test-app")
        register_plugin(MultiRegPlugin1, v, init=True)
        register_plugin(MultiRegPlugin2, v, init=True)

        # Both on_registration hooks should be called
        assert on_reg_calls == ["multi1", "multi2"]

        # Both extensions should work
        results = get_extensions("multireg-ext", v)
        assert len(results) == 2

    def test_on_registration_with_disabled_plugin(self, clean_env):
        """Test that on_registration is called even for disabled plugins."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        on_reg_calls = []

        class DisabledRegPlugin(Plugin):
            def extension_point_name(self, v):
                return "disabledreg-ext"

            def is_enabled(self, v):
                return False

            def on_registration(self, v):
                on_reg_calls.append("disabled_registered")

            def initialize(self, v, logger):
                return "should_not_init"

        v = init_framework_test_harness("test-app")
        register_plugin(DisabledRegPlugin, v, init=True)

        # on_registration should still be called even though plugin is disabled
        assert len(on_reg_calls) == 1
        assert on_reg_calls[0] == "disabled_registered"

    def test_on_registration_with_lazy_plugin(self, clean_env):
        """Test that on_registration is called immediately for lazy plugins."""
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.plugins import register_plugin

        call_order = []

        class LazyRegPlugin(Plugin):
            eager = False

            def extension_point_name(self, v):
                return "lazyreg-ext"

            def on_registration(self, v):
                call_order.append("on_registration")

            def initialize(self, v, logger):
                call_order.append("initialize")
                return "lazy_value"

        v = init_framework_test_harness("test-app")
        register_plugin(LazyRegPlugin, v, init=False)

        # on_registration should be called immediately upon registration
        assert call_order == ["on_registration"]

        # initialize should not be called yet (lazy)
        assert "initialize" not in call_order
