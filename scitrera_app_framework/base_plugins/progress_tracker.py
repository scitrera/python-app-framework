from __future__ import annotations

from logging import Logger
from botwinick_utils.progress_reporting.tracker import ProgressTracker
from scitrera_app_framework.api import Plugin, Variables

EXT_PROGRESS_TRACKER = '__progress_tracker'


class ProgressTrackerPlugin(Plugin):
    eager = False

    def extension_point_name(self, v: Variables) -> str:
        return EXT_PROGRESS_TRACKER

    def initialize(self, v: Variables, logger: Logger) -> object | None:
        tracker = ProgressTracker()
        return tracker

    def shutdown(self, v: Variables, logger: Logger, value: object | None) -> None:
        return
