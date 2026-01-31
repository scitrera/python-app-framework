# scitrera-app-framework

Common code and utilities for Scitrera applications and container images.

This package provides a lightweight application framework for Python services, CLIs, and desktop apps. It centers on a
small environment/variables abstraction, structured logging, a simple plugin system, optional stateful working
directories, and helper utilities for background execution, multi‑tenant configuration, and integration with external
tools like Pyroscope.

> Note: This repository is being gradually opened and updated. Expect incremental improvements and additional docs
> as code is moved from private projects.

## Stack and Packaging

- Language: Python (>= 3.9)
- Dependencies (runtime):
    - botwinick-utils (>= 0.0.20)
    - vpd
    - python-json-logger (>= 4.0.0)
- Optional/dev dependencies:
    - python-dotenv (for loading .env files via `add_env_file_source`)

## Overview

Key capabilities:

- Variables and configuration abstraction with layered sources and ergonomic access.
- Structured logging integration with simple JSON formatting option.
- Plugin and extension registry supporting both single and multi-extension modes, with optional async lifecycle hooks.
- Optional stateful working directory management (e.g., for containerized or desktop apps).
- Background execution plugin backed by thread pool.
- Optional profiling integration via Pyroscope plugin.
- Multi-tenant configuration helper with pluggable provider.
- Convenience utilities for desktop apps and test harnesses.

## Requirements

- Python 3.9+
- OS: Windows, macOS, Linux (framework is OS-independent; some optional pieces may differ by platform)

## Installation

Choose one of the following:

- From source (editable):
    - `pip install -e .`
    - or install runtime deps only: `pip install -r requirements.txt`

- From PyPI:
    - `pip install scitrera-app-framework`

## Quick Start

Initialize the framework at the start of your program and get a logger:

```python
from scitrera_app_framework import init_framework, get_logger

if __name__ == '__main__':
    v = init_framework('my-app', log_level='INFO')
    logger = get_logger(v)
    logger.info('Hello from SAF!')

    logger2 = get_logger(v, name='child')
    logger2.info('Hello from SAF child logger!')
```

Enable base plugins (e.g., background execution) and submit a job:

```python
from scitrera_app_framework import init_framework, get_extension
from scitrera_app_framework.base_plugins import EXT_BACKGROUND_EXEC

init_framework('my-app', base_plugins=True)
get_extension(EXT_BACKGROUND_EXEC).submit_job(print, 'background task')
```

Multi-tenant example:

```python
from scitrera_app_framework import init_framework, get_logger
from scitrera_app_framework.ext_plugins.multi_tenant import get_tenant_variables

v = init_framework('my-app', log_level='DEBUG', multitenant=True)

# Obtain per-tenant Variables and a logger
tenant_v = get_tenant_variables('tenant1', v=v)
tenant_logger = get_logger(tenant_v)
tenant_logger.info('tenant-specific log')
```

List plugins for a multi-extension point (from tests):

```python
from scitrera_app_framework import init_framework, register_plugin, get_extensions
from scitrera_app_framework.api import Plugin, Variables

EXT = 'example-ext'


class ImplA(Plugin):
    def extension_point_name(self, v: Variables):
        return EXT

    def is_multi_extension(self, v: Variables):
        return True

    def initialize(self, v, logger):
        return 'A'


class ImplB(ImplA):
    def initialize(self, v, logger):
        return 'B'


init_framework('my-app')
register_plugin(ImplA)
register_plugin(ImplB)
print(get_extensions(EXT))  # ['A', 'B']
```

Async plugin lifecycle (for asyncio applications):

```python
import asyncio
from scitrera_app_framework import init_framework, register_plugin, shutdown_all_plugins
from scitrera_app_framework.core import async_plugins_ready, async_plugins_stopping
from scitrera_app_framework.api import Plugin, Variables

class AsyncDatabasePlugin(Plugin):
    def extension_point_name(self, v):
        return 'database'

    def initialize(self, v, logger):
        self._pool = None
        return {'host': v.environ('DB_HOST', default='localhost')}

    async def async_ready(self, v, logger, value):
        """Called after init - establish async connections."""
        # self._pool = await create_pool(...)
        logger.info('Database pool ready')

    async def async_stopping(self, v, logger, value):
        """Called before shutdown - graceful async cleanup."""
        # if self._pool: await self._pool.close()
        logger.info('Database pool closed')

async def main():
    v = init_framework('async-app')
    register_plugin(AsyncDatabasePlugin, v, init=True)

    await async_plugins_ready(v)  # Calls async_ready on all plugins
    try:
        # Run your async application
        await asyncio.sleep(1)
    finally:
        await async_plugins_stopping(v)  # Calls async_stopping
        shutdown_all_plugins(v)

asyncio.run(main())
```

See `docs/async_plugins.md` for full documentation on automatic vs manual async handling modes.

## Entry Points and Scripts

- Primary usage is as a Python library you import into your own application.
- Utilities under `scitrera_app_framework/slaunch/` provide helpers for launching and managing environments (e.g.,
  conda), but are not wired as direct CLIs. You can import and call functions like `slaunch.main.launch_app(...)` from
  your code.

## Key Modules and APIs

- `scitrera_app_framework.init_framework(...)`: main initialization; sets up logging, stateful paths, and shutdown hooks
  based on env/kwargs.
- `init_framework_desktop(...)`: desktop-friendly defaults (e.g., use `~/.config/<APP_NAME>` and atexit hooks).
- `init_framework_test_harness(...)`: testing-friendly defaults (DEBUG logging, no shutdown hooks/stateful).
- `init_framework_embedded(...)`: use when embedding within larger apps; avoids overriding external logging.
- `get_logger(v=None, name=None)`: get the main or child logger.
- `get_working_path(v=None, default='.', env_key='DATA_WORKING_PATH')`: resolve a working path from env/stateful.
- Plugin system:
    - `register_plugin(PluginType, v=None, init=False)`
    - `get_extension(ext_name_or_type, v=None)` for single extension
    - `get_extensions(ext_name_or_type, v=None)` for multi-extension
    - Plugin lifecycle hooks:
        - `on_registration(v)` – called once when plugin is first registered (before initialization)
        - `initialize(v, logger)` – main initialization, returns extension point value
        - `shutdown(v, logger, value)` – cleanup on shutdown
    - Async lifecycle (for asyncio apps):
        - `async_plugins_ready(v)` – call `async_ready()` on all plugins
        - `async_plugins_stopping(v)` – call `async_stopping()` on all plugins
        - `set_async_auto_enabled(enabled, v)` – enable/disable automatic async handling
    - Built-ins:
        - Background executor: `EXT_BACKGROUND_EXEC` and `get_background_exec()`
        - Pyroscope profiling: `ext_plugins.pyroscope_plugin.PyroscopePlugin`
        - Multi-tenant: `ext_plugins.muti_tenant.MultiTenantPlugin`
- Env file support: `scitrera_app_framework.core.util.add_env_file_source(".env")` (requires `python-dotenv`).

## Environment Variables

Common environment variables recognized by the framework and plugins:

Core and logging:

- `APP_NAME`: Override computed application name.
- `BUILD_IMAGE_NAME`: Image name for logging context (default: base app name).
- `BUILD_CONTAINER_VERSION`: Version string (default: `DEV`).
- `LOGGING_LEVEL`: Log level (default from `init_framework(log_level=...)`).
- `LOGGING_FORMAT`: `'json'` for JSON logs or a Python `%`-format string. Otherwise uses a sensible default.
- `LOGGING_DATE_FORMAT`: Date/time format string.
- `SAF_ENABLE_PYTHON_FAULT_HANDLER`: Enable Python `faulthandler` (default True unless overridden by `init_framework`).
- `SAF_INSTALL_SHUTDOWN_HOOKS`: Install shutdown hooks (default True unless overridden).
- `SAF_SHUTDOWN_HOOK_VIA_ATEXIT`: Prefer atexit-based hooks (default depends on context; `init_framework_desktop` uses
  True).

Stateful and paths:

- `SAF_SETUP_STATEFUL`: Enable stateful working directory setup (default True unless overridden).
- `STATEFUL_ROOT`: Root directory for stateful data (default: `./scratch` unless overridden by `init_framework`).
- `RUN_ID`: Used in stateful path composition.
- `RUN_SERIAL`: Used in stateful path composition; may be auto-set when `SAF_STATEFUL_SERIAL_STRATEGY=ms`.
- `SAF_STATEFUL_CHDIR`: Change working directory into the stateful path (default True for base; False in desktop
  helper).
- `SAF_STATEFUL_SERIAL_STRATEGY`: e.g., `ms` to use current time in milliseconds.
- `DATA_WORKING_PATH`: When set, overrides `get_working_path()` resolution.

Background executor plugin:

- `SAF_JOB_THREADS`: Max worker threads (default from botwinick-utils).
- `SAF_JOB_COLLISIONS_INFO`: Log job collisions as info (default False).

Pyroscope plugin:

- `PYROSCOPE_ENABLED`: Enable plugin (also controllable via `init_framework(pyroscope=True)` defaulting).
- `PYROSCOPE_SERVER`: Server address (default `http://pyroscope.pyroscope.svc:4040`).
- `PYROSCOPE_USER`: Basic auth user (default empty).
- `PYROSCOPE_TOKEN`: Basic auth password/token (default empty).
- `PYROSCOPE_TENANT`: Tenant ID (default empty).
- `PYROSCOPE_SAMPLE_RATE`: Sample rate (int, default 100).
- `PYROSCOPE_DETECT_SUBPROCESSES`: Detect subprocesses (bool, default True).
- `PYROSCOPE_ON_CPU`: CPU profiling (bool, default True).
- `PYROSCOPE_GIL_ONLY`: GIL-only profiling (bool, default True).
- `PYROSCOPE_ENABLE_LOGGING`: Enable Pyroscope client logging (bool, default False).
- `PYROSCOPE_TAG_*`: Any variables with this prefix are turned into Pyroscope tags.

Multi-tenant plugin:

- `SAF_MULTITENANT_ENABLED`: Enable multi-tenant plugin.
- `SAF_MULTITENANT_PROVIDER`: Python import path for provider type (default is the built-in `BaseMultiTenantProvider`).
- `SAF_MULTITENANT_INCLUDE_ENV`: If True, include process env in tenant Variables placement (EnvPlacement.BOTTOM).

## Slaunch utilities (conda/python helpers)

Located under `scitrera_app_framework/slaunch/` with functions for:

- Creating and updating conda environments (apply conda/pip requirements).
- Launching apps with manifests of libs/apps and self-update support.
- Windows/macOS/Linux support via platform detection.

These are utility functions intended to be imported and used by your own launcher scripts. There is no direct CLI entry
point defined in this package.

## Kubernetes utilities (k8s.util)

The module `scitrera_app_framework.k8s.util` contains small, practical helpers for working with Kubernetes objects.
These are useful when building simple operators or orchestrating activities from Python in a K8s environment.

- Completely optional and separate from the core framework; nothing depends on them by default.
- Requires the Kubernetes Python client (and uses utilities from `vpd`). Install with: `pip install kubernetes`.
- Functions work with either plain dicts (YAML loaded) or Kubernetes client objects where noted.

Highlights:

- `apply_yaml_object(obj, verb='apply'|'get'|'replace')`: Apply/get/replace a K8s object (TODO: describe server-side vs
  client-side apply).
- `parse_yaml(path_or_text)`: Parse YAML into Python objects (dicts). Handy for loading manifests.
- `start_pod(pod_def, wait=True, replace=False, wait_delay=0.25, wait_until_terminated=False)`: Create or replace a Pod
  and optionally wait until Running (or Terminated).
- `is_pod_running(pod_def, strict=False)`: Check if a Pod is Running (or Pending when `strict=False`).
- `is_pod_in_terminated_state(pod_def)`: Check if a Pod finished (Succeeded or Failed).
- `pod_exists(pod_def)`: Determine if a Pod currently exists.
- `get_pod_env(pod_def, container_name=None, container_index=0)`: Get a reference to a container's `env` list for
  in-place edits.
- `merge_env_vars(env, *complex_items, key_upper=True, **fixed_pairs)`: Merge environment variable definitions (supports
  complex `valueFrom` entries and simple key=value pairs). Modifies list in-place.
- `fixed_env_vars(**pairs)`: Build fixed env var entries from kwargs.
- `get_metadata_name(obj)`, `get_metadata_namespace(obj)`: Extract metadata fields from dicts or client objects.
- `get_headless_service_dns_name_for_pod(pod_def, svc_def)`: Compose the DNS name `<pod>.<service>.<namespace>.svc` for
  a headless Service.

Example: launch a Pod from YAML and wait until it runs

```python
from scitrera_app_framework.k8s.util import parse_yaml, start_pod, is_pod_running

pod = parse_yaml('pod.yaml')
start_pod(pod, wait=True)
print('running?', is_pod_running(pod, strict=True))
```

Example: add env vars to the first container of a Pod manifest before applying

```python
from scitrera_app_framework.k8s.util import parse_yaml, get_pod_env, merge_env_vars, apply_yaml_object

pod = parse_yaml('pod.yaml')
env = get_pod_env(pod)
merge_env_vars(env, {'name': 'CONFIG_PATH', 'valueFrom': {'configMapKeyRef': {'name': 'my-cm', 'key': 'cfg'}}},
               IMAGE_TAG='v1.2.3', DEBUG=True)
apply_yaml_object(pod)  # apply modified manifest
```

Note: These helpers assume your local environment is configured to talk to a cluster (e.g., `KUBECONFIG` or in-cluster
config).

## Project Structure

- `scitrera_app_framework/` – Library code
    - `api/` – Variables and Plugin base types
    - `core/` – Initialization, logging, stateful paths, plugin registry (not intended to be used directly by users)
    - `base_plugins/` – Built-in optional plugins (e.g., background executor)
    - `ext_plugins/` – Optional extensions (e.g., Pyroscope, Multi-tenant)
    - `k8s/` - Optional Kubernetes Utilities
    - `slaunch/` – "slaunch" is a white-label ready set of utilities to maintain structured conda environments and
      applications with auto-updating on start, etc.
    - `util/` – Miscellaneous helpers (async, parsing, imports)
- `setup.py` – Build configuration
- `requirements.txt` – Development/runtime dependencies list
- `LICENSE.txt` – BSD 3‑Clause license text

## License

BSD 3‑Clause License. See `LICENSE.txt` for details.

## Contributing

- Issues and PRs are welcome. Please keep changes small and focused.