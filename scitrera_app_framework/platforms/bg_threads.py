"""
Pass-thru import for botwinick_utils.platforms.bg_threads

Importing through scitrera-app-framework registers `bg_exec_shutdown` as a shutdown function
"""
from botwinick_utils.platforms.bg_threads import *
from ..core import register_shutdown_function

register_shutdown_function(bg_exec_shutdown)
