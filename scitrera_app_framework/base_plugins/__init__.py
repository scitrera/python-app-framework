from ..api import Variables
from ..core.plugins import get_extension
from .bg_exec import EXT_BACKGROUND_EXEC, JobExecutorEngine
from .progress_tracker import EXT_PROGRESS_TRACKER, ProgressTracker


def register_package_plugins(package: str, v: Variables = None, exclusions=(), recursive=False):
    """
    Register plugin classes found in the given package.

    This function searches for all subclasses of the `Plugin` class within the specified package (non-recursively by default),
    and registers them. Plugins can be excluded from registration by specifying them in the `exclusions` parameter.

    :param package: The package or module in which to search for plugin classes.
    :param v: optional framework Variables instance to operate on; default system instance is used if not provided
    :param exclusions: An optional tuple of plugin classes that should be excluded from registration. Defaults to an empty tuple.
    :param recursive: Whether to recursively search for packages that contains plugins. Defaults to False.
    """
    from ..api import Plugin
    from ..util.imports import find_types_in_modules
    from ..core.plugins import register_plugin

    for plugin in find_types_in_modules(package, Plugin, recursive=recursive, exclude_base_type=True):
        if plugin in exclusions:
            continue
        register_plugin(plugin, v)

    return


def get_background_exec(v: Variables = None) -> JobExecutorEngine:
    """
    Get (background) thread pool executor for default framework instance (or given framework variables instance)

    :param v: optional framework Variables instance to operate on; default system instance is used if not provided
    :return: JobExecutorEngine (background thread pool executor)
    """
    return get_extension(EXT_BACKGROUND_EXEC, v)


def get_progress_tracker(v: Variables = None) -> ProgressTracker:
    """
    Get progress tracker instance for default framework instance (or given framework variables instance)

    :param v: optional framework Variables instance to operate on; default system instance is used if not provided
    :return: ProgressTracker (utility class to facilitate tracking progress of operations for a UI, etc.)
    """
    return get_extension(EXT_PROGRESS_TRACKER, v)
