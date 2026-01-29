"""
Tests for scitrera_app_framework.ext_plugins module.
"""
import os
import pytest
from typing import Iterable

from scitrera_app_framework.api import Variables, EnvPlacement


class TestMultiTenantPlugin:
    """Tests for MultiTenantPlugin and related functionality."""

    def test_multitenant_disabled_by_default(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.plugins import get_extension
        from scitrera_app_framework.ext_plugins.multi_tenant import EXT_MULTITENANT

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)

        # Multi-tenant should not be enabled by default
        with pytest.raises(ValueError):
            get_extension(EXT_MULTITENANT, v)

    def test_multitenant_enabled_via_kwarg(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.ext_plugins.multi_tenant import (
            get_tenant_provider, BaseMultiTenantProvider
        )

        v = init_framework(
            "test-app",
            multitenant=True,
            shutdown_hooks=False,
            stateful=False
        )

        provider = get_tenant_provider(v)
        assert provider is not None
        assert isinstance(provider, BaseMultiTenantProvider)

    def test_multitenant_enabled_via_env(self, clean_env):
        os.environ["SAF_MULTITENANT_ENABLED"] = "true"

        try:
            from scitrera_app_framework import init_framework
            from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_provider

            v = init_framework("test-app", shutdown_hooks=False, stateful=False)

            provider = get_tenant_provider(v)
            assert provider is not None
        finally:
            del os.environ["SAF_MULTITENANT_ENABLED"]

    def test_get_tenant_variables(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables

        v = init_framework(
            "test-app",
            multitenant=True,
            shutdown_hooks=False,
            stateful=False
        )

        tenant_v = get_tenant_variables("tenant1", v)

        assert tenant_v is not None
        assert isinstance(tenant_v, Variables)

    def test_tenant_variables_isolated(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables

        v = init_framework(
            "test-app",
            multitenant=True,
            shutdown_hooks=False,
            stateful=False
        )

        tenant1_v = get_tenant_variables("tenant1", v)
        tenant2_v = get_tenant_variables("tenant2", v)

        # Set values in each tenant
        tenant1_v.set("key", "tenant1_value")
        tenant2_v.set("key", "tenant2_value")

        # Values should be isolated
        assert tenant1_v.get("key") == "tenant1_value"
        assert tenant2_v.get("key") == "tenant2_value"

    def test_tenant_variables_cached(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables

        v = init_framework(
            "test-app",
            multitenant=True,
            shutdown_hooks=False,
            stateful=False
        )

        tenant_v1 = get_tenant_variables("tenant1", v)
        tenant_v2 = get_tenant_variables("tenant1", v)

        # Same tenant ID should return same instance
        assert tenant_v1 is tenant_v2

    def test_tenant_has_logger(self, clean_env):
        from scitrera_app_framework import init_framework, get_logger
        from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables

        v = init_framework(
            "test-app",
            multitenant=True,
            shutdown_hooks=False,
            stateful=False
        )

        tenant_v = get_tenant_variables("tenant1", v)
        logger = get_logger(tenant_v)

        assert logger is not None
        assert "tenant1" in logger.name


class TestBaseMultiTenantProvider:
    """Tests for BaseMultiTenantProvider class."""

    def test_provider_getitem(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.ext_plugins.multi_tenant import (
            get_tenant_provider, BaseMultiTenantProvider
        )

        v = init_framework(
            "test-app",
            multitenant=True,
            shutdown_hooks=False,
            stateful=False
        )

        provider = get_tenant_provider(v)
        tenant_v = provider["my_tenant"]

        assert tenant_v is not None
        assert isinstance(tenant_v, Variables)

    def test_provider_get_method(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_provider

        v = init_framework(
            "test-app",
            multitenant=True,
            shutdown_hooks=False,
            stateful=False
        )

        provider = get_tenant_provider(v)
        tenant_v = provider.get("my_tenant")

        assert tenant_v is not None


class TestCustomMultiTenantProvider:
    """Tests for custom multi-tenant provider."""

    def test_custom_provider_basic(self, clean_env):
        """Test that BaseMultiTenantProvider can be subclassed and used."""
        from scitrera_app_framework.ext_plugins.multi_tenant import BaseMultiTenantProvider
        from scitrera_app_framework import init_framework_test_harness

        # Create a root Variables for the provider
        v = init_framework_test_harness("test-app")

        # Define custom provider
        class CustomProvider(BaseMultiTenantProvider):
            custom_attr = "custom_value"

            def _tenant_sources(self, tenant_id: str) -> Iterable:
                return [{"custom_source_key": f"value_for_{tenant_id}"}]

        # Create provider instance directly
        provider = CustomProvider(v)
        assert hasattr(provider, 'custom_attr')
        assert provider.custom_attr == "custom_value"

        # Custom sources should be available
        tenant_v = provider["tenant1"]
        assert tenant_v.get("custom_source_key") == "value_for_tenant1"


class TestMultiTenantEnvPlacement:
    """Tests for multi-tenant environment variable placement."""

    def test_env_placement_ignored_by_default(self, clean_env):
        os.environ["TEST_ENV_VAR"] = "from_process_env"

        try:
            from scitrera_app_framework import init_framework
            from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables

            v = init_framework(
                "test-app",
                multitenant=True,
                shutdown_hooks=False,
                stateful=False
            )

            tenant_v = get_tenant_variables("tenant1", v)

            # By default, env is IGNORED for tenant variables
            assert tenant_v.get("TEST_ENV_VAR") is None
        finally:
            del os.environ["TEST_ENV_VAR"]

    def test_env_placement_bottom_when_configured(self, clean_env):
        os.environ["TEST_ENV_VAR2"] = "from_process_env"
        os.environ["SAF_MULTITENANT_INCLUDE_ENV"] = "true"

        try:
            from scitrera_app_framework import init_framework
            from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables

            v = init_framework(
                "test-app",
                multitenant=True,
                shutdown_hooks=False,
                stateful=False
            )

            tenant_v = get_tenant_variables("tenant1", v)

            # With INCLUDE_ENV=true, env should be accessible
            assert tenant_v.get("TEST_ENV_VAR2") == "from_process_env"
        finally:
            del os.environ["TEST_ENV_VAR2"]
            del os.environ["SAF_MULTITENANT_INCLUDE_ENV"]


class TestPyroscopePlugin:
    """Tests for PyroscopePlugin (behavior when pyroscope not installed)."""

    def test_pyroscope_disabled_by_default(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.plugins import get_extension
        from scitrera_app_framework.ext_plugins.pyroscope_plugin import EXT_PYROSCOPE

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)

        # Pyroscope is always registered but disabled by default
        # When disabled, get_extension should fail
        with pytest.raises(ValueError):
            get_extension(EXT_PYROSCOPE, v)

    def test_pyroscope_enabled_but_not_installed(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.plugins import get_extension
        from scitrera_app_framework.ext_plugins.pyroscope_plugin import EXT_PYROSCOPE

        # When enabled but pyroscope not installed, should return None
        v = init_framework(
            "test-app",
            pyroscope=True,
            shutdown_hooks=False,
            stateful=False
        )

        result = get_extension(EXT_PYROSCOPE, v)
        # Result should be None since pyroscope module not installed
        assert result is None

    def test_pyroscope_constants(self):
        from scitrera_app_framework.ext_plugins.pyroscope_plugin import (
            EXT_PYROSCOPE, PYROSCOPE_ENABLED
        )

        assert EXT_PYROSCOPE == "pyroscope"
        assert PYROSCOPE_ENABLED == "PYROSCOPE_ENABLED"
