from ..api import Variables
from ..core.plugins import get_extension
from .bg_exec import EXT_BACKGROUND_EXEC, JobExecutorEngine
from .progress_tracker import EXT_PROGRESS_TRACKER, ProgressTracker


def register_package_plugins(package, v=None, exclusions=()):
    from ..api import Plugin
    from ..util.imports import find_types_in_modules
    from ..core.plugins import register_plugin

    for plugin in find_types_in_modules(package, Plugin, recursive=False, exclude_base_type=True):
        if plugin in exclusions:
            continue
        register_plugin(plugin, v)

    return


def get_background_exec(v: Variables = None) -> JobExecutorEngine:
    return get_extension(EXT_BACKGROUND_EXEC, v)


def get_progress_tracker(v: Variables = None) -> ProgressTracker:
    return get_extension(EXT_PROGRESS_TRACKER, v)
