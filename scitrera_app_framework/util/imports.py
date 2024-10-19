from __future__ import annotations

import importlib
import importlib.util
import inspect
import pathlib
import pkgutil

from types import ModuleType
from typing import Optional, Generator, Type, Any


def import_modules(package_name: str, recursive: bool = True) -> Generator[ModuleType]:
    """
    Import all modules from a given package and optionally do so recursively for subpackages.

    :param package_name: The name of the package to import modules from.
    :param recursive: If True, recursively import subpackages and their modules.
    :return: A generator that yields imported modules.
    :raises ModuleNotFoundError: If the specified package cannot be found.
    :raises ImportError: If there is an issue importing any module.
    """
    try:
        # Import the base package
        package = importlib.import_module(package_name)
    except ModuleNotFoundError:
        raise ModuleNotFoundError(f"Package '{package_name}' not found")

    # Check if the imported item is a package (not a regular module)
    if not hasattr(package, '__path__'):
        raise ValueError(f"'{package_name}' is not a package")

    package_path = package.__path__

    # Iterate through the modules in the package
    for _, module_name, is_pkg in pkgutil.iter_modules(package_path):
        full_module_name = f"{package_name}.{module_name}"

        try:
            # Import the module and yield it
            yield importlib.import_module(full_module_name)
        except ImportError as e:
            raise ImportError(f"Error importing module '{full_module_name}'") from e

        # If the module is a package and recursive is True, import submodules recursively
        if is_pkg and recursive:
            yield from import_modules(full_module_name, recursive=recursive)

    return


def find_types_in_modules(package_name: str,
                          base_type: Type,
                          recursive: bool = True,
                          exclude_base_type: bool = True,
                          exclude_abstract: bool = True) -> Generator[Type]:
    """
    Find all classes (types) in the given package and its submodules that are subclasses of the given base_type.

    :param package_name: The name of the package to search for types.
    :param base_type: The base type or class to match subclasses against.
    :param recursive: If True, search recursively through submodules.
    :param exclude_base_type: If True, exclude the base_type itself from the results.
    :param exclude_abstract: If True, exclude abstract base classes from the results.
    :return: A generator that yields subclasses of base_type found in the modules.
    """
    history = set()

    # Iterate over modules in the package, with recursion if enabled
    for module in import_modules(package_name, recursive=recursive):
        # Loop through each attribute in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            # Check if the attribute is a class, is a subclass of base_type, and meets the filtering conditions
            if (inspect.isclass(attr) and issubclass(attr, base_type) and
                    not (exclude_abstract and inspect.isabstract(attr)) and
                    not (exclude_base_type and attr is base_type) and
                    attr not in history):
                yield attr
                history.add(attr)

    return


def get_python_type_by_name(type_name: str, expected_parent_type: Type[Any]) -> Type[Any]:
    """
    Retrieve a Python class/type by its fully qualified name and ensure it is a subclass of the expected parent type.

    :param type_name: The fully qualified name of the type (e.g., 'module.submodule.ClassName').
    :param expected_parent_type: The type or class that the retrieved type must inherit from.
    :return: The retrieved type if found and validated.
    :raises ValueError: If the type_name is invalid or the type is not a subclass of expected_parent_type.
    :raises ModuleNotFoundError: If the specified module cannot be imported.
    :raises AttributeError: If the type name cannot be found within the module.
    """
    if not type_name:
        raise ValueError('Invalid type_name provided')

    parts = type_name.split('.')
    if len(parts) < 2:
        raise ValueError('type_name must be in the format "module.submodule.ClassName"')

    module_name = '.'.join(parts[:-1])
    class_name = parts[-1]

    try:
        # Import the module
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ModuleNotFoundError(f"Could not import module '{module_name}'") from e

    try:
        # Retrieve the class/type from the module
        retrieved_type = getattr(module, class_name)
    except AttributeError as e:
        raise AttributeError(f"Type '{class_name}' not found in module '{module_name}'") from e

    # Ensure the retrieved type is a subclass of expected_parent_type
    if not issubclass(retrieved_type, expected_parent_type):
        raise TypeError(f"Retrieved type '{class_name}' is not a subclass of {expected_parent_type.__name__}")

    return retrieved_type


def path_for_module(module_name: str, try_import=True, raise_exceptions=True) -> Optional[pathlib.Path]:
    """
    Return the path associated with a given Python package/module if it exists.

    :param module_name: string name of Python package/module
    :param try_import: whether to try to import the module if it isn't already in the current Python interpreter
    :param raise_exceptions: whether to raise exceptions on failures or return None
    :return: path for Python package/module or None if not found and raise_exceptions=False
    """
    spec = importlib.util.find_spec(module_name)
    if spec and spec.origin:
        return pathlib.Path(spec.origin).parent
    elif try_import:
        try:
            importlib.import_module(module_name)
            return path_for_module(module_name, try_import=False, raise_exceptions=raise_exceptions)
        except ImportError:
            if raise_exceptions:
                raise ModuleNotFoundError(f"Module '{module_name}' not found or failed to import")
    elif raise_exceptions:
        raise ModuleNotFoundError(f"Module '{module_name}' not found")
    return None
