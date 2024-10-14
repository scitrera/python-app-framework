from .core import (register_shutdown_function, get_logger, get_working_path, init_framework, )
from .plugins import (get_extension, register_plugin, init_all_plugins, )

from botwinick_utils.platforms import bg_threads

register_shutdown_function(bg_threads.bg_exec_shutdown)
