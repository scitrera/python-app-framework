from __future__ import annotations

from logging import Logger
from scitrera_app_framework.api import Plugin, Variables, ext_parse_bool
# noinspection PyProtectedMember
from scitrera_app_framework.core.core import _VAR_PARAM_MAP

EXT_PYROSCOPE = 'pyroscope'
PYROSCOPE_ENABLED = 'PYROSCOPE_ENABLED'


class PyroscopePlugin(Plugin):
    eager = True

    def extension_point_name(self, v: Variables) -> str:
        return EXT_PYROSCOPE

    def initialize(self, v: Variables, logger: Logger) -> object | None:
        logger.info('Initializing Pyroscope Profiling')

        try:
            # noinspection PyPackageRequirements,PyUnresolvedReferences
            import pyroscope

            app_name = v.get('SAF_BASE_APP_NAME')
            tags = v.get(_VAR_PARAM_MAP)

            # resume original functionality
            tags.update({
                'app_name': app_name,
                'run_id': v.environ('RUN_ID', default='msa'),
            })
            # append tags from environments variables in the form:
            # PYROSCOPE_TAG_TAGX=VALUE_X --> tagx=VALUE_X
            tags.update(v.import_from_env_by_prefix('PYROSCOPE_TAG'))

            pyroscope.configure(
                application_name=app_name,
                server_address=v.environ('PYROSCOPE_SERVER', default='http://pyroscope.pyroscope.svc:4040'),
                basic_auth_username=v.environ('PYROSCOPE_USER', default=''),
                basic_auth_password=v.environ('PYROSCOPE_TOKEN', default=''),
                # auth_token=v.environ('PYROSCOPE_TOKEN', default=''),
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
            pyroscope = None

        return pyroscope

    def is_enabled(self, v: Variables) -> bool:
        # do not set a default value here since we establish default ahead of registering plugin
        return v.environ(PYROSCOPE_ENABLED, type_fn=ext_parse_bool)

    def shutdown(self, v: Variables, logger: Logger, value: object | None) -> None:
        return
