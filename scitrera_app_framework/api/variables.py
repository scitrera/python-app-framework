from __future__ import annotations

from os import environ
from typing import Callable, Any, Set


class EnvironProxy(object):

    def __getitem__(self, item: str):
        return environ[item.upper()]

    def __contains__(self, item: str):
        return item.upper() in environ

    pass


_environment = EnvironProxy()
NO_MATCH = object()
NOT_SET = NO_MATCH


class Variables(object):
    _local = None
    _env_defaults = None
    _type_fns = None
    _sources = None

    def __init__(self, sources=()):
        """
        Instantiate a Variables instance to act as the centerpiece of coordinating application
        components. Realistically, this should be called "Environment" or something, but way-back-when,
        it was called Variables to act as a container for environment variables plus--and that stuck.

        :param sources: optional iterable of sources to search for variables (i.e., for a multi-tier key-value store)
        """
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

    def environ(self, key: str, default: Any = NOT_SET, type_fn: Callable = None):
        """
        Get value using a key/environment variable name. If a default is provided, that default will be registered. If a type_fn is
        provided, that type_fn will be called whenever getting that key.

        :param key: the string key or environment variable name to get. Note that the default implementation will check the environment
                    for key.upper()--so using lower case keys internally but falling back to equivalent keys in environment but with
                    all upper case names should work fine.
        :param default: the default value to use if the key does not exist. This is registered within the Variables object such that
                        future calls to get, __getitem__, or this function will use that default value. None will ultimately be returned
                        if there is no default configured.
        :param type_fn: a type function (single arg function that takes the raw value/environment value string as an input) and returns the
                        desired target. Examples: int, float, ext_parse_bool, ext_parse_csv, ext_get_python, etc.
        :return: the value or default if key is otherwise not defined anywhere in the available sources
        """
        if default is not NOT_SET:  # use NO_MATCH/NOT_SET to allow None as a default value
            self._env_defaults[key] = default
        if type_fn is not None:
            self._type_fns[key] = type_fn

        # keep a record of encountered keys...
        self._keys.add(key)

        return self[key]

    def __getitem__(self, key: str, default: Any = None, local: bool = False):
        """
        Get a key from the available sources. If there is no match but the key exists in the environment as key.upper(), then
        the environment variable value will be returned (wrapped by type_fn if specified). Otherwise, the defined default will
        be returned.  If there is no defined default, the result will be None unless otherwise specified [like dict.get(key, default=None)].

        :param key: the key or environment variable name to fetch
        :param default: the default value to use if key is otherwise not defined anywhere and there is no other default value configured.
        :param local: only search explicitly defined values and do not fall back to other sources (environment, configured defaults, etc.)
        :return: the value or default if key is otherwise not defined anywhere in the available sources
        """
        # TODO: potentially switch to using vpd.simple search_tree? [may require augmenting vpd.simple search_tree to be more flexible...]
        match = NO_MATCH
        if local:
            match = self._local.get(key, NO_MATCH)
        else:
            for source in self._sources:
                if key in source:
                    match = source[key]
                    break

        if match is not NO_MATCH:
            # if key not in self._keys:  # TODO: should any item that we retrieve should be considered part of us?
            #     self._keys.add(key)
            type_fn = self._type_fns.get(key, None)
            if type_fn is not None:
                return type_fn(match)
            return match

        return default  # TODO: or should we raise exception like dict.__getitem__

    __getattr__ = __getitem__
    get = __getitem__

    def import_from_env_by_prefix(self, prefix: str, sep: str = '_', drop_prefix=True, prefix_lower=False, key_lower=True) \
            -> dict[str, Any]:
        """
        Import values from the process environment into the local Variables instance if the environment variable names start with the
        given prefix and given separator. The default separator is underscore ("_"). The output of this function will be a call to
        `get_by_prefix` that will return a dict of values that match the prefix. The default settings are intended to make it relatively
        straightforward to "namespace" environment variables into groups for different purposes within the application--and then
        import them to act as kwargs, etc. for configuration.

        Example Environment Variables:

        APP1_NAME="Widgetizer"
        APP1_V1AX="SomethingV1AXLike"
        APP1_W222="WOW"
        APP2_NVER="MORE"

        >>> v = Variables()
        >>> hits = v.import_from_env_by_prefix('APP1')
        >>> print(hits)
            {'name':"Widgetizer", 'v1ax': "SomethingV1AXLike", 'w222': "WOW"}

        :param prefix: the environment variable prefix to base our search.
        :param sep: the default separator that follows the prefix. It will be part of the lookup, so it does matter.
        :param drop_prefix: whether the prefix should be dropped from the keys of the resulting dict. This does not affect
                            importing the values.
        :param prefix_lower: whether the prefix should be lowercased before searching the Variables instance. (Only related to output
                             and does not affect importing values).
        :param key_lower: whether the resulting key in the results dict should be lowercased. The default is True. (Only related
                          to output and does not affect importing values).
        :return: dict of values whose keys match the given prefix
        """
        se = self.environ
        ps = f'{prefix}{sep}'
        _ = {k: se(k) for k in environ.keys() if k.startswith(ps)}
        return self.get_by_prefix(prefix, sep, drop_prefix, prefix_lower, key_lower)

    def import_from_dict_by_prefix(self, prefix: str, source: dict, sep='_', drop_prefix=True, prefix_lower=False, key_lower=True) \
            -> dict[str, Any]:
        """
        This is the equivalent function to `import_from_env_by_prefix` except that it takes a dict source rather than falling back
        to environment values. This function internally works by configuring the values in the given source dict as the fallback
        defaults rather than setting the values directly--so it does effectively set the values if not set otherwise... however,
        environment variables would still act to override these values!

        :param prefix: the key prefix to base our search.
        :param source: a source dict from which to pull values. If empty or None, then this function just passes through to `get_by_prefix`.
        :param sep: the default separator that follows the prefix. It will be part of the lookup, so it does matter.
        :param drop_prefix: whether the prefix should be dropped from the keys of the resulting dict. This does not affect
                            importing the values.
        :param prefix_lower: whether the prefix should be lowercased before searching the Variables instance. (Only related to output
                             and does not affect importing values).
        :param key_lower: whether the resulting key in the results dict should be lowercased. The default is True. (Only related
                          to output and does not affect importing values).
        :return: dict of values whose keys match the given prefix
        """
        if not source:
            return self.get_by_prefix(prefix, sep, drop_prefix)

        se = self.environ
        ps = f'{prefix}{sep}'
        _ = {k: se(k, default=v) for k, v in source.items() if k.startswith(ps)}
        return self.get_by_prefix(prefix, sep, drop_prefix, prefix_lower, key_lower)

    def get_by_prefix(self, prefix: str, sep='_', drop_prefix=True, prefix_lower=False, key_lower=True) -> dict[str, Any]:
        """
        Get a subset of values from this Variables instance that match the given prefix and separator. The default settings
        will drop the prefix and lowercase the resulting dict keys. This is intended to make it straightforward to create
        kwargs inputs to classes and functions for configuration via "namespaced" environment variables.

        :param prefix: the key prefix to base our search.
        :param sep: the default separator that follows the prefix. It will be part of the lookup, so it does matter.
        :param drop_prefix: whether the prefix should be dropped from the keys of the resulting dict.
        :param prefix_lower: whether the prefix should be lowercased before searching the Variables instance.
        :param key_lower: whether the resulting key in the results dict should be lowercased. The default is True.
        :return: dict of values whose keys match the given prefix
        """
        get = self.get
        effective_prefix = prefix.lower() if prefix_lower else prefix
        ps = f'{effective_prefix}{sep}'

        def key_filter(k: str):
            key = k
            if drop_prefix:
                key = key.removeprefix(ps)
            if key_lower:
                key = key.lower()
            return key

        return {key_filter(k): get(k) for k in self._keys if k.startswith(ps)}

    def set_type_fn(self, key: str, type_fn: Callable):
        """
        Configure a type function for a given key

        :param key: the key or environment variable name for which you wish to define a type function
        :param type_fn: a type function that takes the raw value/environment value string as an input
        """
        self._type_fns[key] = type_fn
        return

    def set_default_value(self, key: str, default: Any):
        """
        Configure a default value for a given key

        :param key: the key or environment variable name for which you wish to define a default value
        :param default: the default value to use if key is otherwise not defined anywhere in the available sources
        """
        self._env_defaults[key] = default
        return

    def set_type_default(self, key: str, default: Any = NOT_SET, type_fn: Callable = NOT_SET):
        """
        (Optionally) configure default and type function for a given key. This is just meant to reduce the number of
        function calls by combining the functionality of `set_type_fn` and `set_default_value`.

        :param key: the key or environment variable name
        :param default: the default value to use if key is otherwise not defined anywhere in the available sources
        :param type_fn: a type function that takes the raw value/environment value string as an input and coerces it to the correct type
        """
        if default is not NOT_SET:
            self._env_defaults[key] = default
        if type_fn is not NOT_SET:
            self._type_fns[key] = type_fn
        return

    def set(self, key: str, value):
        """
        Explicitly set a key-value pair for this Variables instance

        :param key: the key to set
        :param value: the value to set
        """
        self._local[key] = value
        self._keys.add(key)
        return value

    def update(self, dict_values: dict = None, **kwargs):
        """
        Set many key-value pairs for this Variables instance.

        :param dict_values: a dict of key-value pairs to set. Note that any values in dict_values will override kwargs.
        :param kwargs: key-value pairs provided as kwargs
        """
        if dict_values:
            kwargs.update(dict_values)
        for k, v in kwargs.items():
            self[k] = v

    def __setitem__(self, key: str, value):
        self._local[key] = value
        self._keys.add(key)
        return

    def __contains__(self, key: str) -> bool:
        return key in self._keys or key in _environment

    def keys(self) -> Set[str]:
        """ Get a copy of the identified keys in this Variables instance. """
        return self._keys.copy()

    def get_or_set(self, key: str, value_fn: callable) -> Any:
        """
        Convenience function to cover a common pattern. This function searches the LOCAL data for the given key
        and will populate it by calling the provided no-arg value_fn if it does not exist in the local data.
        This is most often used as an optional/failsafe set function to configure a local value if it is not already set
        but otherwise not overwriting the value.

        :param key: the key to get or set
        :param value_fn: a no-arg function that will be called to provide a value if the key is not found
        :return: the value of the local key (either because it already existed or because we set it to a new value)
        """
        mapping = self._local
        if key in mapping:
            return mapping[key]
        mapping[key] = result = value_fn()
        return result

    def get_or_set_default(self, key: str, value_fn: callable) -> Any:
        """
        Convenience function to cover a common pattern. This function searches the DEFAULTS data for the given key
        and will populate it by calling the provided no-arg value_fn if it does not exist in the DEFAULTS data.
        This is most often used as an optional/failsafe set function to configure a default value if it is not already set
        but otherwise not overwriting an existing default value.

        :param key: the key to get or set
        :param value_fn: a no-arg function that will be called to provide a value if the key is not found
        :return: the value of the DEFAULT key (either because it already existed or because we set it to a new value)
        """
        mapping = self._env_defaults
        if key in mapping:
            return mapping[key]
        mapping[key] = result = value_fn()
        return result

    def add_source(self, src: "Variables" | dict):
        """
        Add another source for possible key-value pair matches to this Variables instance. `src` is expected
        to either be another Variables instance or a dict (technically it can be anything that implements
        __contains__ and get(key, default) functions--so it's even possible for the source to be files, remote, database, etc.).

        The additional source will be added as 2nd to last to search. The last source is always the configured fallback default values.

        :param src: the additional source to search.
        """
        # add new sources to the end of the list but before env_defaults fallback
        self._sources.insert(len(self._sources) - 1, src)
        return

    def export_all_variables(self) -> dict[str, Any]:
        """
        Export all identified/declared keys from this instance to a dict
        """
        return {k: self.__getitem__(k) for k in self._keys}

    pass
