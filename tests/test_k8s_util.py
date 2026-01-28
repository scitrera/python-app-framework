"""
Tests for scitrera_app_framework.k8s.util module.

Note: These tests cover utility functions that don't require actual Kubernetes connectivity.
Functions like start_pod, is_pod_running, etc. that require K8s are not tested here.
"""
import pytest

# Skip all tests in this module if kubernetes is not installed
pytest.importorskip("kubernetes", reason="kubernetes package not installed")

from scitrera_app_framework.k8s.util import (
    get_metadata_name,
    get_metadata_namespace,
    get_headless_service_dns_name_for_pod,
    fixed_env_vars,
    merge_env_vars,
    get_pod_env,
    _is_running_phase,
    _is_not_running_phase,
    _is_active_phase,
    _is_terminated_phase,
    _is_not_terminated_phase,
)


class TestGetMetadataName:
    """Tests for get_metadata_name function."""

    def test_dict_with_name(self):
        obj = {"metadata": {"name": "my-pod"}}
        assert get_metadata_name(obj) == "my-pod"

    def test_dict_without_name(self):
        obj = {"metadata": {}}
        assert get_metadata_name(obj) is None

    def test_dict_without_metadata(self):
        obj = {}
        assert get_metadata_name(obj) is None

    def test_nested_metadata(self):
        obj = {
            "metadata": {
                "name": "test-name",
                "namespace": "test-ns"
            }
        }
        assert get_metadata_name(obj) == "test-name"


class TestGetMetadataNamespace:
    """Tests for get_metadata_namespace function."""

    def test_dict_with_namespace(self):
        obj = {"metadata": {"namespace": "my-namespace"}}
        assert get_metadata_namespace(obj) == "my-namespace"

    def test_dict_without_namespace(self):
        obj = {"metadata": {"name": "pod-name"}}
        assert get_metadata_namespace(obj) is None

    def test_dict_without_metadata(self):
        obj = {}
        assert get_metadata_namespace(obj) is None


class TestGetHeadlessServiceDnsName:
    """Tests for get_headless_service_dns_name_for_pod function."""

    def test_basic_dns_name(self):
        pod = {"metadata": {"name": "my-pod"}}
        service = {"metadata": {"name": "my-service", "namespace": "default"}}

        result = get_headless_service_dns_name_for_pod(pod, service)

        assert result == "my-pod.my-service.default.svc"

    def test_custom_namespace(self):
        pod = {"metadata": {"name": "worker-0"}}
        service = {"metadata": {"name": "worker-headless", "namespace": "production"}}

        result = get_headless_service_dns_name_for_pod(pod, service)

        assert result == "worker-0.worker-headless.production.svc"


class TestFixedEnvVars:
    """Tests for fixed_env_vars function."""

    def test_basic_env_vars(self):
        result = fixed_env_vars(my_var="my_value", another="val2")

        assert len(result) == 2
        names = {item["name"] for item in result}
        assert "MY_VAR" in names
        assert "ANOTHER" in names

    def test_uppercase_keys(self):
        result = fixed_env_vars(key_upper=True, lowercase_key="value")

        assert result[0]["name"] == "LOWERCASE_KEY"
        assert result[0]["value"] == "value"

    def test_preserve_case(self):
        result = fixed_env_vars(key_upper=False, MixedCase="value")

        assert result[0]["name"] == "MixedCase"

    def test_value_conversion(self):
        result = fixed_env_vars(int_val=42, bool_val=True)

        values = {item["name"]: item["value"] for item in result}
        assert values["INT_VAL"] == "42"
        assert values["BOOL_VAL"] == "True"

    def test_empty_kwargs(self):
        result = fixed_env_vars()
        assert result == []


class TestMergeEnvVars:
    """Tests for merge_env_vars function."""

    def test_merge_kwargs_only(self):
        result = merge_env_vars(None, key1="val1", key2="val2")

        assert len(result) == 2
        names = {item["name"] for item in result}
        assert "KEY1" in names
        assert "KEY2" in names

    def test_merge_with_original(self):
        original = [{"name": "EXISTING", "value": "existing_value"}]
        result = merge_env_vars(original, new_key="new_value")

        assert len(result) == 2
        names = {item["name"] for item in result}
        assert "EXISTING" in names
        assert "NEW_KEY" in names
        # Original should be modified in-place
        assert original is result

    def test_merge_overrides_existing(self):
        original = [{"name": "KEY", "value": "old_value"}]
        result = merge_env_vars(original, KEY="new_value")

        assert len(result) == 1
        assert result[0]["value"] == "new_value"

    def test_merge_with_complex_items(self):
        original = []
        complex_item = {
            "name": "CONFIG_PATH",
            "valueFrom": {
                "configMapKeyRef": {
                    "name": "my-config",
                    "key": "path"
                }
            }
        }

        result = merge_env_vars(original, complex_item, simple="value")

        assert len(result) == 2
        names = {item["name"] for item in result}
        assert "CONFIG_PATH" in names
        assert "SIMPLE" in names

        # Check complex item preserved
        config_item = next(i for i in result if i["name"] == "CONFIG_PATH")
        assert "valueFrom" in config_item

    def test_merge_preserves_case_option(self):
        result = merge_env_vars(None, key_upper=False, MixedCase="value")

        assert result[0]["name"] == "MixedCase"


class TestGetPodEnv:
    """Tests for get_pod_env function."""

    def test_get_env_by_index(self):
        pod = {
            "spec": {
                "containers": [
                    {"name": "container-0", "env": [{"name": "VAR1", "value": "val1"}]},
                    {"name": "container-1", "env": [{"name": "VAR2", "value": "val2"}]}
                ]
            }
        }

        env = get_pod_env(pod, container_index=0)
        assert env[0]["name"] == "VAR1"

        env = get_pod_env(pod, container_index=1)
        assert env[0]["name"] == "VAR2"

    def test_get_env_by_name(self):
        pod = {
            "spec": {
                "containers": [
                    {"name": "main", "env": [{"name": "MAIN_VAR", "value": "main"}]},
                    {"name": "sidecar", "env": [{"name": "SIDECAR_VAR", "value": "sidecar"}]}
                ]
            }
        }

        env = get_pod_env(pod, container_name="sidecar")
        assert env[0]["name"] == "SIDECAR_VAR"

    def test_get_env_creates_if_missing(self):
        pod = {
            "spec": {
                "containers": [
                    {"name": "main"}  # No env key
                ]
            }
        }

        env = get_pod_env(pod)
        assert env == []
        # Should have been created
        assert "env" in pod["spec"]["containers"][0]

    def test_get_env_empty_pod(self):
        assert get_pod_env(None) is None
        assert get_pod_env({}) is None
        assert get_pod_env({"spec": {}}) is None

    def test_get_env_reference_allows_modification(self):
        pod = {
            "spec": {
                "containers": [
                    {"name": "main", "env": []}
                ]
            }
        }

        env = get_pod_env(pod)
        env.append({"name": "NEW_VAR", "value": "new"})

        # Modification should reflect in original
        assert len(pod["spec"]["containers"][0]["env"]) == 1
        assert pod["spec"]["containers"][0]["env"][0]["name"] == "NEW_VAR"


class TestPhaseHelpers:
    """Tests for pod phase helper functions."""

    def test_is_running_phase(self):
        assert _is_running_phase("Running") is True
        assert _is_running_phase("Pending") is False
        assert _is_running_phase("Succeeded") is False
        assert _is_running_phase("Failed") is False
        assert _is_running_phase(None) is False

    def test_is_not_running_phase(self):
        assert _is_not_running_phase("Running") is False
        assert _is_not_running_phase("Pending") is True
        assert _is_not_running_phase("Succeeded") is True

    def test_is_active_phase(self):
        assert _is_active_phase("Running") is True
        assert _is_active_phase("Pending") is True
        assert _is_active_phase("Succeeded") is False
        assert _is_active_phase("Failed") is False

    def test_is_terminated_phase(self):
        assert _is_terminated_phase("Succeeded") is True
        assert _is_terminated_phase("Failed") is True
        assert _is_terminated_phase("Running") is False
        assert _is_terminated_phase("Pending") is False

    def test_is_not_terminated_phase(self):
        assert _is_not_terminated_phase("Running") is True
        assert _is_not_terminated_phase("Pending") is True
        assert _is_not_terminated_phase("Succeeded") is False
        assert _is_not_terminated_phase("Failed") is False


class TestAllExports:
    """Test that __all__ exports are correct."""

    def test_all_exports(self):
        from scitrera_app_framework.k8s.util import __all__

        expected = (
            'apply_yaml_object', 'start_pod', 'is_pod_running', 'is_pod_in_terminated_state',
            'pod_exists', 'get_pod_env', 'get_metadata_name', 'get_metadata_namespace',
            'get_headless_service_dns_name_for_pod', 'merge_env_vars', 'fixed_env_vars',
            'parse_yaml',
        )

        for name in expected:
            assert name in __all__
