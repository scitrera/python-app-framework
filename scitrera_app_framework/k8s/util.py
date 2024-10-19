from time import sleep
from os import path as osp

from vpd.next.k8s.config import apply_yaml_object, parse_yaml


def get_metadata_name(k8s_object):
    if isinstance(k8s_object, dict):
        return k8s_object.get('metadata', {}).get('name', None)
    try:
        return k8s_object.metadata.name
    except AttributeError:
        return None


def get_metadata_namespace(k8s_object):
    if isinstance(k8s_object, dict):
        return k8s_object.get('metadata', {}).get('namespace', None)
    try:
        return k8s_object.metadata.namespace
    except AttributeError:
        return None


def get_headless_service_dns_name_for_pod(pod_def, service_def):
    service_name = get_metadata_name(service_def)
    namespace = get_metadata_namespace(service_def)
    pod_name = get_metadata_name(pod_def)
    return f'{pod_name}.{service_name}.{namespace}.svc'


def fixed_env_vars(key_upper=True, **kwargs):
    """
    Create list of dicts to represent fixed value kubernetes pod environment variables, populated based on
    provided kwargs.

    :param key_upper: if True (default), convert all keys (from kwargs) to upper-case
    :param kwargs: key-value pairs of environments variables
    :return: list of dicts suitable for inclusion in a k8s pod definition
    """
    return [{
        'name': k.upper() if key_upper else k,
        'value': str(v),
    } for (k, v) in kwargs.items()]


def merge_env_vars(original_pod_env=None, *args, key_upper=True, **kwargs):
    """
    Either create (or modify in-place) list of dicts to represent kubernetes pod environment variables by merging:
    1) given args (intended to be dicts that can reference fields or have more complex syntax)
    2) kwargs (key-value pairs)
    3) original pod environment variables if given

    The merger occurs following the above priority order, meaning that args override kwargs which override original environment definitions.

    :param original_pod_env: original environment (list of dicts) or None
    :param args: dicts that represent pod environment variables (that can be more complex than fixed values)
    :param key_upper: if True (default), convert all keys (from kwargs) to upper-case
    :param kwargs: key-value pairs of fixed environments variables
    :return: list of dicts suitable for inclusion in a k8s pod definition (note that if original was from a pod definition,
    then the original definition is overridden in-place)
    """
    if original_pod_env is None:
        original_pod_env = []

    new_values = fixed_env_vars(key_upper=key_upper, **kwargs) + list(args)

    result = {}
    for i in (original_pod_env + new_values):
        if i['name'] in result:
            result[i['name']].update(i)
        else:
            result[i['name']] = i

    original_pod_env.clear()
    original_pod_env.extend(result.values())

    return original_pod_env


def get_pod_env(pod_def, container_name=None, container_index=0):
    """
    get reference to env list for a given pod definition dict

    :param pod_def: pod definition dict
    :param container_name: name of container to find within pod definition or None
    :param container_index: index of container to find within pod definition (if name not specified)
    :return:
    """
    containers = pod_def.get('spec', {}).get('containers', []) if pod_def else None
    if not containers:
        return None

    # TODO: do we need to consider error handling if name is not defined?
    containers_map = {container_def['name']: i for i, container_def in enumerate(containers)}
    if container_name is not None:
        container_index = containers_map[container_name]  # ok to bubble up error if name not found

    container_def = containers[container_index]
    if 'env' not in container_def:
        env = container_def['env'] = []
    else:
        env = container_def['env']

    return env


def pod_exists(pod_def):
    return apply_yaml_object(pod_def, verb='get') is not None


def _is_running_phase(phase):
    return 'Running' == phase


def _is_not_running_phase(phase):
    return 'Running' != phase


def _is_active_phase(phase):
    return phase in ('Running', 'Pending')


def _is_terminated_phase(phase):
    return phase in ('Succeeded', 'Failed')


def _is_not_terminated_phase(phase):
    return phase not in ('Succeeded', 'Failed')


def is_pod_running(pod_def, strict=False):
    state = apply_yaml_object(pod_def, verb='get')  # get existing state
    if state is None:  # does not exist, create
        return False
    state = dict(state)
    phase = state.get('status', {}).get('phase', None)
    if strict:
        return _is_running_phase(phase)
    return _is_active_phase(phase)


def is_pod_in_terminated_state(pod_def):
    state = apply_yaml_object(pod_def, verb='get')  # get existing state
    if state is None:  # does not exist, create
        return False
    state = dict(state)
    phase = state.get('status', {}).get('phase', None)
    return _is_terminated_phase(phase)


def start_pod(pod_def, wait=True, replace=False, wait_delay=0.25, wait_until_terminated=False):
    state = apply_yaml_object(pod_def, verb='get')  # get existing state
    if state is None:  # does not exist, create
        state = apply_yaml_object(pod_def)
    elif replace:  # exists and replace option, replace
        state = apply_yaml_object(pod_def, verb='replace')
    # else: # exists and not replace option
    #     pass
    # TODO: if a pod is exited/succeeded then we need replace to make it work!

    if wait:
        state = dict(state)
        check_fn = _is_not_terminated_phase if wait_until_terminated else _is_not_running_phase
        phase = state.get('status', {}).get('phase', None)
        while check_fn(phase):
            state = dict(apply_yaml_object(pod_def, verb='get'))  # TODO: raises TypeError if obj deleted while waiting
            sleep(wait_delay)
            phase = state.get('status', {}).get('phase', None)

    return state
