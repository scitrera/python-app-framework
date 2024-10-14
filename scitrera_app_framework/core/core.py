from __future__ import annotations

import os
import importlib
import faulthandler
import logging
import sys
import signal
# from time import sleep
from os import chdir, makedirs, path as osp

from botwinick_utils.util import LOGGING_FORMAT, LOGGING_DATE_FORMAT

from ..util import ext_parse_bool
from ..api.variables import Variables

_sigterm_hooks = []

_default_vars_inst = None

# variables for standardized internal names
_VAR_APP_STATEFUL_ROOT = '_app_state_root'
_VAR_APP_STATEFUL_READY = '_app_state_ready'
_VAR_MAIN_LOGGER = '_main_logger'


def _get_default_vars_instance():
    global _default_vars_inst
    if _default_vars_inst is None:
        _default_vars_inst = Variables()
    return _default_vars_inst


# noinspection PyCompatibility
def register_shutdown_function(fn, *args, **kwargs):
    _sigterm_hooks.append((fn, args, kwargs))


def install_signal_hooks(v: Variables = None, via_at_exit=True):
    if v is None:
        v = _get_default_vars_instance()

    logger = get_logger(v)

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


def get_logger(v: Variables = None, logger=None, name=None):
    if v is None:
        v = _get_default_vars_instance()

    if logger is None and name is None:
        logger = v.get(_VAR_MAIN_LOGGER)
        if logger is None:
            # TODO: save main logger?
            logger = logging.getLogger('main')
    elif logger is None and name is not None:
        return logging.getLogger(name)
    elif name is not None:
        return logger.getChild(name)
    return logger


def _init_pyroscope_profiling(v: Variables = None, app_name=None, **tags):
    if v is None:
        v = _get_default_vars_instance()

    logger = get_logger(v)
    logger.info('Initializing Pyroscope Profiling')

    try:
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        import pyroscope

        app_name = app_name or v.get('APP_NAME')
        tags.update({
            'app_name': app_name,
            'run_id': v.environ('RUN_ID', default='msa'),
        })
        # append tags from environments variables in the form:
        # PYROSCOPE_TAG_TAGX=VALUE_X --> TAGX=VALUE_X
        tags.update(v.import_from_env_by_prefix('PYROSCOPE_TAG'))

        pyroscope.configure(
            application_name=app_name,
            server_address=v.environ('PYROSCOPE_SERVER', default='http://pyroscope.pyroscope.svc:4040'),
            basic_auth_username=v.environ('PYROSCOPE_USER', default=''),
            basic_auth_password=v.environ('PYROSCOPE_TOKEN', default=''),
            tenant_id=v.environ('PYROSCOPE_TENANT', default=''),
            sample_rate=v.environ('PYROSCOPE_SAMPLE_RATE', type_fn=int, default=100),
            detect_subprocesses=v.environ('PYROSCOPE_DETECT_SUBPROCESSES', type_fn=ext_parse_bool, default=True),
            oncpu=v.environ('PYROSCOPE_ON_CPU', type_fn=ext_parse_bool, default=True),
            gil_only=v.environ('PYROSCOPE_GIL_ONLY', type_fn=ext_parse_bool, default=True),
            enable_logging=v.environ('PYROSCOPE_ENABLE_LOGGING', type_fn=ext_parse_bool, default=False),
            tags=tags,
        )

    except ImportError as e:
        logger.warning('Pyroscope was not able to be initialized: %s', e)

    return


def _init_logging(logger_name, level='INFO', formatter=None):
    log_level = logging.getLevelName(level.upper())
    logging.root.setLevel(log_level)

    logging.root.handlers.clear()
    handler = logging.StreamHandler()
    if formatter is not None:
        handler.setFormatter(formatter)
    logging.root.addHandler(handler)

    logger = logging.getLogger(logger_name)
    return logger


def _log_fmt_json(**static_fields):
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


def _init_stateful_root(v: Variables, local_name=None, default_stateful_root='./scratch', default_run_id=None, default_run_serial=None):
    logger = get_logger(v)

    if local_name is None:
        local_name = v.get('APP_NAME')

    # setup working directory for application state if available
    state_root = v.environ('STATEFUL_ROOT', default=default_stateful_root)
    if not osp.exists(state_root):
        logger.info('state_root "%s" does not exist. aborting stateful setup', state_root)
        return

    # use run_id and run_serial with local_name to determine path
    run_id = v.environ('RUN_ID', default=default_run_id)
    run_serial = v.environ('RUN_SERIAL', default=default_run_serial)
    app_state_root = osp.join(state_root, *filter(None, (run_id, run_serial, local_name)))
    v.set(_VAR_APP_STATEFUL_ROOT, app_state_root)

    # makedirs as needed and set working directory to stateful root
    logger.info('app stateful root=%s', app_state_root)
    makedirs(app_state_root, exist_ok=True)
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
    if v.get(_VAR_APP_STATEFUL_READY):  # should be True or None
        return v.get(_VAR_APP_STATEFUL_ROOT)  # if ready, we expect this to be a defined value
    return None


def load_python_type_by_name(type_name, expected_parent_type):  # TODO: move upstream?
    if not type_name:
        raise ValueError('Invalid type_name')

    # TODO: better to handle errors or to just not and let them bubble up naturally
    parts = type_name.split('.')
    pkg = '.'.join(parts[:-1])
    name = parts[-1]

    pkg = importlib.import_module(pkg)
    strategy_type = getattr(pkg, name)
    if issubclass(strategy_type, expected_parent_type):
        return strategy_type

    raise ValueError('given type name does not match expected type')


def load_strategy(v: Variables, parent_type, prefix='STRATEGY'):
    # dynamic strategy loading and configuration
    strategy_kwargs = v.import_from_env_by_prefix(prefix)
    strategy_type_name = strategy_kwargs.pop('type', None)

    try:
        strategy = load_python_type_by_name(strategy_type_name, parent_type)
    except (ValueError, ImportError) as e:
        get_logger(v).error('unable to load strategy "%s": %s', strategy_type_name, e)
        strategy = None

    return strategy, strategy_kwargs


def get_working_path(v: Variables = None, default='.', env_key='DATA_WORKING_PATH'):
    """
    Opinionated function to get working path;
    resolution order:
    1) ENVIRONMENT VARIABLE for env_key
    2) STATEFUL ROOT derived location (if available)
    3) given default to this function

    :param v: framework env/variables object
    :param default: fallback working path (default is '.')
    :param env_key: environment key for working path override (first priority) value
    :return:
    """
    if v is None:
        v = _get_default_vars_instance()
    stateful_ready_root = is_stateful_ready(v)
    return v.environ(env_key, default=stateful_ready_root if stateful_ready_root is not None else default)


def init_framework(base_app_name: str, v: Variables = None, pyroscope=False, shutdown_hooks=True, stateful=True,
                   default_stateful_root='./scratch', fixed_logger=None, log_format=None, log_level='INFO', fault_handler=True, sep='-',
                   unnamed_params=(), **params):
    """
    Initialize the Scitrera Application Framework. This should be the first thing to be called in a "main" function
    for an application or container entrypoint.

    :param base_app_name: hard-coded base application name
    :param v: an optional variables instance (a default instance will be provided and managed if None)
    :param pyroscope: whether the default functionality is to initialize pyroscope (env variable will override this)
    :param shutdown_hooks: whether the default functionality is to install shutdown hooks (env variable will override this)
    :param stateful: whether the default functionality is to try to install stateful functionality (env variable will override this)
    :param default_stateful_root: the default stateful root if not provided by env variable
    :param fixed_logger: a predefined logger. Only use this in advanced usage when the framework is not at the center of the application.
    :param log_format: either 'json' to log following json message per line convention to facilitate log aggregation
                        or a %-style log format string.
    :param log_level: the default log level if not set by env variable.
    :param fault_handler: whether the default functionality is to try to install the python fault handler (env variable will override this)
    :param sep: the default separator used when constructing a longer, more complex app name based on given parameters
    :param unnamed_params: an iterable (tuple) containing parameters that should not be included in the app name
    :param params: additional parameters to include as part of app name, pyroscope tagging, etc.
    :return: variables instance for the framework
    """
    # init variables framework
    if v is None:
        v = _get_default_vars_instance()

    # normalize parameters map w/ environment fallback values
    param_map = {k.lower(): v.environ(k.upper(), default=val) for k, val in params.items()}

    # install python fault handler
    if v.environ('SAF_ENABLE_PYTHON_FAULT_HANDLER', default=fault_handler, type_fn=ext_parse_bool):
        faulthandler.enable()

    # determine app name with suffixes attached
    name_ = base_app_name
    name_params = [n for n in param_map.keys() if n not in unnamed_params]
    if len(name_params) > 0:
        name_ += sep + sep.join((str(param_map[n]) for n in name_params))
    app_name = v.environ('APP_NAME', default=name_)
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
        logger = v.set(_VAR_MAIN_LOGGER, _init_logging(app_name, level=v.environ('LOGGING_LEVEL', default=log_level), formatter=fmt))
        if build_container_version != 'DEV':
            logger.info('Initializing %s; container=%s, version=%s', app_name, build_image_name, build_container_version)
        else:
            logger.info('Initializing %s', app_name)
    else:
        logger = v.set(_VAR_MAIN_LOGGER, fixed_logger)

    # install signal shutdown hooks (must be on MainThread)
    if v.environ('SAF_INSTALL_SHUTDOWN_HOOKS', default=shutdown_hooks, type_fn=ext_parse_bool):
        install_signal_hooks(v)  # TODO: make atexit vs signal handler configurable?

    # do pyroscope init -- built in support for pyroscope profiling
    if v.environ('SAF_SETUP_PYROSCOPE', default=pyroscope, type_fn=ext_parse_bool):
        _init_pyroscope_profiling(v, app_name=base_app_name, **param_map)

    # init stateful root (which is also configuration dependent, so honestly, it probably should just always be on by default...)
    if v.environ('SAF_SETUP_STATEFUL', default=stateful, type_fn=ext_parse_bool):
        _init_stateful_root(v, local_name=app_name, default_stateful_root=default_stateful_root)

    return v


def log_module_versions(v: Variables):
    from sys import modules

    logger = get_logger(v)
    module_versions = {name: getattr(module, '__version__', None) for name, module in modules.copy().items()
                       if hasattr(module, '__version__')}
    logger.info('module versions = %s', module_versions)

    return


_lmv = log_module_versions


# noinspection PyShadowingNames
def log_framework_variables(v: Variables, log_module_versions=True, **kwargs):
    logger = get_logger(v)
    # TODO: more complex/thorough code to identify material that should be redacted
    logger.info('framework variables%s = %s', kwargs,
                {k: '(redacted)' if ('password' in k.lower() or 'secret' in k.lower()) else val
                 for (k, val) in v.export_all_variables().items()})

    # experimental: include logging module versions
    if log_module_versions:
        _lmv(v)

    return


def go_sigterm_yourself():
    # Send SIGTERM signal to the own process
    os.kill(os.getpid(), signal.SIGTERM)
