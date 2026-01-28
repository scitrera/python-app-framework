"""
Tests for scitrera_app_framework.core.util module.
"""
import os
import pytest
from pathlib import Path


class TestAddEnvFileSource:
    """Tests for add_env_file_source function."""

    def test_add_env_file_source(self, clean_env, tmp_path):
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\nANOTHER_VAR=another_value\n")

        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.util import add_env_file_source

        v = init_framework_test_harness("test-app")

        try:
            add_env_file_source(str(env_file), v)

            # Values should be accessible
            assert v.get("TEST_VAR") == "test_value"
            assert v.get("ANOTHER_VAR") == "another_value"
        except ImportError:
            pytest.skip("python-dotenv not installed")

    def test_add_env_file_source_with_path_object(self, clean_env, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PATH_VAR=path_value\n")

        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.util import add_env_file_source

        v = init_framework_test_harness("test-app")

        try:
            add_env_file_source(env_file, v)  # Pass Path object directly
            assert v.get("PATH_VAR") == "path_value"
        except ImportError:
            pytest.skip("python-dotenv not installed")

    def test_add_env_file_source_priority(self, clean_env, tmp_path):
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("PRIORITY_VAR=from_file\n")

        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.util import add_env_file_source

        v = init_framework_test_harness("test-app")

        try:
            add_env_file_source(str(env_file), v)

            # Local should override file
            v.set("PRIORITY_VAR", "from_local")
            assert v.get("PRIORITY_VAR") == "from_local"
        except ImportError:
            pytest.skip("python-dotenv not installed")

    def test_add_env_file_source_env_priority(self, clean_env, tmp_path):
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("ENV_PRIORITY_VAR=from_file\n")

        os.environ["ENV_PRIORITY_VAR"] = "from_env"

        try:
            from scitrera_app_framework import init_framework_test_harness
            from scitrera_app_framework.core.util import add_env_file_source

            v = init_framework_test_harness("test-app")

            try:
                add_env_file_source(str(env_file), v)

                # Environment should override file (default EnvPlacement.TOP)
                assert v.get("ENV_PRIORITY_VAR") == "from_env"
            except ImportError:
                pytest.skip("python-dotenv not installed")
        finally:
            del os.environ["ENV_PRIORITY_VAR"]

    def test_add_env_file_without_dotenv_raises(self, clean_env, tmp_path):
        # This test verifies the error handling when dotenv is not available
        # Since we have dotenv installed for testing, skip this test
        try:
            import dotenv
            pytest.skip("python-dotenv is installed, cannot test ImportError path")
        except ImportError:
            # dotenv not installed, we can test the error path
            from scitrera_app_framework import init_framework_test_harness
            from scitrera_app_framework.core.util import add_env_file_source

            v = init_framework_test_harness("test-app")
            env_file = tmp_path / ".env"
            env_file.write_text("VAR=value\n")

            with pytest.raises(ImportError, match="dotenv"):
                add_env_file_source(str(env_file), v)

    def test_add_env_file_nonexistent_file(self, clean_env):
        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.util import add_env_file_source

        v = init_framework_test_harness("test-app")

        try:
            # Should not raise, but values won't be set
            add_env_file_source("/nonexistent/path/.env", v)
            # Just verify no crash
            assert True
        except ImportError:
            pytest.skip("python-dotenv not installed")

    def test_add_env_file_uses_default_variables(self, clean_env, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DEFAULT_TEST=default_value\n")

        from scitrera_app_framework import init_framework_test_harness
        from scitrera_app_framework.core.util import add_env_file_source
        from scitrera_app_framework.core import get_variables

        v = init_framework_test_harness("test-app")

        try:
            # Call without v parameter - should use default
            add_env_file_source(str(env_file))

            # Get default variables instance and check
            default_v = get_variables(None)
            assert default_v.get("DEFAULT_TEST") == "default_value"
        except ImportError:
            pytest.skip("python-dotenv not installed")
