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
    register_base_plugins = kwargs.pop('base_plugins', True)
    v = _init_framework(*args, **kwargs)

    if v.environ('SAF_BASE_PLUGINS', default=register_base_plugins, type_fn=ext_parse_bool):
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
    which makes more sense for a desktop application than the defaults which are more geared towards
    containerized applications.

    Also sets the following defaults (that take effect unless overridden by environment or kwarg):
    * set the default stateful_chdir functionality to False
    * set the default shutdown hooks approach to use the stdlib "atexit" module
    * set base plugins to register

    :param args: arguments from `init_framework`
    :param kwargs: keyword arguments from `init_framework`
    :return:
    """
    import pathlib

    # configure stateful to target ~/.config/{APP_NAME}
    if 'default_stateful_root' not in kwargs:
        kwargs['default_stateful_root'] = pathlib.Path.home()
    if 'default_run_id' not in kwargs:
        kwargs['default_run_id'] = '.config'
    if 'default_serial_strategy' not in kwargs:
        kwargs['default_serial_strategy'] = None

    # preserve current directory (app functionality may depend on working directory)
    if 'stateful_chdir' not in kwargs:
        kwargs['stateful_chdir'] = False

    # prefer atexit to signal handlers for desktop apps
    if 'shutdown_hooks_via_atexit' not in kwargs:
        kwargs['shutdown_hooks_via_atexit'] = True

    # desktop apps are more likely to make use of the base plugins
    if 'base_plugins' not in kwargs:
        kwargs['base_plugins'] = True

    # continue usual framework init
    return init_framework(*args, **kwargs)


init_framework.__doc__ = _init_framework.__doc__
