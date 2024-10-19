from __future__ import annotations

from os import environ
from typing import Callable, Any


class EnvironProxy(object):

    def __getitem__(self, item):
        return environ[item.upper()]

    def __contains__(self, item):
        return item.upper() in environ

    pass


_environment = EnvironProxy()
_no_match = object()


class Variables2(object):
    _local = None
    _env_defaults = None
    _type_fns = None
    _sources = None

    def __init__(self, sources=()):
        self._local = {}  # type: dict[str, Any]
        self._env_defaults = {}  # type: dict[str, Any]
        self._type_fns = {}  # type: dict[str, Callable]
        self._keys = set()  # type: set[str]
        self._sources = (
                [_environment,  # we prioritize env variables
                 self._local,  # then we fall back to local settings to act as configurable defaults
                 ] + list(sources) +  # then given other sources
                [self._env_defaults, ]  # falling back to general defaults
        )

    def environ(self, key: str, environment_variable: str = None, default=None, type_fn: Callable = None):
        if environment_variable:  # if provided, environment variable is authoritative as key; we're transitioning away from old convention
            key = environment_variable
        # TODO: consider if we want to force case conventions or make lookups case insensitive? for now, leave case up to developer
        # if environment_variable:  # enforce that keys should be equal to lower-case variant of environment variables
        #     key = environment_variable.lower()
        # elif key:  # enforce keys are lowercase
        #     key = key.lower()

        if default is not None:
            self._env_defaults[key] = default
        if type_fn is not None:
            self._type_fns[key] = type_fn

        # keep a record of encountered keys...
        self._keys.add(key)

        return self.__getitem__(key)

    def set_type_fn(self, key: str, type_fn: Callable):
        self._type_fns[key] = type_fn
        return

    def __getitem__(self, key: str, local=False):
        match = _no_match
        if local:
            match = self._local.get(key, _no_match)
        else:
            for source in self._sources:
                if key in source:
                    match = source[key]
                    break

        if match is not _no_match:
            type_fn = self._type_fns.get(match, None)
            if type_fn is not None:
                return type_fn(match)
            return match

        return None  # TODO: or should we raise exception like dict.__getitem__

    __getattr__ = __getitem__
    get = __getitem__

    def import_from_env_by_prefix(self, prefix: str, sep='_', drop_prefix=True):
        """

        :param prefix:
        :param sep:
        :param drop_prefix:
        :return:
        """
        se = self.environ
        ps = f'{prefix}{sep}'
        _ = {k: se(k) for k in environ.keys() if k.startswith(ps)}
        return self.get_by_prefix(prefix, sep, drop_prefix)

    def import_from_dict_by_prefix(self, prefix: str, source: dict, sep='_', drop_prefix=True):
        """

        :param prefix:
        :param source:
        :param sep:
        :param drop_prefix:
        :return:
        """
        if not source:
            return self.get_by_prefix(prefix, sep, drop_prefix)

        se = self.environ
        ps = f'{prefix}{sep}'
        _ = {k: se(k, default=v) for k, v in source.items() if k.startswith(ps)}
        return self.get_by_prefix(prefix, sep, drop_prefix)

    def get_by_prefix(self, prefix: str, sep='_', drop_prefix=True, prefix_lower=True):
        get = self.get
        effective_prefix = prefix.lower() if prefix_lower else prefix
        ps = f'{effective_prefix}{sep}'

        def key_filter(k: str):
            if not drop_prefix:
                return k
            return k.removeprefix(ps)

        return {key_filter(k): get(k) for k in self._keys if k.startswith(ps)}

    def set(self, key: str, value):
        self._local[key] = value
        self._keys.add(key)
        return value

    def update(self, dict_values: dict = None, **kwargs):
        if dict_values:
            kwargs.update(dict_values)
        for k, v in kwargs.items():
            self[k] = v

    def __setitem__(self, key, value):
        # key = key.lower()
        self._local[key] = value
        self._keys.add(key)

    def __contains__(self, key):
        key = key.lower()
        return key in self._keys or key in _environment

    def keys(self):
        return self._keys.copy()

    def get_or_set(self, key, default_fn):
        mapping = self._local
        if key in mapping:
            return mapping[key]
        mapping[key] = result = default_fn()
        return result

    def add_source(self, src: "Variables2" | dict):
        self._sources.append(src)
        return

    def export_all_variables(self):
        return {k: self.__getitem__(k) for k in self._keys}

    pass
