from .bg_exec import EXT_BACKGROUND_EXEC
from .progress_tracker import EXT_PROGRESS_TRACKER


def _register_base_plugins(v=None):
    # TODO: formalize base plugins registration approach

    from scitrera_app_framework.core import register_plugin

    from .bg_exec import BackgroundThreadExecutorPlugin
    register_plugin(BackgroundThreadExecutorPlugin, v=v)

    from .progress_tracker import ProgressTrackerPlugin
    register_plugin(ProgressTrackerPlugin, v=v)

    return
