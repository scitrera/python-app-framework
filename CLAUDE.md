# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scitrera Application Framework (SAF) is a lightweight Python application framework for services, CLIs, and desktop apps. It provides:
- Environment/variables abstraction with layered sources and ergonomic access
- Structured logging with JSON formatting option
- Simple plugin/extension system supporting dependency injection and OSGi-style multi-extensions
- Optional stateful working directory management
- Background execution, multi-tenant configuration, and Pyroscope profiling plugins

## Development Commands

```bash
# Install (editable)
pip install -e .

# Install test dependencies
pip install pytest pytest-cov python-dotenv

# Run full test suite
pytest tests/ -v

# Run a single test file
pytest tests/test_api_variables.py -v

# Run a single test
pytest tests/test_api_variables.py::TestVariablesBasic::test_set_and_get -v

# Run with coverage
pytest tests/ --cov=scitrera_app_framework --cov-report=term-missing

```

## Architecture

### Core Initialization Flow

1. `init_framework(app_name)` → creates/returns a `Variables` instance
2. Logging is configured (JSON or %-format based on `LOGGING_FORMAT`)
3. Stateful paths optionally set up under `STATEFUL_ROOT`
4. Shutdown hooks registered (SIGTERM or atexit)
5. Plugins registered and initialized

Alternate init functions with different defaults:
- `init_framework_desktop()` – uses `~/.config/$APP_NAME`, atexit hooks
- `init_framework_test_harness()` – DEBUG logging, no stateful/shutdown
- `init_framework_embedded()` – avoids overriding external logging config

### Variables System (`api/variables.py`)

The `Variables` class is the central configuration container. It searches sources in priority order:
1. Process environment (`os.environ` with uppercase keys)
2. Local settings (`v.set()`)
3. Additional sources added via `v.add_source()`
4. Fallback defaults

Key methods:
- `v.environ(key, default=, type_fn=)` – get with default/type registration
- `v.set(key, value)` – set local value
- `v.get_by_prefix(prefix)` – extract namespaced config as dict (useful for kwargs)
- `v.import_from_env_by_prefix(prefix)` – import env vars matching prefix

`EnvPlacement` enum controls where environment appears in search order (TOP, BOTTOM, BOTTOM2, IGNORED).

### Plugin System (`api/plugins.py`, `core/plugins.py`)

Plugins implement the `Plugin` abstract class:
- `extension_point_name(v)` – the named slot this plugin fills
- `is_enabled(v)` – for single-extension mode (dependency injection)
- `is_multi_extension(v)` – for OSGi-style multiple implementations
- `get_dependencies(v)` – list of extension points that must init first
- `initialize(v, logger)` – returns the extension value
- `shutdown(v, logger, value)` – cleanup

Registration:
```python
register_plugin(MyPlugin, v, init=True)  # register and initialize
value = get_extension('ext-name', v)     # single extension
values = get_extensions('ext-name', v)   # multi-extension (returns dict)
```

Built-in plugins:
- `EXT_BACKGROUND_EXEC` – thread pool via `get_background_exec()`
- `EXT_PROGRESS_TRACKER` – progress tracking for UIs

### Package Layout

```
scitrera_app_framework/
├── api/           # Variables and Plugin base types (public API)
├── core/          # Framework init, logging, plugin registry (internal)
├── base_plugins/  # Built-in optional plugins (bg_exec, progress_tracker)
├── ext_plugins/   # Optional extensions (pyroscope, multi-tenant)
├── k8s/           # Kubernetes utilities (apply_yaml_object, start_pod, etc.)
├── slaunch/       # Conda environment management and app launching utilities
└── util/          # Parsing, imports, async helpers (no api/core deps)
```

## Code Conventions

- Internal framework variables use "epp" keys: `=|name|` (equal-pipe-pipe pattern)
- Type functions for environment parsing: `ext_parse_bool`, `ext_parse_csv`, `ext_get_python`
- Use lazy string formatting in logging: `logger.debug("item: %s", item)` not f-strings
- The `v` parameter is conventionally the Variables instance; `None` uses the default singleton

## Key Environment Variables

Core:
- `APP_NAME` – override computed app name
- `LOGGING_LEVEL` – log level (default from init kwarg)
- `LOGGING_FORMAT` – `'json'` for JSON logs, or a %-format string

Stateful:
- `STATEFUL_ROOT` – root directory for stateful data (default: `./scratch`)
- `SAF_SETUP_STATEFUL` – enable/disable stateful features
- `SAF_STATEFUL_CHDIR` – whether to chdir into stateful path

Plugins:
- `SAF_BASE_PLUGINS` – auto-register base plugins
- `PYROSCOPE_ENABLED` – enable Pyroscope profiling
- `SAF_MULTITENANT_ENABLED` – enable multi-tenant plugin
