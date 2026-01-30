from __future__ import annotations

import asyncio
import threading
from logging import Logger
from typing import Type, Iterable, Any, Optional

from ..api import Variables, Plugin
from .core import _get_default_vars_instance, get_logger

_VAR_ASYNC_LOOP = '=|async_loop|'
_VAR_ASYNC_LOOP_THREAD = '=|async_loop_thread|'

_NOT_INIT = object()


def _plugin_registry(v: Variables = None) -> Variables:
    return v.get_or_set('=|PR|', value_fn=Variables)


def _impl_registry(v: Variables = None) -> dict:
    # IR = Implementations Registry (formerly Extensions Registry)
    return v.get_or_set('=|IR|', value_fn=dict)


def _impl_options(ext_name: str, v: Variables = None) -> set[Plugin]:  # TODO: without hash/eq, sets for plugins sorta makes no sense
    # EIR = Extension Implementations Registry
    return v.get_or_set('=|EIR|', value_fn=Variables).get_or_set(ext_name, value_fn=set)


def _multi_ext_options(ext_name: str, v: Variables = None) -> dict[str, list[Any]]:
    # EOR = Extension Options Registry
    return v.get_or_set('=|EOR|', value_fn=Variables).get_or_set(ext_name, value_fn=dict)


def _find_plugin_for_single_ext(ext_name: str, v: Variables = None):
    # if already initialized and registered, just return that plugin
    er = _impl_registry(v)
    if ext_name in er:
        plugin, value = er[ext_name]
        return plugin, value

    # if not ready, then we need to scan through the options and see if we can find a candidate
    options = _impl_options(ext_name, v=v)
    for opt in options:
        if opt.is_enabled(v):  # TODO: conflict detection
            return opt, None

    return None, None


def _init_plugin(name, v: Variables = None, _requested_by=None, _now=False, async_enabled: Optional[bool] = None):
    if v is None:
        v = _get_default_vars_instance()
    if async_enabled is None:
        async_enabled = _is_async_auto_enabled(v)

    pr = _plugin_registry(v)
    plugin = pr.get(name, local=True)  # type: Plugin
    if plugin is None:
        raise ValueError(f'unable to find plugin: {name}')

    # prep extension point information
    er = _impl_registry(v)
    ext_name = plugin.extension_point_name(v)

    # note that this approach means that a plugin cannot simultaneous be single & multi!
    if ext_name in er:  # return extension point registry result if plugin is marked as initialized
        return er[ext_name]

    is_single = plugin.is_enabled(v)
    is_multi = plugin.is_multi_extension(v)

    if not (is_single or is_multi):  # abort init of this plugin if it is disabled
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
        dep_plugin, _ = _find_plugin_for_single_ext(dep, v)
        if not dep_plugin:
            raise ValueError(f'unable to find registered plugin for extension point: {dep}')
        elif dep in _requested_by:
            raise ValueError(f'circular dependency "{dep}" encountered while trying to init {name}; history={_requested_by}')
        logger.debug('Processing dependency "%s" for extension point "%s"', dep, ext_name)
        _init_plugin(dep_plugin.name(), v, _requested_by=_requested_by)

    # check for ER conflict
    if ext_name in er and not is_multi:
        existing_plugin, existing_result = er[ext_name]  # type: Plugin, object
        raise ValueError(f'duplicated hit on extension point "{ext_name}"; '
                         f'write attempted by {name} by already taken by {existing_plugin.name()}')

    # now we initialize the requested plugin
    plugin.collected = True
    if plugin.eager or _now:  # if the plugin is eager... or we need it NOW, then make sure we initialize
        logger.debug('initializing plugin "%s" for extension point "%s", multi=%s', name, ext_name, is_multi)
        value = plugin.initialize(v, plugin.get_logger(v))
        plugin.initialized = True

        # try automatic async handling if possible (and enabled)
        if async_enabled:
            # if the plugin has an async_ready method, we can call it automatically IF:
            # 1. it hasn't been called before
            # 2. there's a captured async loop
            # If in the loop thread, we schedule without blocking (fire-and-forget).
            # If in a different thread, we can safely block and wait for completion.
            # For guaranteed ordering, users should await async_plugins_ready() explicitly.
            loop = get_captured_async_loop(v)
            if not plugin._async_ready_called and loop is not None:
                coro = plugin.async_ready(v, logger, value)
                if _is_in_loop_thread(v):
                    # Same thread as loop - schedule without blocking (fire-and-forget)
                    loop.create_task(coro)
                else:
                    # Different thread - safe to block and wait
                    timeout = v.get('=|ASYNC_PLUGIN_READY_TIMEOUT|', default=None)
                    future = asyncio.run_coroutine_threadsafe(coro, loop)
                    future.result(timeout=timeout)
                plugin._async_ready_called = True
    else:
        value = None

    # result
    result = (plugin, value)

    # commit to extension point registry
    if is_single:
        er[ext_name] = result = (plugin, value)
    if is_multi:
        _multi_ext_options(ext_name, v)[name] = list(result)  # list so that it's mutable later!
    pr.get_or_set('=|STARTUP_ORDER|', value_fn=list).append(plugin)

    return result


def shutdown_all_plugins(v: Variables = None, async_enabled: Optional[bool] = None):
    if v is None:
        v = _get_default_vars_instance()
    if async_enabled is None:
        async_enabled = _is_async_auto_enabled(v)

    pr = _plugin_registry(v)
    er = _impl_registry(v)
    logger = get_logger(v)
    for plugin in reversed(pr.get_or_set('=|STARTUP_ORDER|', value_fn=list)):  # type: Plugin
        if plugin.initialized:
            name = plugin.name()
            ext_name = plugin.extension_point_name(v)
            logger.debug('SAF: shutdown plugin: %s for %s', name, ext_name)
            try:
                if plugin.is_enabled(v):  # single extension mode (default)
                    _, value = er[ext_name]
                elif plugin.is_multi_extension(v):  # multi extension mode (alternative)
                    _, value = _multi_ext_options(ext_name, v)[name]
                else:
                    logger.warning('Unable to find value for extension point: %s', ext_name)
                    value = None

                if async_enabled:
                    # automatically handle async stopping IF:
                    # 1. it hasn't been called before
                    # 2. there's a captured async loop
                    # If in the loop thread, we schedule without blocking (fire-and-forget).
                    # If in a different thread, we can safely block and wait for completion.
                    # For guaranteed ordering, users should await async_plugins_stopping() explicitly.
                    loop = get_captured_async_loop(v)
                    if not plugin._async_stopping_called and loop is not None:
                        coro = plugin.async_stopping(v, logger, value)
                        if _is_in_loop_thread(v):
                            # Same thread as loop - schedule without blocking (fire-and-forget)
                            loop.create_task(coro)
                        else:
                            # Different thread - safe to block and wait
                            timeout = v.get('=|ASYNC_PLUGIN_STOPPING_TIMEOUT|', default=None)
                            future = asyncio.run_coroutine_threadsafe(coro, loop)
                            future.result(timeout=timeout)
                        plugin._async_stopping_called = True

                plugin.shutdown(v, plugin.get_logger(v), value)
            except Exception as e:
                logger.warning('Exception while shutting down plugin "%s" at extension point "%s": %s', name, ext_name, e)

    return


def register_plugin(plugin_type: Type[Plugin], v: Variables = None, init=False):
    """
    Register plugin to registry (either system default or given v)

    :param plugin_type:
    :param v:
    :param init:
    :return:
    """
    if v is None:
        v = _get_default_vars_instance()
    pr = _plugin_registry(v)
    instance = plugin_type()
    if (name := instance.name()) not in pr:
        ext_name = instance.extension_point_name(v)
        is_single = instance.is_enabled(v)
        is_multi = instance.is_multi_extension(v)

        get_logger(v).debug('Registering plugin: "%s" for extension point "%s", single=%s, multi=%s',
                            name, ext_name, is_single, is_multi)
        pr[name] = instance

        # add to implementations registry to keep record of it
        _impl_options((ext_name := instance.extension_point_name(v)), v=v).add(instance)

        # add to extension options registry if novel (to facilitate looking it up later)
        if is_multi and name not in (eo_dict := _multi_ext_options(ext_name, v=v)):
            eo_dict[name] = [instance, _NOT_INIT]

    elif (existing := pr.get(name)) is not None and not isinstance(existing, plugin_type):
        raise ValueError(f'Duplicate plugin name with different implementation: {name}, {type(existing)} vs {plugin_type}')

    if init:
        _init_plugin(instance.name(), v)

    return instance


def get_extension(extension_point: str | Type[Plugin], v: Variables = None):
    """
    Get implementation for the given extension_point

    :param extension_point:
    :param v:
    :return:
    """
    if v is None:
        v = _get_default_vars_instance()

    if isinstance(extension_point, type) and issubclass(extension_point, Plugin):
        instance = register_plugin(extension_point, init=True)
        extension_point = instance.extension_point_name(v)
    elif not isinstance(extension_point, str):
        raise ValueError(f'unable to determine extension point with given input: {extension_point}')

    er = _impl_registry(v)
    hit = er.get(extension_point)  # type: tuple[Plugin, object|None]
    if hit is None and ((hit := _find_plugin_for_single_ext(extension_point, v))[0] is None):
        raise ValueError(f'unknown extension point: {extension_point}')

    plugin, value = hit
    if value is None and not plugin.initialized:
        hit = _init_plugin(plugin.name(), v, _now=True)

    plugin, value = hit
    return value


def get_extensions(extension_point: str | Type[Plugin], v: Variables = None) -> dict[str, Any]:
    """
    Get an iterable of values associated with a given multi extension point.

    :param extension_point: string name of extension point
    :param v: optional variables/environment instance (uses system default if not provided)
    :return:
    """
    # noinspection DuplicatedCode
    if v is None:
        v = _get_default_vars_instance()

    if isinstance(extension_point, type) and issubclass(extension_point, Plugin):
        instance = register_plugin(extension_point, init=True)
        extension_point = instance.extension_point_name(v)
    elif not isinstance(extension_point, str):
        raise ValueError(f'unable to determine extension point with given input: {extension_point}')

    registry = _multi_ext_options(extension_point, v)
    result = {}
    for name, container in registry.items():
        instance, value = container
        # # TODO: support check is_multi_extension late to allow runtime enable/disable of extensions
        # if not instance.is_multi_extension(v):
        #     continue
        if value is _NOT_INIT:
            instance, value = _init_plugin(name, v, _now=True)
        result[name] = value
    return result


def init_all_plugins(v: Variables = None, async_enabled: Optional[bool] = None):
    if v is None:
        v = _get_default_vars_instance()
    if async_enabled is None:
        async_enabled = _is_async_auto_enabled(v)
    pr = _plugin_registry(v)
    for name in pr.keys():
        _init_plugin(name, v=v, async_enabled=async_enabled)
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


set_implementation = set_extension


# -----------------------------------------------------------------------------
# Async Lifecycle Functions
# -----------------------------------------------------------------------------

def _is_async_auto_enabled(v: Variables = None) -> bool:
    if v is None:
        v = _get_default_vars_instance()
    return v.get('=|ASYNC_PLUGIN_LIFECYCLE_AUTO|', default=True)


def set_async_auto_enabled(enabled: bool, v: Variables = None):
    if v is None:
        v = _get_default_vars_instance()
    v.set('=|ASYNC_PLUGIN_LIFECYCLE_AUTO|', enabled)
    return


def _get_plugin_value(plugin: Plugin, v: Variables):
    """Helper to retrieve the extension point value for a plugin."""
    er = _impl_registry(v)
    ext_name = plugin.extension_point_name(v)
    if plugin.is_enabled(v):
        entry = er.get(ext_name)
        if entry:
            return entry[1]
    elif plugin.is_multi_extension(v):
        entry = _multi_ext_options(ext_name, v).get(plugin.name())
        if entry:
            return entry[1]
    return None


def capture_async_loop(v: Variables = None, first_time_only: bool = False) -> asyncio.AbstractEventLoop | None:
    """
    Capture a reference to the currently running asyncio event loop.
    Call this from within an async context to enable async shutdown support.

    Returns the captured loop, or None if not in an async context.
    """
    if v is None:
        v = _get_default_vars_instance()
    try:
        loop = asyncio.get_running_loop()
        thread_id = threading.current_thread().ident
        if first_time_only:  # only set if not already set
            v.get_or_set(_VAR_ASYNC_LOOP, lambda: loop)
            v.get_or_set(_VAR_ASYNC_LOOP_THREAD, lambda: thread_id)
        else:
            v.set(_VAR_ASYNC_LOOP, loop)
            v.set(_VAR_ASYNC_LOOP_THREAD, thread_id)
        return loop
    except RuntimeError:
        return None


def _is_in_loop_thread(v: Variables = None) -> bool:
    """
    Check if the current thread is the same thread where the async loop was captured.
    Returns False if no loop was captured or if we're in a different thread.
    """
    if v is None:
        v = _get_default_vars_instance()
    captured_thread_id = v.get(_VAR_ASYNC_LOOP_THREAD)
    if captured_thread_id is None:
        return False
    return threading.current_thread().ident == captured_thread_id


def get_captured_async_loop(v: Variables = None) -> asyncio.AbstractEventLoop | None:
    """
    Get the previously captured async event loop reference.
    Returns None if no loop was captured or if the loop is closed.
    """
    if v is None:
        v = _get_default_vars_instance()
    async_loop_ref = v.get(_VAR_ASYNC_LOOP)
    if async_loop_ref is not None and not async_loop_ref.is_closed():
        return async_loop_ref
    return None


def clear_async_loop_ref(v: Variables = None):
    """Clear the captured async loop reference and thread ID."""
    if v is None:
        v = _get_default_vars_instance()
    v.set(_VAR_ASYNC_LOOP, None)
    v.set(_VAR_ASYNC_LOOP_THREAD, None)


async def async_plugins_ready(v: Variables = None, *, capture_loop: bool = True):
    """
    Signal all initialized plugins that the application is ready for async operations.
    Call this after framework initialization, from within an async context.

    This will call `async_ready()` on each initialized plugin in startup order.
    Plugins that don't override `async_ready()` will be skipped (returns None).

    :param v: variables instance (uses default if None)
    :param capture_loop: whether to capture the current event loop for later use (default True)
    """
    if v is None:
        v = _get_default_vars_instance()

    if capture_loop:
        capture_async_loop(v)

    logger = get_logger(v)
    pr = _plugin_registry(v)
    startup_order = pr.get_or_set('=|STARTUP_ORDER|', value_fn=list)

    for plugin in startup_order:  # type: Plugin
        if not plugin.initialized:
            continue

        try:
            value = _get_plugin_value(plugin, v)
            coro = plugin.async_ready(v, plugin.get_logger(v), value)
            if coro is not None and not plugin._async_ready_called:
                logger.debug('SAF: async_ready for plugin: %s', plugin.name())
                await coro
                plugin._async_ready_called = True
        except Exception as e:
            logger.warning('Exception in async_ready for plugin "%s": %s', plugin.name(), e)


async def async_plugins_stopping(v: Variables = None):
    """
    Signal all initialized plugins that the application is stopping.
    Call this before shutdown_all_plugins(), from within an async context.

    This will call `async_stopping()` on each initialized plugin in reverse startup order.
    Plugins that don't override `async_stopping()` will be skipped (returns None).

    :param v: variables instance (uses default if None)
    """
    if v is None:
        v = _get_default_vars_instance()

    logger = get_logger(v)
    pr = _plugin_registry(v)
    startup_order = pr.get_or_set('=|STARTUP_ORDER|', value_fn=list)

    for plugin in reversed(startup_order):  # type: Plugin
        if not plugin.initialized:
            continue

        try:
            value = _get_plugin_value(plugin, v)
            coro = plugin.async_stopping(v, plugin.get_logger(v), value)
            if coro is not None and not plugin._async_stopping_called:
                logger.debug('SAF: async_stopping for plugin: %s', plugin.name())
                await coro
                plugin._async_stopping_called = True
        except Exception as e:
            logger.warning('Exception in async_stopping for plugin "%s": %s', plugin.name(), e)


def schedule_async_shutdown(v: Variables = None, timeout: float = 5.0) -> bool:
    """
    Attempt to schedule async_plugins_stopping() on the captured event loop.
    This is useful when shutdown is triggered from a sync context (e.g., signal handler)
    but async cleanup is still desired.

    This function is non-blocking and thread-safe. It schedules the coroutine
    on the captured loop using run_coroutine_threadsafe.

    :param v: variables instance (uses default if None)
    :param timeout: maximum time to wait for async shutdown to complete (seconds)
    :return: True if async shutdown was scheduled and completed, False otherwise
    """
    loop = get_captured_async_loop(v)
    if loop is None:
        return False

    if loop.is_closed():
        clear_async_loop_ref(v)
        return False

    try:
        future = asyncio.run_coroutine_threadsafe(async_plugins_stopping(v), loop)
        future.result(timeout=timeout)
        return True
    except asyncio.TimeoutError:
        get_logger(v).warning('Async shutdown timed out after %.1f seconds', timeout)
        return False
    except Exception as e:
        get_logger(v).debug('Could not schedule async shutdown: %s', e)
        return False
