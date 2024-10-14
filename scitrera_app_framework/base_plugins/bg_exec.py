from __future__ import annotations

from logging import Logger
from botwinick_utils.platforms.bg_threads import JobExecutorEngine, DEFAULT_BG_THREADS
from scitrera_app_framework.api import Plugin, Variables

EXT_BACKGROUND_EXEC = '__bg_exec'


class BackgroundThreadExecutorPlugin(Plugin):
    eager = False

    def extension_point_name(self, v: Variables) -> str:
        return EXT_BACKGROUND_EXEC

    def initialize(self, v: Variables, logger: Logger) -> object | None:
        threads = v.environ('SAF_JOB_THREADS', default=DEFAULT_BG_THREADS, type_fn=int)

        engine = JobExecutorEngine(max_workers=threads, name='SAF Job Executor')
        return engine

    def shutdown(self, v: Variables, logger: Logger, value: object | None) -> None:
        engine = self.get_my_extension(v)  # type: JobExecutorEngine
        if engine:
            engine.shutdown(wait=False, cancel_pending=True)

        return
