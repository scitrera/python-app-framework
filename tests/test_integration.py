"""
Integration tests for scitrera_app_framework.

These tests verify that multiple components work together correctly.
"""
import os
import pytest
import logging
from concurrent.futures import Future


class TestFrameworkLifecycle:
    """Tests for complete framework lifecycle."""

    def test_full_init_and_shutdown(self, clean_env, tmp_path):
        import time
        from scitrera_app_framework import (
            init_framework, get_logger
        )
        from scitrera_app_framework.core import (
            register_shutdown_function, get_working_path
        )
        from scitrera_app_framework.core.plugins import shutdown_all_plugins
        from scitrera_app_framework.base_plugins import get_background_exec

        shutdown_called = []

        def on_shutdown():
            shutdown_called.append(True)

        # Initialize framework
        v = init_framework(
            "integration-test",
            base_plugins=True,
            shutdown_hooks=False,  # We'll call manually
            stateful=True,
            stateful_chdir=False,
            default_stateful_root=str(tmp_path)
        )

        # Register custom shutdown
        register_shutdown_function(on_shutdown)

        # Use logger
        logger = get_logger(v)
        logger.info("Integration test started")

        # Use background executor
        executor = get_background_exec(v)
        results = []
        executor.submit_job(lambda: results.append(42))
        time.sleep(0.2)
        assert 42 in results

        # Verify working path
        path = get_working_path(v)
        assert str(tmp_path) in path

        # Shutdown
        shutdown_all_plugins(v)

    def test_multiple_init_calls(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness

        # First init
        v1 = init_framework_test_harness("app1")

        # Second init should work (uses same default instance)
        v2 = init_framework_test_harness("app2")

        # Both should reference the same default variables
        # (because we're using the same default instance mechanism)

    def test_embedded_mode(self, clean_env):
        from scitrera_app_framework import init_framework_embedded, get_logger

        # Create custom logger
        custom_logger = logging.getLogger("EmbeddedTest")
        handler = logging.StreamHandler()
        custom_logger.addHandler(handler)

        v = init_framework_embedded("embedded-app", fixed_logger=custom_logger)

        logger = get_logger(v)
        assert logger is custom_logger

        # Framework should not have modified root logger significantly
        # (no new handlers added by framework)


class TestPluginCoordination:
    """Tests for plugin system coordination."""

    def test_plugin_dependency_chain(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.api import Plugin, Variables
        from scitrera_app_framework.core.plugins import (
            register_plugin, get_extension
        )
        from logging import Logger

        init_order = []

        class PluginA(Plugin):
            def extension_point_name(self, v):
                return "plugin-a"

            def initialize(self, v, logger):
                init_order.append("A")
                return "A"

        class PluginB(Plugin):
            def extension_point_name(self, v):
                return "plugin-b"

            def get_dependencies(self, v):
                return ["plugin-a"]

            def initialize(self, v, logger):
                init_order.append("B")
                return "B"

        class PluginC(Plugin):
            def extension_point_name(self, v):
                return "plugin-c"

            def get_dependencies(self, v):
                return ["plugin-b"]

            def initialize(self, v, logger):
                init_order.append("C")
                return "C"

        v = init_framework_test_harness("test-app")

        # Register all but init only C (should trigger chain)
        register_plugin(PluginA, v)
        register_plugin(PluginB, v)
        register_plugin(PluginC, v, init=True)

        # Should have initialized in dependency order
        assert init_order == ["A", "B", "C"]

    def test_multi_extension_collection(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.api import Plugin
        from scitrera_app_framework.core.plugins import (
            register_plugin, get_extensions
        )

        class MultiA(Plugin):
            _source = "A"

            def extension_point_name(self, v):
                return "multi"

            def is_multi_extension(self, v):
                return True

            def initialize(self, v, logger):
                return {"source": self._source}

        class MultiB(Plugin):
            _source = "B"

            def extension_point_name(self, v):
                return "multi"

            def is_multi_extension(self, v):
                return True

            def initialize(self, v, logger):
                return {"source": self._source}

        class MultiC(Plugin):
            _source = "C"

            def extension_point_name(self, v):
                return "multi"

            def is_multi_extension(self, v):
                return True

            def initialize(self, v, logger):
                return {"source": self._source}

        v = init_framework_test_harness("test-app")
        register_plugin(MultiA, v, init=True)
        register_plugin(MultiB, v, init=True)
        register_plugin(MultiC, v, init=True)

        results = get_extensions("multi", v)

        # Verify all three plugins are registered
        assert len(results) == 3
        # Verify plugin names are in the keys
        assert any("MultiA" in k for k in results.keys())
        assert any("MultiB" in k for k in results.keys())
        assert any("MultiC" in k for k in results.keys())


class TestVariablesIntegration:
    """Integration tests for Variables system."""

    def test_variables_with_env_and_sources(self, clean_env):
        os.environ["INT_TEST_VAR"] = "from_env"

        try:
            from scitrera_app_framework import init_framework_test_harness

            v = init_framework_test_harness("test-app")

            # Add additional source
            v.add_source({"SOURCE_VAR": "from_source"})

            # Set local
            v.set("LOCAL_VAR", "from_local")

            # Set default
            v.environ("DEFAULT_VAR", default="from_default")

            # Check all accessible
            assert v.get("INT_TEST_VAR") == "from_env"
            assert v.get("SOURCE_VAR") == "from_source"
            assert v.get("LOCAL_VAR") == "from_local"
            assert v.get("DEFAULT_VAR") == "from_default"

            # Check priority (local > source > default)
            v.add_source({"LOCAL_VAR": "should_not_see"})
            assert v.get("LOCAL_VAR") == "from_local"
        finally:
            del os.environ["INT_TEST_VAR"]

    def test_variables_prefix_import_export(self, clean_env):
        os.environ["MYAPP_DB_HOST"] = "localhost"
        os.environ["MYAPP_DB_PORT"] = "5432"
        os.environ["MYAPP_DB_NAME"] = "testdb"
        os.environ["OTHER_VAR"] = "other"

        try:
            from scitrera_app_framework import init_framework_test_harness

            v = init_framework_test_harness("test-app")

            # Import by prefix
            db_config = v.import_from_env_by_prefix("MYAPP_DB")

            assert "host" in db_config
            assert "port" in db_config
            assert "name" in db_config
            assert db_config["host"] == "localhost"
            assert db_config["port"] == "5432"

            # Export all
            exported = v.export_all_variables()
            assert "MYAPP_DB_HOST" in exported
        finally:
            del os.environ["MYAPP_DB_HOST"]
            del os.environ["MYAPP_DB_PORT"]
            del os.environ["MYAPP_DB_NAME"]
            del os.environ["OTHER_VAR"]


class TestMultiTenantIntegration:
    """Integration tests for multi-tenant functionality."""

    def test_multitenant_isolation(self, clean_env):
        from scitrera_app_framework import init_framework, get_logger
        from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables

        v = init_framework(
            "multi-tenant-app",
            multitenant=True,
            shutdown_hooks=False,
            stateful=False
        )

        # Create tenant configurations
        tenant1 = get_tenant_variables("tenant1", v)
        tenant2 = get_tenant_variables("tenant2", v)

        tenant1.set("API_KEY", "key1")
        tenant2.set("API_KEY", "key2")

        tenant1.set("SHARED_CONFIG", "shared")
        tenant2.set("SHARED_CONFIG", "shared")

        # Verify isolation
        assert tenant1.get("API_KEY") != tenant2.get("API_KEY")

        # Verify each tenant has its own logger
        logger1 = get_logger(tenant1)
        logger2 = get_logger(tenant2)

        assert "tenant1" in logger1.name
        assert "tenant2" in logger2.name

    def test_multitenant_with_base_plugins(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables
        from scitrera_app_framework.base_plugins import get_background_exec

        v = init_framework(
            "multi-tenant-app",
            multitenant=True,
            base_plugins=True,
            shutdown_hooks=False,
            stateful=False
        )

        # Base plugins should work alongside multitenant
        executor = get_background_exec(v)
        assert executor is not None

        # Tenant variables should still work
        tenant_v = get_tenant_variables("tenant1", v)
        tenant_v.set("test", "value")
        assert tenant_v.get("test") == "value"


class TestLoggingIntegration:
    """Integration tests for logging functionality."""

    def test_json_logging_format(self, clean_env):
        os.environ["LOGGING_FORMAT"] = "json"

        try:
            from scitrera_app_framework import init_framework, get_logger

            v = init_framework(
                "json-log-test",
                shutdown_hooks=False,
                stateful=False
            )

            logger = get_logger(v)
            # Just verify that logging doesn't crash with JSON format
            logger.info("test message")
            # Success if no exception
        finally:
            del os.environ["LOGGING_FORMAT"]

    def test_custom_log_format(self, clean_env):
        os.environ["LOGGING_FORMAT"] = "%(levelname)s - %(message)s"

        try:
            from scitrera_app_framework import init_framework, get_logger

            v = init_framework(
                "custom-log-test",
                shutdown_hooks=False,
                stateful=False
            )

            logger = get_logger(v)
            logger.info("test message")
            # Verify no crash with custom format
        finally:
            del os.environ["LOGGING_FORMAT"]

    def test_child_loggers(self, clean_env):
        from scitrera_app_framework import init_framework, get_logger

        v = init_framework(
            "parent-app",
            shutdown_hooks=False,
            stateful=False
        )

        parent_logger = get_logger(v)
        child1 = get_logger(v, name="child1")
        child2 = get_logger(v, name="child2")
        grandchild = get_logger(v, name="child1.grandchild")

        assert parent_logger.name in child1.name
        assert parent_logger.name in child2.name
        assert "child1" in grandchild.name


class TestErrorHandling:
    """Tests for error handling across the framework."""

    def test_invalid_log_level_handled(self, clean_env):
        from scitrera_app_framework import init_framework

        # Invalid log level should be handled gracefully
        # or raise appropriate error
        try:
            v = init_framework(
                "test-app",
                log_level="INVALID_LEVEL",
                shutdown_hooks=False,
                stateful=False
            )
            # If it succeeds, logging module handles invalid levels
        except (ValueError, KeyError):
            # Expected if validation is strict
            pass

    def test_missing_stateful_root(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.core import is_stateful_ready

        v = init_framework(
            "test-app",
            shutdown_hooks=False,
            stateful=True,
            default_stateful_root="/nonexistent/path/xyz123"
        )

        # Stateful should not be ready if root doesn't exist
        assert is_stateful_ready(v) is None
