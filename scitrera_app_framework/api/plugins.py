from __future__ import annotations

from abc import abstractmethod
from logging import Logger
from typing import Iterable

from .variables import Variables as Variables, NOT_SET


class Plugin(object):
    collected: bool = False  # whether this plugin has been registered to plugin and extension registry
    initialized: bool = False  # whether this plugin has run its `initialize` method
    _async_ready_called: bool = False  # whether this plugin has run its `async_ready` method
    _async_stopping_called: bool = False  # whether this plugin has run its `async_stopping` method
    eager: bool = True  # whether this plugin defers running `initialize` until extension point requested or eagerly upon init call

    # TODO: is_single_/is_multi_extension could be set as class fields rather than as methods?

    def name(self) -> str:
        """
        Each plugin should have a name that does not conflict with any other plugin.
        """
        return f'{self.__class__.__module__}.{self.__class__.__name__}'

    def extension_point_name(self, v: Variables) -> str:
        """
        Each plugin should define the extension point that it fills. Often, this can be the name; however,
        it is possible that multiple plugins may potentially connect to the same extension point. This facilitates
        selecting different implementations at init-time, swapping in mock units, etc.

        However, it should be noted that only one plugin at a time can be enabled for a given extension point.
        """
        return self.name()

    @staticmethod
    def get_extension(target_name: str, v: Variables = None):
        """
        Convenience method that calls core `get_extension`. Here to facilitate pulling in dependencies, etc.
        """
        from scitrera_app_framework.core import get_extension
        return get_extension(target_name, v)

    def get_my_extension(self, v: Variables):
        """
        Convenience method that loads the extension point value for my extension point. Typically, this will be
        the result of the `initialize` method; however, it could come from a different plugin that connects at
        the same extension point.
        """
        from scitrera_app_framework.core import get_extension
        return get_extension(self.extension_point_name(v), v)

    def get_logger(self, v: Variables):
        """
        Convenience method that returns a child Logger (using extension point name) to the application main logger
        """
        from scitrera_app_framework.core import get_logger
        return get_logger(v).getChild(self.extension_point_name(v))

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def is_enabled(self, v: Variables) -> bool:
        """
        Each plugin can use variables to determine if it should be enabled. This provides a mechanism to differentiate between
        alternative plugins that otherwise would conflict on the same extension point--even if both are registered.

        In classic "dependency injection" mode, this method determines if this is the active plugin to provide
        implementation for a given extension point (interface).

        TODO: this method should ideally change names to be more clear for its intended usage (e.g. is_active_implementation)
        """
        return True

    # noinspection PyMethodMayBeStatic
    def is_multi_extension(self, v: Variables) -> bool:
        """
        In the OSGi sense of a plugin registry/system, it could be possible that multiple plugins could
        simultaneously add value at a certain extension point (e.g. for a "file reader" extension, there may be
        multiple valid implementations that should be considered). TODO: better example

        By default, this will be False since the initial implementation was to provide a dependency injection
        like approach. This was added to support an OSGi extension-type approach as well.

        :param v: optional variables/environment instance (will use default instance if not provided)
        """
        return False

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get_dependencies(self, v: Variables) -> Iterable[str] | None:
        """
        Each plugin may declare other plugins that must initialize before itself
        """
        return ()

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def on_registration(self, v: Variables) -> None:
        """
        Optional hook called once when the plugin is first registered/collected,
        before initialization. This is called only once per plugin instance,
        regardless of how many times register_plugin is called.

        Use this for early setup that needs to happen before initialization,
        such as registering additional plugins, setting up environment defaults,
        or other preparatory actions.

        The default implementation does nothing.

        :param v: the variables/environment instance
        """
        pass

    @abstractmethod
    def initialize(self, v: Variables, logger: Logger) -> object | None:
        """
        Each plugin, on initialization, may produce an object that can be recalled by name. The initialize method
        is given the relevant Variables object instance to ensure that it can pull settings from environment variables.

        This is the primary place to put code for what should happen when loading this plugin...
        """
        pass

    def shutdown(self, v: Variables, logger: Logger, value: object | None) -> None:
        """
        Each plugin can also have a shutdown method that declares how it should be safely shutdown
        """
        return

    # -------------------------------------------------------------------------
    # Async Lifecycle Hooks (Optional)
    # -------------------------------------------------------------------------
    # These methods provide optional async lifecycle support for plugins that need
    # to perform async operations (e.g., establishing database connections, starting
    # async tasks, etc.). They are called by the framework when running in an async
    # context via `async_plugins_ready()` and `async_plugins_stopping()`.
    #
    # The sync `initialize()` and `shutdown()` methods remain the primary lifecycle
    # methods. These async hooks are additive and do not replace them.
    # -------------------------------------------------------------------------

    async def async_ready(self, v: Variables, logger: Logger, value: object | None) -> None:
        """
        Optional async hook called after all plugins have been initialized, when running
        in an async context. Use this for async resource acquisition such as:
        - Establishing database connection pools
        - Starting background async tasks
        - Opening async network connections/sessions

        This is called AFTER `initialize()` completes. The `value` parameter is the
        return value from `initialize()`.

        Override this method to perform async setup. The default implementation
        does nothing.

        :param v: variables instance
        :param logger: logger for this plugin
        :param value: the value returned by initialize()
        """
        pass

    async def async_stopping(self, v: Variables, logger: Logger, value: object | None) -> None:
        """
        Optional async hook called before shutdown begins, when running in an async
        context. Use this for graceful async cleanup such as:
        - Draining message queues
        - Closing async connections gracefully
        - Cancelling and awaiting background tasks

        This is called BEFORE `shutdown()`. The `value` parameter is the extension
        point value (same as passed to shutdown).

        Override this method to perform async teardown. The default implementation
        does nothing.

        :param v: variables instance
        :param logger: logger for this plugin
        :param value: the extension point value
        """
        pass


def enabled_option_pattern(plugin: Plugin, v: Variables, env_variable: str, default: str = NOT_SET, self_attr: str = None) -> bool:
    """
    Pattern function to enable creating subclasses or related plugins such that this function can provide the result
    of the `is_enabled` method by matching an environment variable value to either the plugin name or an attribute of the plugin class

    :param plugin: the plugin being evaluated (generally will be 'self' when used as part of plugin classes)
    :param v: the variables instance (should come from `is_enabled` method arguments)
    :param env_variable: the string corresponding with the environment variable to query
    :param default: the default value to be applied if the environment variable is not set
    :param self_attr: the name of the attribute to be matched (if not provided, then the plugin's full name will be used)
    :return: boolean True/False
    """
    target_value = getattr(plugin, self_attr) if self_attr else plugin.name()
    return v.environ(env_variable, default=default) == target_value
