"""
Tests for scitrera_app_framework.api.plugins module.
"""
import pytest
from logging import Logger
from scitrera_app_framework.api.plugins import Plugin, enabled_option_pattern
from scitrera_app_framework.api.variables import Variables, NOT_SET


class ConcretePlugin(Plugin):
    """Concrete implementation of Plugin for testing."""

    def initialize(self, v: Variables, logger: Logger):
        return "initialized_value"


class CustomExtensionPlugin(Plugin):
    """Plugin with custom extension point name."""

    def extension_point_name(self, v: Variables) -> str:
        return "custom-extension-point"

    def initialize(self, v: Variables, logger: Logger):
        return "custom_value"


class MultiExtensionPlugin(Plugin):
    """Plugin configured for multi-extension mode."""

    def is_multi_extension(self, v: Variables) -> bool:
        return True

    def initialize(self, v: Variables, logger: Logger):
        return "multi_value"


class DisabledPlugin(Plugin):
    """Plugin that is disabled."""

    def is_enabled(self, v: Variables) -> bool:
        return False

    def initialize(self, v: Variables, logger: Logger):
        return "should_not_see_this"


class PluginWithDependencies(Plugin):
    """Plugin that declares dependencies."""

    def get_dependencies(self, v: Variables):
        return ["dep1", "dep2"]

    def initialize(self, v: Variables, logger: Logger):
        return "has_deps"


class LazyPlugin(Plugin):
    """Non-eager plugin."""
    eager = False

    def initialize(self, v: Variables, logger: Logger):
        return "lazy_value"


class TestPluginBase:
    """Tests for Plugin base class."""

    def test_plugin_name(self):
        plugin = ConcretePlugin()
        name = plugin.name()
        assert "ConcretePlugin" in name
        assert "test_api_plugins" in name

    def test_extension_point_name_default(self):
        plugin = ConcretePlugin()
        v = Variables()
        # By default, extension_point_name equals name
        assert plugin.extension_point_name(v) == plugin.name()

    def test_extension_point_name_custom(self):
        plugin = CustomExtensionPlugin()
        v = Variables()
        assert plugin.extension_point_name(v) == "custom-extension-point"

    def test_is_enabled_default(self):
        plugin = ConcretePlugin()
        v = Variables()
        assert plugin.is_enabled(v) is True

    def test_is_enabled_disabled(self):
        plugin = DisabledPlugin()
        v = Variables()
        assert plugin.is_enabled(v) is False

    def test_is_multi_extension_default(self):
        plugin = ConcretePlugin()
        v = Variables()
        assert plugin.is_multi_extension(v) is False

    def test_is_multi_extension_enabled(self):
        plugin = MultiExtensionPlugin()
        v = Variables()
        assert plugin.is_multi_extension(v) is True

    def test_get_dependencies_default(self):
        plugin = ConcretePlugin()
        v = Variables()
        deps = plugin.get_dependencies(v)
        assert list(deps) == []

    def test_get_dependencies_custom(self):
        plugin = PluginWithDependencies()
        v = Variables()
        deps = list(plugin.get_dependencies(v))
        assert "dep1" in deps
        assert "dep2" in deps

    def test_eager_default(self):
        plugin = ConcretePlugin()
        assert plugin.eager is True

    def test_eager_false(self):
        plugin = LazyPlugin()
        assert plugin.eager is False

    def test_collected_default(self):
        plugin = ConcretePlugin()
        assert plugin.collected is False

    def test_initialized_default(self):
        plugin = ConcretePlugin()
        assert plugin.initialized is False

    def test_shutdown_default(self):
        plugin = ConcretePlugin()
        v = Variables()
        import logging
        logger = logging.getLogger("test")
        # Should not raise
        plugin.shutdown(v, logger, "some_value")


class TestPluginStaticMethods:
    """Tests for Plugin static/convenience methods."""

    def test_get_extension_static(self):
        # This test requires framework to be initialized
        from scitrera_app_framework import init_framework_test_harness

        v = init_framework_test_harness("test-app")

        # Register a plugin first
        from scitrera_app_framework.core.plugins import register_plugin
        register_plugin(ConcretePlugin, v, init=True)

        plugin = ConcretePlugin()
        # get_extension should work
        result = Plugin.get_extension(plugin.name(), v)
        assert result == "initialized_value"


class TestEnabledOptionPattern:
    """Tests for enabled_option_pattern function."""

    def test_enabled_when_matches_name(self):
        class NamedPlugin(Plugin):
            def initialize(self, v, logger):
                return None

        plugin = NamedPlugin()
        v = Variables()
        v.set("PLUGIN_SELECTOR", plugin.name())

        result = enabled_option_pattern(plugin, v, "PLUGIN_SELECTOR")
        assert result is True

    def test_disabled_when_no_match(self):
        class NamedPlugin(Plugin):
            def initialize(self, v, logger):
                return None

        plugin = NamedPlugin()
        v = Variables()
        v.set("PLUGIN_SELECTOR", "other_plugin")

        result = enabled_option_pattern(plugin, v, "PLUGIN_SELECTOR")
        assert result is False

    def test_enabled_with_custom_attr(self):
        class AttrPlugin(Plugin):
            identifier = "my-custom-id"

            def initialize(self, v, logger):
                return None

        plugin = AttrPlugin()
        v = Variables()
        v.set("PLUGIN_SELECTOR", "my-custom-id")

        result = enabled_option_pattern(plugin, v, "PLUGIN_SELECTOR", self_attr="identifier")
        assert result is True

    def test_with_default_value(self):
        class DefaultPlugin(Plugin):
            def initialize(self, v, logger):
                return None

        plugin = DefaultPlugin()
        v = Variables()
        # Don't set the env var, use default

        # If default equals the plugin name, should be enabled
        result = enabled_option_pattern(plugin, v, "UNSET_VAR", default=plugin.name())
        assert result is True

        # If default is different, should be disabled
        result = enabled_option_pattern(plugin, v, "UNSET_VAR", default="other")
        assert result is False
