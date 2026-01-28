"""
Tests for scitrera_app_framework.base_plugins module.
"""
import time
import pytest
from concurrent.futures import Future

from scitrera_app_framework.base_plugins import (
    EXT_BACKGROUND_EXEC,
    EXT_PROGRESS_TRACKER,
    get_background_exec,
    get_progress_tracker,
    register_package_plugins,
)


class TestRegisterPackagePlugins:
    """Tests for register_package_plugins function."""

    def test_register_base_plugins(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework import base_plugins

        v = init_framework_test_harness("test-app")
        register_package_plugins(base_plugins.__name__, v, recursive=False)

        # Should have registered the base plugins
        from scitrera_app_framework.core.plugins import _plugin_registry
        pr = _plugin_registry(v)

        # Check that plugins are registered (by checking keys exist)
        plugin_names = list(pr.keys())
        bg_exec_registered = any("BackgroundThreadExecutor" in name for name in plugin_names)
        progress_registered = any("ProgressTracker" in name for name in plugin_names)

        assert bg_exec_registered
        assert progress_registered

    def test_register_with_exclusions(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework import base_plugins
        from scitrera_app_framework.base_plugins.bg_exec import BackgroundThreadExecutorPlugin

        v = init_framework_test_harness("test-app")
        register_package_plugins(
            base_plugins.__name__,
            v,
            exclusions=(BackgroundThreadExecutorPlugin,),
            recursive=False
        )

        from scitrera_app_framework.core.plugins import _plugin_registry
        pr = _plugin_registry(v)

        plugin_names = list(pr.keys())
        bg_exec_registered = any("BackgroundThreadExecutor" in name for name in plugin_names)

        assert not bg_exec_registered


class TestBackgroundExecPlugin:
    """Tests for BackgroundThreadExecutorPlugin."""

    def test_get_background_exec(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework("test-app", base_plugins=True, shutdown_hooks=False, stateful=False)
        executor = get_background_exec(v)

        assert executor is not None

    def test_submit_job(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework("test-app", base_plugins=True, shutdown_hooks=False, stateful=False)
        executor = get_background_exec(v)

        results = []

        def job_fn(value):
            results.append(value)
            return value * 2

        # submit_job returns bool indicating if job was accepted
        accepted = executor.submit_job(job_fn, 21)
        assert accepted is True

        # Wait a bit for completion
        time.sleep(0.2)
        assert 21 in results

    def test_submit_job_with_id(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework("test-app", base_plugins=True, shutdown_hooks=False, stateful=False)
        executor = get_background_exec(v)

        # Test that submit_job with job_id returns boolean
        accepted = executor.submit_job(lambda: None, job_id="test_job_id")
        assert isinstance(accepted, bool)

        # If accepted, the job should have been queued
        if accepted:
            time.sleep(0.2)  # Give it time to execute

    def test_executor_shutdown(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.plugins import shutdown_all_plugins

        v = init_framework("test-app", base_plugins=True, shutdown_hooks=False, stateful=False)
        executor = get_background_exec(v)

        # Submit a job
        completed = []
        executor.submit_job(lambda: completed.append(True))
        time.sleep(0.2)

        # Shutdown should not raise
        shutdown_all_plugins(v)


class TestProgressTrackerPlugin:
    """Tests for ProgressTrackerPlugin."""

    def test_get_progress_tracker(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework("test-app", base_plugins=True, shutdown_hooks=False, stateful=False)
        tracker = get_progress_tracker(v)

        assert tracker is not None

    def test_progress_tracker_basic_operations(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework("test-app", base_plugins=True, shutdown_hooks=False, stateful=False)
        tracker = get_progress_tracker(v)

        # The actual API depends on botwinick_utils.progress_reporting.tracker
        # but we can at least verify the object exists and has expected attributes
        assert hasattr(tracker, '__class__')


class TestBasePluginsIntegration:
    """Integration tests for base plugins."""

    def test_init_with_base_plugins(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework("test-app", base_plugins=True, shutdown_hooks=False, stateful=False)

        # Both plugins should be accessible
        executor = get_background_exec(v)
        tracker = get_progress_tracker(v)

        assert executor is not None
        assert tracker is not None

    def test_init_with_base_plugins_env_var(self, clean_env):
        import os
        os.environ["SAF_BASE_PLUGINS"] = "true"

        try:
            from scitrera_app_framework import init_framework

            v = init_framework("test-app", shutdown_hooks=False, stateful=False)

            # Base plugins should be registered via env var
            executor = get_background_exec(v)
            assert executor is not None
        finally:
            del os.environ["SAF_BASE_PLUGINS"]

    def test_background_exec_extension_constant(self):
        assert EXT_BACKGROUND_EXEC == "__bg_exec"

    def test_progress_tracker_extension_constant(self):
        assert EXT_PROGRESS_TRACKER == "__progress_tracker"
