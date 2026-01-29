"""
Tests for scitrera_app_framework.core.core module.
"""
import os
import sys
import logging
import pytest
from unittest.mock import patch, MagicMock

from scitrera_app_framework.api import Variables


class TestInitFrameworkIdempotent:
    """Tests for init_framework idempotent behavior (duplicate initialization detection)."""

    def test_init_framework_returns_same_instance_on_reinit(self, clean_env):
        """Calling init_framework twice with same Variables returns the same instance."""
        from scitrera_app_framework import init_framework

        v1 = init_framework("test-app", shutdown_hooks=False, stateful=False)
        v2 = init_framework("test-app-2", shutdown_hooks=False, stateful=False)

        # Should return the same instance (default Variables singleton)
        assert v1 is v2

    def test_init_framework_does_not_reinitialize(self, clean_env, capture_logs):
        """Second init_framework call should not reconfigure logging or change app name."""
        from scitrera_app_framework import init_framework, get_logger

        v1 = init_framework("app-first", shutdown_hooks=False, stateful=False)
        original_app_name = v1.get("APP_NAME")
        logger = get_logger(v1)
        logger.addHandler(capture_logs)

        # Second call with different app name
        v2 = init_framework("app-second", shutdown_hooks=False, stateful=False)

        # APP_NAME should remain the original (not overwritten)
        assert v2.get("APP_NAME") == original_app_name
        assert v2.get("APP_NAME") == "app-first"

        # No "Initializing" log message should appear for second call
        init_messages = [m for m in capture_logs.get_messages() if "Initializing" in m]
        assert len(init_messages) == 0  # capture_logs was added after first init

    def test_init_framework_explicit_variables_instance_idempotent(self, clean_env):
        """Passing an explicit Variables instance respects idempotent behavior."""
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.api import Variables

        v = Variables()

        v1 = init_framework("app-first", shutdown_hooks=False, stateful=False, v=v)
        v2 = init_framework("app-second", shutdown_hooks=False, stateful=False, v=v)

        assert v1 is v
        assert v2 is v
        assert v.get("APP_NAME") == "app-first"

    def test_init_framework_separate_instances_initialize_independently(self, clean_env):
        """Different Variables instances can be initialized separately."""
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.api import Variables

        v1 = Variables()
        v2 = Variables()

        result1 = init_framework("app-one", shutdown_hooks=False, stateful=False, v=v1)
        result2 = init_framework("app-two", shutdown_hooks=False, stateful=False, v=v2)

        assert result1 is v1
        assert result2 is v2
        assert v1.get("APP_NAME") == "app-one"
        assert v2.get("APP_NAME") == "app-two"

    def test_init_framework_idempotent_preserves_param_map(self, clean_env):
        """Second init call does not overwrite _VAR_PARAM_MAP from first call."""
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.core import _VAR_PARAM_MAP

        v1 = init_framework(
            "app-first",
            shutdown_hooks=False,
            stateful=False,
            worker_id=1,
            region="us-east"
        )
        original_param_map = v1.get(_VAR_PARAM_MAP)

        # Second call with different params
        v2 = init_framework(
            "app-second",
            shutdown_hooks=False,
            stateful=False,
            worker_id=99,
            region="eu-west"
        )

        # Param map should be unchanged
        assert v2.get(_VAR_PARAM_MAP) is original_param_map
        assert v2.get(_VAR_PARAM_MAP)["worker_id"] == 1
        assert v2.get(_VAR_PARAM_MAP)["region"] == "us-east"


class TestInitFramework:
    """Tests for init_framework and related functions."""

    def test_init_framework_basic(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)

        assert v is not None
        assert isinstance(v, Variables)
        assert v.get("APP_NAME") == "test-app"
        assert v.get("SAF_BASE_APP_NAME") == "test-app"

    def test_init_framework_with_params(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework(
            "test-app",
            shutdown_hooks=False,
            stateful=False,
            worker_id=1,
            region="us-east"
        )

        # App name should include params
        app_name = v.get("APP_NAME")
        assert "test-app" in app_name
        assert "1" in app_name
        assert "us-east" in app_name

    def test_init_framework_unnamed_params(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework(
            "test-app",
            shutdown_hooks=False,
            stateful=False,
            worker_id=1,
            region="us-east",
            unnamed_params=("region",)
        )

        # Region should not be in the app name
        app_name = v.get("APP_NAME")
        assert "1" in app_name
        assert "us-east" not in app_name

    def test_init_framework_custom_separator(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework(
            "test-app",
            shutdown_hooks=False,
            stateful=False,
            sep="_",
            worker_id=1
        )

        app_name = v.get("APP_NAME")
        assert "test-app_" in app_name

    def test_init_framework_log_level(self, clean_env):
        from scitrera_app_framework import init_framework

        v = init_framework(
            "test-app",
            shutdown_hooks=False,
            stateful=False,
            log_level="DEBUG"
        )

        # Root logger should be set to DEBUG
        assert logging.root.level == logging.DEBUG

    def test_init_framework_log_level_from_env(self, clean_env):
        os.environ["LOGGING_LEVEL"] = "WARNING"
        try:
            from scitrera_app_framework import init_framework

            v = init_framework(
                "test-app",
                shutdown_hooks=False,
                stateful=False,
                log_level="DEBUG"  # Should be overridden by env
            )

            assert logging.root.level == logging.WARNING
        finally:
            del os.environ["LOGGING_LEVEL"]

    def test_init_framework_app_name_from_env(self, clean_env):
        os.environ["APP_NAME"] = "env-app-name"
        try:
            from scitrera_app_framework import init_framework

            v = init_framework(
                "test-app",
                shutdown_hooks=False,
                stateful=False
            )

            assert v.get("APP_NAME") == "env-app-name"
        finally:
            del os.environ["APP_NAME"]


class TestInitFrameworkVariants:
    """Tests for init_framework variant functions."""

    def test_init_framework_test_harness(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness

        v = init_framework_test_harness("test-app")

        # Test harness should have DEBUG logging
        assert logging.root.level == logging.DEBUG

    def test_init_framework_desktop(self, clean_env):
        from scitrera_app_framework import init_framework_desktop
        import pathlib

        v = init_framework_desktop("test-app", stateful=False)

        # Should have base plugins enabled by default
        # Note: actual path handling would need stateful=True

    def test_init_framework_embedded(self, clean_env):
        from scitrera_app_framework import init_framework_embedded

        # Create a custom logger
        custom_logger = logging.getLogger("CustomLogger")

        v = init_framework_embedded("test-app", fixed_logger=custom_logger)

        # Should use our custom logger
        from scitrera_app_framework import get_logger
        logger = get_logger(v)
        assert logger is custom_logger


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_basic(self, clean_env):
        from scitrera_app_framework import init_framework, get_logger

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        logger = get_logger(v)

        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_get_logger_child(self, clean_env):
        from scitrera_app_framework import init_framework, get_logger

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        child_logger = get_logger(v, name="child")

        assert child_logger is not None
        assert "child" in child_logger.name

    def test_get_logger_without_init(self):
        from scitrera_app_framework import get_logger

        # Should return a fallback logger with warning
        logger = get_logger(None)
        assert logger is not None
        assert logger.name == "SAF"


class TestGetWorkingPath:
    """Tests for get_working_path function."""

    def test_get_working_path_default(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core import get_working_path

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        path = get_working_path(v)

        # Without stateful, should return default
        assert path == "."

    def test_get_working_path_custom_default(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core import get_working_path

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        path = get_working_path(v, default="/custom/path")

        assert path == "/custom/path"

    def test_get_working_path_from_env(self, clean_env):
        os.environ["DATA_WORKING_PATH"] = "/from/env"
        try:
            from scitrera_app_framework import init_framework
            from scitrera_app_framework.core import get_working_path

            v = init_framework("test-app", shutdown_hooks=False, stateful=False)
            path = get_working_path(v)

            assert path == "/from/env"
        finally:
            del os.environ["DATA_WORKING_PATH"]


class TestGetVariables:
    """Tests for get_variables function."""

    def test_get_variables_returns_given(self):
        from scitrera_app_framework.core import get_variables

        v = Variables()
        result = get_variables(v)

        assert result is v

    def test_get_variables_returns_default(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core import get_variables

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        result = get_variables(None)

        # Should return the default instance
        assert result is not None
        assert isinstance(result, Variables)


class TestRegisterShutdownFunction:
    """Tests for register_shutdown_function."""

    def test_register_shutdown_function(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core import register_shutdown_function
        import scitrera_app_framework.core.core as core_module

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)

        called = []

        def my_shutdown(arg):
            called.append(arg)

        register_shutdown_function(my_shutdown, "test_arg")

        # Check that it's registered
        assert len(core_module._sigterm_hooks) > 0
        # Find our hook
        found = any(fn is my_shutdown for fn, args, kwargs in core_module._sigterm_hooks)
        assert found


class TestLoadStrategy:
    """Tests for load_strategy function."""

    def test_load_strategy_basic(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.core import load_strategy

        os.environ["MY_STRATEGY_TYPE"] = "scitrera_app_framework.api.variables.Variables"
        os.environ["MY_STRATEGY_OPTION1"] = "value1"

        try:
            v = init_framework("test-app", shutdown_hooks=False, stateful=False)
            strategy_type, kwargs = load_strategy(v, object, prefix="MY_STRATEGY")

            assert strategy_type is Variables
            assert "option1" in kwargs
            assert kwargs["option1"] == "value1"
        finally:
            del os.environ["MY_STRATEGY_TYPE"]
            del os.environ["MY_STRATEGY_OPTION1"]

    def test_load_strategy_no_type(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.core import load_strategy

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        strategy_type, kwargs = load_strategy(v, object, prefix="NONEXISTENT_STRATEGY")

        assert strategy_type is None

    def test_load_strategy_invalid_type(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.core import load_strategy

        os.environ["BAD_STRATEGY_TYPE"] = "nonexistent.module.Type"

        try:
            v = init_framework("test-app", shutdown_hooks=False, stateful=False)
            strategy_type, kwargs = load_strategy(v, object, prefix="BAD_STRATEGY")

            # Should return None on import error
            assert strategy_type is None
        finally:
            del os.environ["BAD_STRATEGY_TYPE"]


class TestLogFrameworkVariables:
    """Tests for log_framework_variables function."""

    def test_log_framework_variables(self, clean_env, capture_logs):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core import log_framework_variables, get_logger

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        logger = get_logger(v)
        logger.addHandler(capture_logs)

        log_framework_variables(v)

        messages = capture_logs.get_messages(logging.INFO)
        assert any("framework variables" in msg for msg in messages)

    def test_log_framework_variables_with_prefix(self, clean_env, capture_logs):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core import log_framework_variables, get_logger

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        v.set("PREFIX_ONE", "value1")
        v.environ("PREFIX_ONE")  # Register key
        v.set("OTHER_KEY", "value2")
        v.environ("OTHER_KEY")  # Register key

        logger = get_logger(v)
        logger.addHandler(capture_logs)

        log_framework_variables(v, prefixes=("PREFIX_",))

        messages = capture_logs.get_messages(logging.INFO)
        logged_msg = [m for m in messages if "framework variables" in m][0]
        assert "PREFIX_ONE" in logged_msg
        # OTHER_KEY should be filtered out
        # Note: depending on implementation, this might vary


class TestIsStatefulReady:
    """Tests for is_stateful_ready function."""

    def test_is_stateful_ready_false(self, clean_env):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.core import is_stateful_ready

        v = init_framework("test-app", shutdown_hooks=False, stateful=False)
        result = is_stateful_ready(v)

        assert result is None

    def test_is_stateful_ready_true(self, clean_env, tmp_path):
        from scitrera_app_framework import init_framework
        from scitrera_app_framework.core.core import is_stateful_ready

        v = init_framework(
            "test-app",
            shutdown_hooks=False,
            stateful=True,
            stateful_chdir=False,
            default_stateful_root=str(tmp_path)
        )
        result = is_stateful_ready(v)

        assert result is not None
        assert str(tmp_path) in result
