from .core import (register_shutdown_function, get_logger, get_working_path, get_extension, register_plugin, init_all_plugins,
                   init_framework as _init_framework)
from .util import ext_parse_bool
from .base_plugins import EXT_BACKGROUND_EXEC, EXT_PROGRESS_TRACKER


def init_framework(*args, **kwargs):
    v = _init_framework(*args, **kwargs)

    # noinspection PyProtectedMember
    from .base_plugins import _register_base_plugins
    _register_base_plugins(v)

    # register shutdown function to shut down plugins upon initializing plugins...
    # noinspection PyProtectedMember
    from .core.plugins import _shutdown_plugins
    register_shutdown_function(_shutdown_plugins, v)

    return v


init_framework.__doc__ = _init_framework.__doc__
