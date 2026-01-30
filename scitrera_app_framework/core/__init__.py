from .core import (
    register_shutdown_function, get_logger, get_working_path, init_framework, get_variables,
    log_framework_variables, is_stateful_ready, load_strategy
)
from .plugins import (
    get_extension, register_plugin, init_all_plugins, shutdown_all_plugins,
    set_extension, get_extensions,
    async_plugins_ready, async_plugins_stopping, schedule_async_shutdown,
    capture_async_loop, get_captured_async_loop, clear_async_loop_ref,
    set_async_auto_enabled,
)
