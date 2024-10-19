from __future__ import annotations

from logging import Logger
from typing import Type, Iterable

from ..api import Variables, Plugin
from .core import _get_default_vars_instance, get_logger


def _plugin_registry(v: Variables = None) -> Variables:
    return v.get_or_set('=|PR|', default_fn=Variables)


def _extension_registry(v: Variables = None) -> dict:
    return v.get_or_set('=|ER|', default_fn=dict)


def _extension_options(ext_name: str, v: Variables = None) -> set[Plugin]:
    # EOR = Extension Options Registry
    return v.get_or_set('=|EOR|', default_fn=Variables).get_or_set(ext_name, default_fn=set)


def _find_plugin_for_ext(ext_name: str, v: Variables = None):
    # if already initialized and registered, just return that plugin
    er = _extension_registry(v)
    if ext_name in er:
        plugin, value = er[ext_name]
        return plugin, value

    # if not ready, then we need to scan through the options and see if we can find a candidate
    options = _extension_options(ext_name, v=v)
    for opt in options:
        if opt.is_enabled(v):  # TODO: conflict detection
            return opt, None

    return None, None


def _init_plugin(name, v: Variables = None, _requested_by=None, _now=False):
    if v is None:
        v = _get_default_vars_instance()
    pr = _plugin_registry(v)
    plugin = pr.get(name, local=True)  # type: Plugin
    if plugin is None:
        raise ValueError(f'unable to find plugin: {name}')

    # prep extension point information
    er = _extension_registry(v)
    ext_name = plugin.extension_point_name(v)

    # TODO: we could manage plugin initialized record-keeping outside of the plugin / in a more private/safe space...
    if plugin.collected:  # return extension point registry result if plugin is marked as initialized
        return er[ext_name]  # TODO: this is kinda flawed either (1) should just search ER or (2) plugin doesn't have to match ext point

    if not plugin.is_enabled(v):  # abort init of this plugin if it is disabled
        return

    # maintain expanding set of upstream extension point requests
    if _requested_by is None:
        _requested_by = {ext_name}
    else:
        _requested_by = _requested_by.copy()
        _requested_by.add(ext_name)

    # setup logger and announce (debug)
    logger = get_logger(v)  # TODO: decide logger context/name (and levels)

    # go through dependencies and try to initialize them as needed
    deps = plugin.get_dependencies(v)
    for dep in deps:
        dep_plugin, _ = _find_plugin_for_ext(dep, v)
        if not dep_plugin:
            raise ValueError(f'unable to find registered plugin for extension point: {dep}')
        elif dep in _requested_by:
            raise ValueError(f'circular dependency "{dep}" encountered while trying to init {name}; history={_requested_by}')
        logger.debug('Processing dependency "%s" for extension point "%s"', dep, ext_name)
        _init_plugin(dep_plugin.name(), v, _requested_by=_requested_by)

    # check for ER conflict
    if ext_name in er:
        existing_plugin, existing_result = er[ext_name]  # type: Plugin, object
        raise ValueError(f'duplicated hit on extension point "{ext_name}"; '
                         f'write attempted by {name} by already taken by {existing_plugin.name()}')

    # now we initialize the requested plugin
    plugin.collected = True
    if plugin.eager or _now:  # if the plugin is eager... or we need it NOW, then make sure we initialize
        logger.debug('initializing plugin "%s" for extension point "%s"', name, ext_name)
        value = plugin.initialize(v, plugin.get_logger(v))
        plugin.initialized = True
    else:
        value = None

    # commit to extension point registry
    er[ext_name] = result = (plugin, value)
    pr.get_or_set('=|STARTUP_ORDER|', default_fn=list).append(plugin)

    return result


def shutdown_all_plugins(v: Variables = None):
    if v is None:
        v = _get_default_vars_instance()

    pr = _plugin_registry(v)
    er = _extension_registry(v)
    logger = get_logger(v)
    for plugin in reversed(pr.get_or_set('=|STARTUP_ORDER|', default_fn=list)):  # type: Plugin
        if plugin.initialized:
            try:
                _, value = er[plugin.extension_point_name(v)]
                plugin.shutdown(v, plugin.get_logger(v), value)
            except Exception as e:
                logger.warning('Exception while shutting down plugin "%s" at extension point "%s": %s',
                               plugin.name(), plugin.extension_point_name(v), e)

    return


def register_plugin(plugin_type: Type[Plugin], v: Variables = None, init=False):
    if v is None:
        v = _get_default_vars_instance()
    pr = _plugin_registry(v)
    instance = plugin_type()
    if (name := instance.name()) not in pr:
        get_logger(v).debug('Registering plugin: "%s" for extension point "%s"', name, instance.extension_point_name(v))
        pr[name] = instance
        _extension_options(instance.extension_point_name(v), v=v).add(instance)
    elif (existing := pr.get(name)) is not None and not isinstance(existing, plugin_type):
        raise ValueError(f'Duplicate plugin name with different implementation: {name}, {type(existing)} vs {plugin_type}')

    if init:
        _init_plugin(instance.name(), v)

    return instance


def get_extension(extension_point: str | Type[Plugin], v: Variables = None):
    if v is None:
        v = _get_default_vars_instance()

    if isinstance(extension_point, type) and issubclass(extension_point, Plugin):
        instance = register_plugin(extension_point, init=True)
        extension_point = instance.extension_point_name(v)
    elif not isinstance(extension_point, str):
        raise ValueError(f'unable to determine extension point with given input: {extension_point}')

    er = _extension_registry(v)
    hit = er.get(extension_point)  # type: tuple[Plugin, object|None]
    if hit is None and ((hit := _find_plugin_for_ext(extension_point, v))[0] is None):
        raise ValueError(f'unknown extension point: {extension_point}')

    plugin, value = hit
    if value is None and not plugin.initialized:
        hit = _init_plugin(plugin.name(), v, _now=True)

    plugin, value = hit
    return value


def init_all_plugins(v: Variables = None):
    if v is None:
        v = _get_default_vars_instance()
    pr = _plugin_registry(v)
    for name in pr.keys():
        _init_plugin(name, v=v)
    return


def set_extension(extension_point: str, init_fn, shutdown_fn=None, dependencies=None, v: Variables = None):
    """
    This function is used to bypass the need to write Plugin types by minimally providing
    an extension point and an initialization function.

    :param extension_point: extension point name
    :param init_fn: no-arg callable function that initialize the extension point, should return object to populate
    the extension point (if it doesn't run a loop or some other continuous activity)
    :param shutdown_fn: optional no-arg callable function to be called on shutdown
    :param dependencies: optional list of required extension points
    :param v: the variables/environment instance
    :return:
    """

    # noinspection PyShadowingNames
    class FacadePlugin(Plugin):
        eager = False

        def name(self) -> str:
            return f'SetExtension|{extension_point}|'

        def extension_point_name(self, v: Variables) -> str:
            return extension_point

        def get_dependencies(self, v: Variables) -> Iterable[str] | None:
            return dependencies or ()

        def initialize(self, v: Variables, logger: Logger) -> object | None:
            return init_fn()

        def shutdown(self, v: Variables, logger: Logger, value: object | None) -> None:
            if shutdown_fn is not None:
                return shutdown_fn()

    if v is None:
        v = _get_default_vars_instance()
    return register_plugin(FacadePlugin, v)
