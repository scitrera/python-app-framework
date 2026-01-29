from __future__ import annotations

from logging import Logger, getLogger
from typing import Iterable, Type

from scitrera_app_framework.api import Plugin, Variables, ext_parse_bool, EnvPlacement
from scitrera_app_framework.util.imports import get_python_type_by_name
from scitrera_app_framework.core.plugins import get_extension

EXT_MULTITENANT = 'multi-tenant'
ENV_MULTITENANT_ENABLED = 'SAF_MULTITENANT_ENABLED'
ENV_MULTITENANT_PROVIDER = 'SAF_MULTITENANT_PROVIDER'
ENV_MULTITENANT_INCLUDE_ENV = 'SAF_MULTITENANT_INCLUDE_ENV'


class BaseMultiTenantProvider:
    def __init__(self, root: Variables):
        self._root = root
        self._data = self._init_local_cache()

    # TODO: improve docs and typing definitions
    # noinspection PyMethodMayBeStatic
    def _init_local_cache(self):
        # anything that supports __getitem__, intended to be dict, can also be some form of TTL / LRU cache
        return {}

    # TODO: improve docs and typing definitions
    # noinspection PyMethodMayBeStatic
    def _tenant_sources(self, tenant_id: str) -> Iterable[Variables | dict]:
        # iterable of sources to be used for tenant-specific Variables instance
        return ()

    # TODO: improve docs and typing definitions
    # noinspection PyMethodMayBeStatic
    def _local_provider(self, tenant_id: str) -> Type[dict | Variables]:
        # single source to be used for "local" in tenant-specific Variables instance; if this is remote, then
        # R/W of tenant data always passes through. If this is dict/local, then reads may come from remote sources
        # if defined, but writes will go to local.
        return dict

    # noinspection PyMethodMayBeStatic
    def _subordinate_logger_name(self, tenant_id: str) -> str:
        return tenant_id

    # TODO: auth/security mechanism for getting sources/local for particular tenant_id?
    #       or leave as-is (leave to downstream/implementation details)

    def __getitem__(self, tenant_id: str):
        data = self._data
        root = self._root

        # if this tenant ID was previously requested, then we return the existing entry and avoid extra work
        if tenant_id in data:
            return data[tenant_id]

        # if we got this far, then we need to instantiate a new Variables object, so prepare configuration now
        sources = self._tenant_sources(tenant_id)
        env_placement = (
            EnvPlacement.BOTTOM
            if root.environ(ENV_MULTITENANT_INCLUDE_ENV, default=DEFAULT_MULTITENANT_INCLUDE_ENV, type_fn=ext_parse_bool)
            else EnvPlacement.IGNORED
        )
        local_provider = self._local_provider(tenant_id)

        # generate Variables instance for tenant and return
        data[tenant_id] = result = Variables(
            sources=sources,
            env_placement=env_placement,
            local_provider=local_provider
        )

        # TODO: perhaps add something to Variables to support parent references for plugin/shutdown/etc.
        #       (or just re-work how plugin shutdown is handled...)

        # TODO: basically do full init instead if we decide to support full subordinate framework instances

        # configure default logger instance for tenant as a convenience item
        #       (for now full framework init on tenant variables not supported)
        # noinspection PyProtectedMember
        from scitrera_app_framework.core.core import _VAR_MAIN_LOGGER, ENV_LOGGING_LEVEL
        logger = result.set(_VAR_MAIN_LOGGER, getLogger(self._subordinate_logger_name(tenant_id)))  # type: Logger
        # TODO: or do we want to do result.environ(ENV_LOGGING_LEVEL, default=root.environ(ENV_LOGGING_LEVEL))
        #       to allow pre-defined logging level for base logger for tenant [...depends on intent and local provider cfg...]
        logger.setLevel(root.environ(ENV_LOGGING_LEVEL))

        return result

    get = __getitem__

    pass


DEFAULT_MULTI_TENANT_PROVIDER = f"{BaseMultiTenantProvider.__module__}.{BaseMultiTenantProvider.__name__}"
DEFAULT_MULTITENANT_INCLUDE_ENV = False


class MultiTenantPlugin(Plugin):
    eager = True

    def extension_point_name(self, v: Variables) -> str:
        return EXT_MULTITENANT

    def initialize(self, v: Variables, logger: Logger) -> object | None:
        logger.debug('Initializing Multi-Tenant Support')

        provider = get_python_type_by_name(
            type_name=v.environ(ENV_MULTITENANT_PROVIDER, default=DEFAULT_MULTI_TENANT_PROVIDER),
            expected_parent_type=BaseMultiTenantProvider
        )
        return provider(v)

    def is_enabled(self, v: Variables) -> bool:
        # note: no default here; set upstream at framework init
        return v.environ(ENV_MULTITENANT_ENABLED, type_fn=ext_parse_bool)

    def shutdown(self, v: Variables, logger: Logger, value: object | None) -> None:
        return


def get_tenant_provider(v: Variables = None) -> BaseMultiTenantProvider:
    """
    Get the multitenant provider implementation from the multitenant plugin.
    """
    return get_extension(EXT_MULTITENANT, v=v)


def get_tenant_variables(tenant_id: str, v: Variables = None) -> Variables:
    """
    Use the multitenant plugin to get a Variables instance for the given tenant.
    """
    return get_extension(EXT_MULTITENANT, v=v)[tenant_id]
