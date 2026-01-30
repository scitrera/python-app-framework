from .api import (
    Variables, Plugin,
)
from .core import (
    register_shutdown_function, get_logger, get_working_path, get_variables,
    get_extension, register_plugin, init_all_plugins, get_extensions,
    init_framework as _init_framework,
    async_plugins_ready, async_plugins_stopping,
)
from .util import (
    ext_parse_bool, ext_parse_csv, ext_get_python,
)
from .base_plugins import (
    register_package_plugins,
    EXT_BACKGROUND_EXEC, get_background_exec,
    EXT_PROGRESS_TRACKER, get_progress_tracker,
)
from .core.util import add_env_file_source


def init_framework(*args, **kwargs) -> Variables:
    register_base_plugins = kwargs.pop('base_plugins', False)
    enable_pyroscope = kwargs.pop('pyroscope', False)

    v = _init_framework(*args, **kwargs)

    # transitioned pyroscope out of core and into being a plugin -- it should be the first thing we load after internal init_framework
    from .ext_plugins.pyroscope_plugin import PyroscopePlugin, PYROSCOPE_ENABLED
    v.set_default_value(PYROSCOPE_ENABLED, enable_pyroscope)  # if not defined in environment, fallback to kwarg (or False)
    register_plugin(PyroscopePlugin, v, init=True)

    # then base plugins
    if v.environ('SAF_BASE_PLUGINS', default=register_base_plugins, type_fn=ext_parse_bool):
        from . import base_plugins
        register_package_plugins(base_plugins.__name__, v, recursive=False)  # explicitly set do not search base_plugins recursively

    # register shutdown function to shut down plugins upon initializing plugins...
    from .core.plugins import shutdown_all_plugins
    register_shutdown_function(shutdown_all_plugins, v)

    # facilitate multitenant init as kwarg and/or environment variable (with typical env variable taking precedence)
    if v.environ('SAF_MULTITENANT_ENABLED', default=kwargs.pop('multitenant', False), type_fn=ext_parse_bool):
        from .ext_plugins.multi_tenant import MultiTenantPlugin
        register_plugin(MultiTenantPlugin, v, init=True)

    # manage whether async plugins are auto-enabled
    from .core.plugins import set_async_auto_enabled
    set_async_auto_enabled(v.environ('SAF_ASYNC_AUTO_MODE', default=kwargs.pop('async_auto_enabled', True), type_fn=ext_parse_bool))

    return v


def init_framework_desktop(*args, **kwargs) -> Variables:
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


def init_framework_test_harness(*args, **kwargs) -> Variables:
    """
    Alternate bootstrap function for `init_framework` meant to be used for testing harnesses.
    All arguments and keyword arguments are the same as `init_framework`, so see that function for details.
    However, it has the following default values that may vary from the base `init_framework`:
    * fault_handler is False by default
    * log_level is DEBUG by default
    * pyroscope is False by default (ok not different, but still worth saying)
    * shutdown_hooks are False by default
    * stateful is False by default

    :param args: arguments from `init_framework`
    :param kwargs: keyword arguments from `init_framework`
    :return:
    """
    if 'fault_handler' not in kwargs:
        kwargs['fault_handler'] = False
    if 'log_level' not in kwargs:
        kwargs['log_level'] = 'DEBUG'
    if 'pyroscope' not in kwargs:
        kwargs['pyroscope'] = False
    if 'shutdown_hooks' not in kwargs:
        kwargs['shutdown_hooks'] = False
    if 'stateful' not in kwargs:
        kwargs['stateful'] = False

    # continue usual framework init
    return init_framework(*args, **kwargs)


def init_framework_embedded(*args, **kwargs) -> Variables:
    """
    Alternate bootstrap function for `init_framework` meant to be used within other applications.
    All arguments and keyword arguments are the same as `init_framework`, so see that function for details.
    However, it has the following default values that may vary from the base `init_framework`:
    * fault_handler is False by default
    * fixed_logger is set to a default python logger 'SAF' if not provided (to avoid overriding logging configuration)
    * pyroscope is False by default (ok not different, but still worth saying)
    * shutdown_hooks are False by default
    * stateful is False by default

    :param args: arguments from `init_framework`
    :param kwargs: keyword arguments from `init_framework`
    :return:
    """
    import logging

    if 'fault_handler' not in kwargs:
        kwargs['fault_handler'] = False
    if 'fixed_logger' not in kwargs:
        kwargs['fixed_logger'] = logging.getLogger('SAF')
    if 'pyroscope' not in kwargs:
        kwargs['pyroscope'] = False
    if 'shutdown_hooks' not in kwargs:
        kwargs['shutdown_hooks'] = False
    if 'stateful' not in kwargs:
        kwargs['stateful'] = False

    # continue usual framework init
    return init_framework(*args, **kwargs)


init_framework.__doc__ = _init_framework.__doc__
