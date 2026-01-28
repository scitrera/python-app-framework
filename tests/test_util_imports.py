"""
Tests for scitrera_app_framework.util.imports module.
"""
import pathlib
import pytest
from scitrera_app_framework.util.imports import (
    _split_module_name,
    path_for_module,
    get_python_type_by_name,
    ext_get_python,
    import_modules,
    find_types_in_modules,
)


class TestSplitModuleName:
    """Tests for _split_module_name function."""

    def test_simple_module_name(self):
        module, name = _split_module_name("os.path")
        assert module == "os"
        assert name == "path"

    def test_deep_module_name(self):
        module, name = _split_module_name("scitrera_app_framework.api.variables.Variables")
        assert module == "scitrera_app_framework.api.variables"
        assert name == "Variables"

    def test_empty_ref_raises(self):
        with pytest.raises(ValueError, match="Invalid ref"):
            _split_module_name("")

    def test_none_ref_raises(self):
        with pytest.raises(ValueError, match="Invalid ref"):
            _split_module_name(None)

    def test_single_part_raises(self):
        with pytest.raises(ValueError, match="must be in the format"):
            _split_module_name("single")


class TestPathForModule:
    """Tests for path_for_module function."""

    def test_existing_module(self):
        result = path_for_module("scitrera_app_framework")
        assert result is not None
        assert isinstance(result, pathlib.Path)
        assert result.exists()

    def test_existing_submodule(self):
        result = path_for_module("scitrera_app_framework.api")
        assert result is not None
        assert isinstance(result, pathlib.Path)

    def test_nonexistent_module_raises(self):
        with pytest.raises(ModuleNotFoundError):
            path_for_module("nonexistent_module_xyz123")

    def test_nonexistent_module_returns_none(self):
        result = path_for_module("nonexistent_module_xyz123", raise_exceptions=False)
        assert result is None

    def test_stdlib_module(self):
        result = path_for_module("json")
        assert result is not None
        assert isinstance(result, pathlib.Path)


class TestGetPythonTypeByName:
    """Tests for get_python_type_by_name function."""

    def test_get_existing_type(self):
        from scitrera_app_framework.api import Variables
        result = get_python_type_by_name(
            "scitrera_app_framework.api.variables.Variables",
            object
        )
        assert result is Variables

    def test_validates_parent_type(self):
        from scitrera_app_framework.api import Plugin
        # Variables is not a subclass of Plugin
        with pytest.raises(TypeError, match="not a subclass"):
            get_python_type_by_name(
                "scitrera_app_framework.api.variables.Variables",
                Plugin
            )

    def test_nonexistent_module_raises(self):
        with pytest.raises(ModuleNotFoundError):
            get_python_type_by_name("nonexistent.Module", object)

    def test_nonexistent_type_raises(self):
        with pytest.raises(AttributeError):
            get_python_type_by_name("scitrera_app_framework.api.NonexistentClass", object)


class TestExtGetPython:
    """Tests for ext_get_python function."""

    def test_get_function(self):
        result = ext_get_python("scitrera_app_framework.util.misc.now_ms")
        from scitrera_app_framework.util.misc import now_ms
        assert result is now_ms

    def test_get_class(self):
        result = ext_get_python("scitrera_app_framework.api.variables.Variables")
        from scitrera_app_framework.api.variables import Variables
        assert result is Variables

    def test_get_constant(self):
        result = ext_get_python("scitrera_app_framework.api.variables.NOT_SET")
        from scitrera_app_framework.api.variables import NOT_SET
        assert result is NOT_SET

    def test_invalid_ref_raises(self):
        with pytest.raises(ValueError):
            ext_get_python("invalid")

    def test_nonexistent_module_raises(self):
        with pytest.raises(ModuleNotFoundError):
            ext_get_python("nonexistent_module.function")


class TestImportModules:
    """Tests for import_modules function."""

    def test_import_package_modules(self):
        modules = list(import_modules("scitrera_app_framework.util", recursive=False))
        module_names = [m.__name__ for m in modules]

        assert "scitrera_app_framework.util.misc" in module_names
        assert "scitrera_app_framework.util.parsing" in module_names
        assert "scitrera_app_framework.util.imports" in module_names

    def test_nonexistent_package_raises(self):
        with pytest.raises(ModuleNotFoundError):
            list(import_modules("nonexistent_package_xyz"))

    def test_module_not_package_raises(self):
        with pytest.raises(ValueError, match="is not a package"):
            list(import_modules("scitrera_app_framework.util.misc"))


class TestFindTypesInModules:
    """Tests for find_types_in_modules function."""

    def test_find_plugin_subclasses(self):
        from scitrera_app_framework.api import Plugin

        plugins = list(find_types_in_modules(
            "scitrera_app_framework.base_plugins",
            Plugin,
            recursive=False
        ))

        plugin_names = [p.__name__ for p in plugins]
        assert "BackgroundThreadExecutorPlugin" in plugin_names
        assert "ProgressTrackerPlugin" in plugin_names

    def test_excludes_base_type_by_default(self):
        from scitrera_app_framework.api import Plugin

        plugins = list(find_types_in_modules(
            "scitrera_app_framework.base_plugins",
            Plugin,
            exclude_base_type=True
        ))

        assert Plugin not in plugins

    def test_includes_base_type_when_requested(self):
        from scitrera_app_framework.api import Plugin

        # Find in a module that imports Plugin
        types_found = list(find_types_in_modules(
            "scitrera_app_framework.api",
            Plugin,
            exclude_base_type=False,
            recursive=False
        ))

        assert Plugin in types_found
