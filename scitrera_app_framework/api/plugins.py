from __future__ import annotations

from abc import abstractmethod
from logging import Logger
from typing import Iterable

from .variables import Variables


class Plugin(object):
    collected: bool = False  # whether this plugin has been registered to plugin and extension registry
    initialized: bool = False  # whether this plugin has run its `initialize` method
    eager: bool = True  # whether this plugin defers running `initialize` until extension point requested or eagerly upon init call

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
        """
        return True

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get_dependencies(self, v: Variables) -> Iterable[str] | None:
        """
        Each plugin may declare other plugins that must initialize before itself
        """
        return ()

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

    pass


def enabled_option_pattern(plugin: Plugin, v: Variables, env_variable: str, default: str, self_attr: str = None) -> bool:
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
