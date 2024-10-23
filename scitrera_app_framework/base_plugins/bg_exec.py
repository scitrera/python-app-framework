from __future__ import annotations

from logging import Logger
from botwinick_utils.platforms import bg_threads
from scitrera_app_framework.api import Plugin, Variables, ext_parse_bool

EXT_BACKGROUND_EXEC = '__bg_exec'
JobExecutorEngine = bg_threads.JobExecutorEngine


class BackgroundThreadExecutorPlugin(Plugin):
    eager = False

    def extension_point_name(self, v: Variables) -> str:
        return EXT_BACKGROUND_EXEC

    def initialize(self, v: Variables, logger: Logger) -> object | None:
        threads = v.environ('SAF_JOB_THREADS', default=bg_threads.DEFAULT_BG_THREADS, type_fn=int)
        log_collisions_as_info = v.environ('SAF_JOB_COLLISIONS_INFO', default=False, type_fn=ext_parse_bool)

        # override default logger to use shorter name
        bg_threads._logger = self.get_logger(v)
        engine = bg_threads.JobExecutorEngine(max_workers=threads, name='SAF Job Executor', thread_name_prefix='saf-bg-exec',
                                              log_collisions_as_info=log_collisions_as_info)
        return engine

    def shutdown(self, v: Variables, logger: Logger, value: object | None) -> None:
        engine = self.get_my_extension(v)  # type: JobExecutorEngine
        if engine:
            engine.shutdown(wait=False, cancel_pending=True)

        return
