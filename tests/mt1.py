from scitrera_app_framework import (init_framework, get_logger)
from scitrera_app_framework.core import log_framework_variables

if __name__ == '__main__':
    v = init_framework('test-app-mt1', log_level='DEBUG', multitenant=True)
    log_framework_variables(v)

    # # enable multi-tenant with default local provider
    # from scitrera_app_framework.ext_plugins.muti_tenant import MultiTenantPlugin, get_tenant_variables, ENV_MULTITENANT_ENABLED
    #
    # v.set(ENV_MULTITENANT_ENABLED, True)
    # register_plugin(MultiTenantPlugin, v=v, init=True)

    from scitrera_app_framework.ext_plugins.muti_tenant import get_tenant_variables

    t1 = get_tenant_variables('tenant1', v=v)
    l1 = get_logger(t1)
    t2 = get_tenant_variables('tenant2', v=v)
    l2 = get_logger(t2)

    t1.environ('REDIS_HOST', default='t1host')
    t2.environ('REDIS_HOST', default='t2host')

    l1.info('---- tenant1 ----')
    log_framework_variables(t1)

    l2.info('---- tenant2 ----')
    log_framework_variables(t2)

    t1 = get_tenant_variables('tenant1', v=v)
    t2 = get_tenant_variables('tenant2', v=v)

    l1.info('---- tenant1 ----')
    log_framework_variables(t1)

    l2.info('---- tenant2 ----')
    log_framework_variables(t2)
