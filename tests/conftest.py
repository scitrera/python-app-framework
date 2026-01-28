"""
Pytest configuration and shared fixtures for scitrera_app_framework tests.
"""
import os
import sys
import pytest
import logging


@pytest.fixture(autouse=True)
def reset_framework_state():
    """Reset framework global state before each test."""
    # Import here to avoid circular imports
    import scitrera_app_framework.core.core as core_module
    import scitrera_app_framework.core.plugins as plugins_module

    # Store original state
    original_default_vars = core_module._default_vars_inst
    original_sigterm_hooks = core_module._sigterm_hooks.copy()

    yield

    # Reset state after test
    core_module._default_vars_inst = original_default_vars
    core_module._sigterm_hooks.clear()
    core_module._sigterm_hooks.extend(original_sigterm_hooks)


@pytest.fixture
def clean_env():
    """Provide a clean environment, removing SAF-related env vars temporarily."""
    saf_vars = {k: v for k, v in os.environ.items()
                if k.startswith('SAF_') or k.startswith('LOGGING_') or k == 'APP_NAME'}
    for k in saf_vars:
        del os.environ[k]

    yield

    # Restore
    os.environ.update(saf_vars)


@pytest.fixture
def temp_env():
    """Context manager to temporarily set environment variables."""
    original = {}

    def _set_env(**kwargs):
        for k, v in kwargs.items():
            if k in os.environ:
                original[k] = os.environ[k]
            os.environ[k] = str(v)

    yield _set_env

    # Cleanup
    for k in list(os.environ.keys()):
        if k in original:
            os.environ[k] = original[k]
        elif k not in original and k in os.environ:
            # Only delete if we added it
            pass


@pytest.fixture
def fresh_variables():
    """Create a fresh Variables instance for testing."""
    from scitrera_app_framework.api import Variables
    return Variables()


@pytest.fixture
def capture_logs():
    """Capture log output for assertions."""
    class LogCapture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(record)

        def get_messages(self, level=None):
            if level is None:
                return [r.getMessage() for r in self.records]
            return [r.getMessage() for r in self.records if r.levelno == level]

    handler = LogCapture()
    handler.setLevel(logging.DEBUG)

    yield handler

    # Cleanup happens automatically as handler goes out of scope
