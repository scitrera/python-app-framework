from __future__ import annotations
from typing import Iterable, Optional, Tuple

import os
import faulthandler
import logging
import sys
import signal
# from time import sleep
from os import chdir, makedirs, path as osp

from botwinick_utils.util import LOGGING_FORMAT, LOGGING_DATE_FORMAT

from ..util import (ext_parse_bool, now_ms)
from ..api import (Variables, is_epp)
from ..util.imports import get_python_type_by_name

_sigterm_hooks = []

_default_vars_inst = None

# variables for standardized internal names (with symbols that make them unlikely to collide with any user variable names)
_VAR_APP_STATEFUL_ROOT = '=|app_state_root|'
_VAR_APP_STATEFUL_READY = '=|app_state_ready|'
_VAR_MAIN_LOGGER = '=|main_logger|'
_VAR_PARAM_MAP = '=|PARAM_MAP|'

ENV_LOGGING_LEVEL = 'LOGGING_LEVEL'


class _SAFStreamHandler(logging.StreamHandler):
    """Custom StreamHandler created by the framework."""
    pass


def _get_default_vars_instance() -> Variables:
    """ Internal function to get/initialize the default variables instance. """
    global _default_vars_inst
    if _default_vars_inst is None:
        _default_vars_inst = Variables()
    return _default_vars_inst


def get_variables(v: Variables = None) -> Variables:
    """
    Function to "filter" a reference to a Variables object such that if a Variables object instance
    is NOT provided then the default instance will be returned instead.

    :param v: optional/possible Variables instance
    :return: either the given Variables instance or the default Variables instance
    """
    if isinstance(v, Variables):
        return v
    return _get_default_vars_instance()


# noinspection PyCompatibility
def register_shutdown_function(fn, *args, **kwargs):
    """
    Register a function to shut down when the framework shuts down.
    :param fn: reference to function
    :param args: arguments to pass to function
    :param kwargs: kwargs to pass to function
    """
    _sigterm_hooks.append((fn, args, kwargs))


def _install_signal_hooks(v: Variables = None, via_at_exit=True):
    """ Internal function to install signal/at_exit hooks for framework """
    if v is None:
        v = _get_default_vars_instance()

    logger = get_logger(v)

    # noinspection PyUnusedLocal
    def sigterm_hook(sig, frame):
        logger.info('received termination signal, processing shutdown calls')
        for (fn, args, kwargs) in reversed(_sigterm_hooks):
            try:
                logger.debug('shutdown call: %s(%s, %s)', fn.__name__, args, kwargs)
                fn(*args, **kwargs)
            except Exception as e:
                logger.warning('exception during shutdown hook: %s', e)

        try:
            # sleep(0.25)  # short sleep to maybe let async stuff catch up a bit...
            sys.exit(0)
        except SystemExit:
            pass

    if via_at_exit:
        import atexit
        logger.debug('installing atexit shutdown hook(s)')
        atexit.register(sigterm_hook, None, None)
    else:
        logger.debug('installing SIGTERM shutdown hook(s)')
        signal.signal(signal.SIGTERM, sigterm_hook)
    return


def get_logger(v: Variables = None, logger=None, name=None) -> logging.Logger:
    """
    Get a logging.Logger instance tied to the framework. It is either the framework's main logger,
    a derived logger using given name, or an emergency logger created to ensure this function
    always returns a logger.

    :param v: variables instance or None to use default instance
    :param logger: potentially a logger to pass through if it makes sense to provide your own in this context
    :param name: optional name to use to create a child logger
    :return: logger instance
    """
    if v is None:
        v = _get_default_vars_instance()

    if logger is None:
        logger = v.get(_VAR_MAIN_LOGGER)
        if logger is None:
            logger = logging.getLogger('SAF')  # no logger, but don't leave developer high and dry...
            logger.warning('logger called before framework initialization! verify plugins / import order')

    if name is not None:
        return logger.getChild(name)
    return logger


def _log_fmt_json(**static_fields):
    """ Internal function to create formatter instance for JSON logs """
    try:
        from pythonjsonlogger.jsonlogger import JsonFormatter

        return JsonFormatter(
            static_fields=static_fields,
            # commented out items are those we want to include
            # those that are listed in reserved_attrs will be skipped if found
            reserved_attrs=(
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                # "filename",
                # "funcName",
                # "levelname",
                "levelno",
                # "lineno",
                "module",
                "msecs",
                # "message",
                "msg",
                # "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                # "threadName",
            ),
            timestamp=False,  # timestamp will come from k8s logs instead
        )
    except ImportError:
        return None


def _init_logging(logger_name, level='INFO', formatter=None, stream=sys.stderr) -> logging.Logger:
    """ Internal function to initialize logging """
    log_level = logging.getLevelName(level.upper())
    root_logger = logging.root
    root_logger.setLevel(log_level)

    # check if a framework-created handler is already present on the root logger.
    root_already_initialized = any(isinstance(h, _SAFStreamHandler) for h in root_logger.handlers)

    # if first time initialization: clear the default handlers and add our custom handler
    if not root_already_initialized and stream is not None:
        root_logger.handlers.clear()
        # noinspection PyTypeChecker
        handler = _SAFStreamHandler(stream=stream)
        if formatter is not None:
            handler.setFormatter(formatter)
        handler.setLevel(log_level)
        root_logger.addHandler(handler)

    # return base logger for framework
    logger = logging.getLogger(logger_name)
    return logger


def _set_root_logging_level(level='INFO'):
    log_level = logging.getLevelName(level.upper())
    root_logger = logging.root
    root_logger.setLevel(log_level)
    for handler in root_logger.handlers:
        if isinstance(handler, _SAFStreamHandler):
            handler.setLevel(log_level)
            return  # job done

    raise ValueError('cannot set root logging level before initialization')


def _init_stateful_root(v: Variables, local_name=None, default_stateful_root='./scratch',
                        default_run_id=None, default_run_serial=None, default_chdir=True, stateful_root_env_key: str = 'STATEFUL_ROOT'):
    """
    Internal function to initialize stateful root/stateful features.

    :param v: variables instance
    :param local_name: application name override
    :param default_stateful_root: default stateful root path
    :param default_run_id: default run_id (part of establishing path)
    :param default_run_serial: default run_serial (part of establishing path)
    :param default_chdir: whether to change directories to stateful root by default
    """
    logger = get_logger(v)

    if local_name is None:
        local_name = v.get('APP_NAME')

    # setup working directory for application state if available
    state_root = v.environ(stateful_root_env_key, default=default_stateful_root)
    if not osp.exists(state_root):
        logger.debug('state_root "%s" does not exist. aborting stateful setup', state_root)
        return

    # use run_id and run_serial with local_name to determine path
    run_id = v.environ('RUN_ID', default=default_run_id)
    run_serial = v.environ('RUN_SERIAL', default=default_run_serial)
    app_state_root = osp.join(state_root, *filter(None, (run_id, run_serial, local_name)))
    v.set(_VAR_APP_STATEFUL_ROOT, app_state_root)

    # makedirs as needed and set working directory to stateful root
    logger.debug('app stateful root=%s', app_state_root)
    makedirs(app_state_root, exist_ok=True)
    if v.environ('SAF_STATEFUL_CHDIR', default=default_chdir, type_fn=ext_parse_bool):
        chdir(app_state_root)
    v.set(_VAR_APP_STATEFUL_READY, True)  # set stateful ready flag to True
    return


def is_stateful_ready(v: Variables):
    """
    Check if stateful init completed successfully. Return stateful root (not None) when successful or None if not
    stateful storage not available.

    :param v: framework variables object
    :return: stateful root if stateful init completed successfully or None if not stateful ready
    """
    if v is None:
        v = _get_default_vars_instance()
    if v.get(_VAR_APP_STATEFUL_READY):  # should be True or None
        return v.get(_VAR_APP_STATEFUL_ROOT)  # if ready, we expect this to be a defined value
    return None


def load_strategy(v: Variables, parent_type, prefix='STRATEGY', drop_prefix=True) -> Tuple[Optional[object], dict]:
    """
    This function will import a python type and return all environment variables that have the same prefix as
    "xxx_type" where xxx is the prefix. So if you want to load `hello_world_widget_factory` and get configuration
    for `hello_world_widget_factory`, you could set environment variables such as:

    WIDGET_FACTORY_TYPE="mypythonpackage.factories.HelloWorldWidgetFactory"
    WIDGET_FACTORY_SPIN_RATE=9000

    and then call this function such as

    >> factory_type, factory_kwargs = load_strategy(v, parent_type=AbstractFactory, prefix="WIDGET_FACTORY")

    If drop_prefix is True (default), then the contents of factory_kwargs will be:
    { 'spin_rate: '9000', }

    Note that if type functions have been defined for the "kwargs" variables, they will be honored and manage type conversion.

    Also note that... obviously the function name implies that this was intended for a specific application; however, it is
    generally a useful component for many different applications. For the moment, the naming will be preserved, but it might
    make sense to change this name to be more generic in the future...

    :param v: variables instance (no default provided, you must supply it)
    :param parent_type: parent class of the type that you are expecting
    :param prefix: prefix that environment variables will have
    :param drop_prefix: whether the prefix should be removed from the string keys of the resulting "strategy" kwargs. Default is True.
    :return: tuple of (type, kwargs populated from environment variables); importing python packages/modules as needed.
    """
    # if v is None:
    #     v = _get_default_vars_instance()
    # dynamic strategy loading and configuration
    strategy_kwargs = v.import_from_env_by_prefix(prefix, drop_prefix=drop_prefix)
    strategy_type_name = strategy_kwargs.pop('type', None)  # type: str|None

    try:
        strategy = None if strategy_type_name is None else get_python_type_by_name(strategy_type_name, parent_type)
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        get_logger(v).error('unable to load strategy "%s" with prefix "%s": %s: %s',
                            strategy_type_name, prefix, e.__class__.__name__, e)
        strategy = None

    return strategy, strategy_kwargs


def get_working_path(v: Variables = None, default='.', env_key='DATA_WORKING_PATH') -> str:
    """
    Opinionated function to get working path;
    resolution order:
    1) ENVIRONMENT VARIABLE for env_key
    2) STATEFUL ROOT derived location (if available)
    3) given default to this function (typically .)

    :param v: framework env/variables object
    :param default: fallback working path (default is '.')
    :param env_key: environment key for working path override (first priority) value
    :return:
    """
    if v is None:
        v = _get_default_vars_instance()
    stateful_ready_root = is_stateful_ready(v)
    return v.environ(env_key, default=stateful_ready_root if stateful_ready_root is not None else default)


def init_framework(base_app_name: str,
                   fixed_logger=None, log_format=None, log_level='INFO',
                   shutdown_hooks=True, shutdown_hooks_via_atexit=True,
                   stateful=True, stateful_chdir=True, default_stateful_root='./scratch', default_run_id=None, default_serial_strategy=None,
                   stateful_root_env_key: str = 'STATEFUL_ROOT',
                   fault_handler=True,
                   sep='-', unnamed_params=(),
                   v: Variables = None,
                   **params) -> Variables:
    """
    Initialize the Scitrera Application Framework. This should be the first thing to be called in a "main" function
    for an application or container entrypoint.

    :param base_app_name: hard-coded base application name
    :param fixed_logger: a predefined logger. Only use this in advanced usage when the framework is not at the center of the application.
    :param log_format: either 'json' to log following json message per line convention to facilitate log aggregation
                        or a %-style log format string.
    :param log_level: the default log level if not set by env variable.
    :param shutdown_hooks: whether the default functionality is to install shutdown hooks (env variable will override this)
    :param shutdown_hooks_via_atexit: whether the default functionality for shutdown hooks is to use stdlib "atexit"
    :param stateful: whether the default functionality is to try to install stateful functionality (env variable will override this)
    :param stateful_chdir: whether the default stateful functionality is to change the current working dir (env variable will override this)
    :param default_stateful_root: the default stateful root if not provided by env variable
    :param default_run_id: default run_id for stateful init (becomes next directory in path after stateful_root)
    :param default_serial_strategy: default strategy for generating run serial (default is None) (alternative: 'ms': use unix time in ms)
    :param stateful_root_env_key: environment variable key to use for stateful root path (env variable will override this)
    :param fault_handler: whether the default functionality is to try to install the python fault handler (env variable will override this)
    :param sep: the default separator used when constructing a longer, more complex app name based on given parameters
    :param unnamed_params: an iterable (tuple) containing parameters that should not be included in the app name
    :param v: an optional variables instance (a default instance will be provided and managed if None)
    :param params: additional parameters to include as part of app name, pyroscope tagging, etc.
    :return: variables instance for the framework
    """
    # init variables framework
    if v is None:
        v = _get_default_vars_instance()

    # check that v isn't already initialized; if it's already initialized -- then we can short-circuit and return v
    if _VAR_MAIN_LOGGER in v:
        return v  # already initialized

    # normalize parameters map w/ environment fallback values
    param_map = v.set(_VAR_PARAM_MAP, {k.lower(): v.environ(k.upper(), default=val) for k, val in params.items()})

    # install python fault handler
    if v.environ('SAF_ENABLE_PYTHON_FAULT_HANDLER', default=fault_handler, type_fn=ext_parse_bool) and sys.stderr is not None:
        # TODO: potentially support faulthandler config with different file if stderr is unavailable?
        faulthandler.enable()

    # determine app name with suffixes attached
    name_ = v.set('SAF_BASE_APP_NAME', base_app_name)
    name_params = [n for n in param_map.keys() if n not in unnamed_params]
    if len(name_params) > 0:
        name_ += sep + sep.join((str(param_map[n]) for n in name_params))
    app_name = v.environ('APP_NAME', default=name_)  # allow environment variable override/configuration of APP_NAME
    build_image_name = v.environ('BUILD_IMAGE_NAME', default=base_app_name)
    build_container_version = v.environ('BUILD_CONTAINER_VERSION', default='DEV')

    # setup logging -- or use a given logger if provided (usually a hint that we're not the central managing framework of the application)
    if fixed_logger is None:
        # do logger init
        log_format = v.environ('LOGGING_FORMAT', default=log_format)
        log_date_format = v.environ('LOGGING_DATE_FORMAT', default=LOGGING_DATE_FORMAT)
        if log_format == 'json':
            fmt = _log_fmt_json(**param_map)
        elif log_format and '%' in log_format:  # TODO: more format control options
            fmt = logging.Formatter(log_format, log_date_format)
        else:
            fmt = logging.Formatter(LOGGING_FORMAT, log_date_format)

        # TODO: mechanism to set stream
        logger = v.set(_VAR_MAIN_LOGGER, _init_logging(
            app_name,
            level=v.environ(ENV_LOGGING_LEVEL, default=log_level),
            formatter=fmt
        ))
        if build_container_version != 'DEV':
            logger.info('Initializing %s; container=%s, version=%s', app_name, build_image_name, build_container_version)
        else:
            logger.info('Initializing %s', app_name)
    else:
        # noinspection PyUnusedLocal
        logger = v.set(_VAR_MAIN_LOGGER, fixed_logger)

    # install signal shutdown hooks (must be on MainThread)
    if v.environ('SAF_INSTALL_SHUTDOWN_HOOKS', default=shutdown_hooks, type_fn=ext_parse_bool):
        _install_signal_hooks(v, via_at_exit=v.environ('SAF_SHUTDOWN_HOOK_VIA_ATEXIT',
                                                       default=shutdown_hooks_via_atexit, type_fn=ext_parse_bool))

    # init stateful root (which is also configuration dependent, so honestly, it probably should just always be on by default...)
    if v.environ('SAF_SETUP_STATEFUL', default=stateful, type_fn=ext_parse_bool):
        serial_strategy = v.environ('SAF_STATEFUL_SERIAL_STRATEGY', default=default_serial_strategy)
        if serial_strategy == 'ms':
            default_serial = now_ms()
        else:
            default_serial = None
        _init_stateful_root(v, local_name=app_name, default_stateful_root=default_stateful_root,
                            default_run_id=default_run_id, default_run_serial=default_serial, default_chdir=stateful_chdir,
                            stateful_root_env_key=stateful_root_env_key)

    return v


def log_module_versions(v: Variables):
    """
    Log __version__ variables for modules in sys.modules as INFO statement
    """
    from sys import modules

    logger = get_logger(v)
    module_versions = {name: getattr(module, '__version__', None) for name, module in modules.copy().items()
                       if hasattr(module, '__version__')}
    logger.info('module versions = %s', module_versions)

    return


_lmv = log_module_versions


# noinspection PyShadowingNames
def log_framework_variables(v: Variables = None, prefixes: str | Iterable[str] = (), exclude_prefixes: str | Iterable[str] = (),
                            log_module_versions: bool = False, **kwargs):
    """
    Function to log framework variables. By default, logs all variables. Can be filtered by only including specified prefixes
    or excluding specified prefixes. The framework variables will be logged as an INFO statement.

    :param v: variables instance (None for default instance)
    :param prefixes: iterable of str prefixes to include (all included if not specified)
    :param exclude_prefixes: iterable of str prefixes to exclude (none excluded if not specified)
    :param log_module_versions: whether this function should also call log_module_versions. This was used at some point, but is now
                                deprecated. The default is False and you can elect to log module versions if you want as a separate
                                decision.
    :param kwargs: kwargs are intended to be part of differentiating this application from others (e.g. ID, symbol, etc.)
    """
    if v is None:
        v = _get_default_vars_instance()
    # developer convenience functionality to support a single prefix for either of those options
    if isinstance(prefixes, str):
        prefixes = (prefixes,)
    if isinstance(exclude_prefixes, str):
        exclude_prefixes = (exclude_prefixes,)

    logger = get_logger(v)
    result = {k: '(redacted)' if any(x in k.lower() for x in ('password', 'secret', 'credentials', 'token',)) else val
              for (k, val) in sorted(v.export_all_variables().items(), key=lambda kv: kv[0])
              if not ((k.startswith('=|') and k.endswith('|')) or any(k.startswith(x) for x in exclude_prefixes)) and
              (not prefixes or any(k.startswith(x) for x in prefixes))}
    # TODO: more complex/thorough code to identify material that should be redacted
    logger.info('framework variables%s = %s', kwargs, result)

    # experimental: include logging module versions
    if log_module_versions:
        _lmv(v)

    return


def go_sigterm_yourself():
    # Send SIGTERM signal to the own process
    os.kill(os.getpid(), signal.SIGTERM)
