from .core import (
    register_shutdown_function, get_logger, get_working_path, get_variables,
    get_extension, register_plugin, init_all_plugins, get_extensions,
    init_framework as _init_framework,
)
from .util import (
    ext_parse_bool, ext_parse_csv,
)
from .base_plugins import (
    register_package_plugins,
    EXT_BACKGROUND_EXEC, get_background_exec,
    EXT_PROGRESS_TRACKER, get_progress_tracker,
)


def init_framework(*args, **kwargs):
    v = _init_framework(*args, **kwargs)

    # import all base_plugins
    from . import base_plugins
    register_package_plugins(base_plugins.__name__, v)

    # register shutdown function to shut down plugins upon initializing plugins...
    from .core.plugins import shutdown_all_plugins
    register_shutdown_function(shutdown_all_plugins, v)

    return v


def init_framework_desktop(*args, **kwargs):
    """
    Alternate bootstrap function for `init_framework`. All arguments and keyword arguments are the
    same as `init_framework`, so see that function for details. However, the default values for
    the stateful root if not specified are changed such that stateful root will be "~/.config/$APP_NAME"
    which makes more sense for a desktop application that the defaults which are more geared towards
    containerized applications.

    :param args: arguments from `init_framework`
    :param kwargs: keyword arguments from `init_framework`
    :return:
    """
    import pathlib
    if 'default_stateful_root' not in kwargs:
        kwargs['default_stateful_root'] = pathlib.Path.home()
    if 'default_run_id' not in kwargs:
        kwargs['default_run_id'] = '.config'
    return init_framework(*args, **kwargs)


init_framework.__doc__ = _init_framework.__doc__
