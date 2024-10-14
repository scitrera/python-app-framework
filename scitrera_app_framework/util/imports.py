import pkgutil
import importlib


def import_modules(package_name, recursive=True):
    package = importlib.import_module(package_name)
    package_path = package.__path__

    for _, module_name, is_pkg in pkgutil.iter_modules(package_path):
        full_module_name = f"{package_name}.{module_name}"
        yield importlib.import_module(full_module_name)
        if is_pkg and recursive:
            yield from import_modules(full_module_name)

    return


def find_types_in_modules(package_name, base_type, recursive=True, exclude_base_type=True):
    history = set()
    for module in import_modules(package_name, recursive=recursive):
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and issubclass(attr, base_type) and attr not in history
                    and not (exclude_base_type and attr is base_type)):
                yield attr
                history.add(attr)

    return


def get_python_type_by_name(type_name, expected_parent_type):  # TODO: move upstream?
    if not type_name:
        raise ValueError('Invalid type_name')

    # TODO: better to handle errors or to just not and let them bubble up naturally
    parts = type_name.split('.')
    pkg = '.'.join(parts[:-1])
    name = parts[-1]

    pkg = importlib.import_module(pkg)
    strategy_type = getattr(pkg, name)
    if issubclass(strategy_type, expected_parent_type):
        return strategy_type

    raise ValueError('given type name does not match expected type')
