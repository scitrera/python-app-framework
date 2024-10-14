from os import getenv, environ
from typing import Callable, Optional


class Variables(object):
    _mapping = None

    def __init__(self, ):  # logger):
        self._mapping = {}
        # self.logger = logger

    def environ(self, key: str, environment_variable: str = None, default=None, type_fn: Callable = None):
        if environment_variable is None:
            environment_variable = key
        mapping = self._mapping
        mapping[key] = (environment_variable, default, type_fn)
        result = self.__getitem__(key)
        # self.logger.info('[CONFIG][ENV] %s = %s', key, result)
        return result

    def import_from_env_by_prefix(self, prefix: str, sep='_', drop_prefix=True):
        """

        :param prefix:
        :param sep:
        :param drop_prefix:
        :return:
        """
        se = self.environ
        ps = f'{prefix}{sep}'
        _ = {k.lower(): se(k.lower(), environment_variable=k) for k in environ.keys() if k.startswith(ps)}
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
        _ = {k.lower(): se(k.lower(), environment_variable=k, default=v) for k, v in source.items() if k.startswith(ps)}
        return self.get_by_prefix(prefix, sep, drop_prefix)

    def get_by_prefix(self, prefix: str, sep='_', drop_prefix=True, prefix_lower=True):
        get = self.get
        effective_prefix = prefix.lower() if prefix_lower else prefix
        ps = f'{effective_prefix}{sep}'

        def key_filter(k: str):
            if not drop_prefix:
                return k
            return k.removeprefix(ps)

        return {key_filter(k): get(k) for k in self._mapping.keys() if k.startswith(ps)}

    def set(self, key: str, value):
        self._mapping[key] = (None, value, None)
        return value

    # def save(self, key: str, value):
    #     self._mapping[key] = (None, value, None)
    #     return value

    def __setitem__(self, key, value):
        self._mapping[key] = (None, value, None)

    def __contains__(self, item):
        return item in self._mapping

    def __getitem__(self, key):
        env_var, default, type_fn = self._mapping.get(key, (None, None, None))  # type: Optional[str, str, Callable]
        if env_var is None:
            return default
        result = getenv(env_var, default)
        if callable(type_fn):
            return type_fn(result)
        return result

    __getattr__ = __getitem__
    get = __getitem__

    def keys(self):
        return self._mapping.keys()

    def get_or_set(self, key, default_fn):
        mapping = self._mapping
        if key in mapping:
            return mapping[key]
        mapping[key] = result = default_fn()
        return result

    def export_all_variables(self):
        return {k: self.__getitem__(k) for k in self._mapping.keys()}

    pass
