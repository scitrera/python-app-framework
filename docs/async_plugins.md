# Async Plugin Lifecycle Support

This document describes how to use async lifecycle hooks in SAF plugins for applications that run within an asyncio event loop.

## Overview

SAF plugins now support optional async lifecycle hooks that integrate with the existing sync lifecycle. This enables plugins to perform async operations (database connections, HTTP sessions, background tasks) without blocking the event loop.

**Key principle:** The sync lifecycle (`initialize`/`shutdown`) remains the primary mechanism. Async hooks are additive and called when running in an async context.

## Automatic vs Manual Async Handling

SAF supports two modes for calling async lifecycle hooks:

### Automatic Mode (Fire-and-Forget)

When an event loop has been captured (via `capture_async_loop()` or `async_plugins_ready()`), async hooks are called **automatically** during plugin initialization and shutdown:

- **During `_init_plugin()`**: If a loop is captured, `async_ready()` is scheduled automatically
- **During `shutdown_all_plugins()`**: If a loop is captured, `async_stopping()` is scheduled automatically

**Thread behavior:**
- **Same thread as event loop**: Uses `loop.create_task()` (fire-and-forget, non-blocking)
- **Different thread**: Uses `run_coroutine_threadsafe().result()` (blocks until complete)

### Manual Mode (Explicit Await)

For guaranteed ordering and completion, explicitly call the async lifecycle functions:

```python
await async_plugins_ready(v)    # Awaits all async_ready() hooks
await async_plugins_stopping(v)  # Awaits all async_stopping() hooks
```

**When to use manual mode:**
- When async initialization must complete before proceeding
- When you need guaranteed ordering between plugins
- When running in a fully async application

### Idempotency

Both modes use flags (`_async_ready_called`, `_async_stopping_called`) to prevent duplicate invocations. If automatic handling runs first, manual calls will skip already-handled plugins, and vice versa.

## Lifecycle Order

```
1. register_plugin()             # Plugin instance created
2. initialize()                  # Sync init (returns extension value)
3. [AUTO] async_ready()          # If loop captured, scheduled automatically
   -or-
   await async_plugins_ready()   # Manual: awaits all async_ready() hooks
4. ... application runs ...
5. [AUTO] async_stopping()       # If loop captured, scheduled automatically
   -or-
   await async_plugins_stopping() # Manual: awaits all async_stopping() hooks
6. shutdown_all_plugins()        # Sync shutdown
   └── shutdown()                # Per-plugin sync cleanup
```

## Writing an Async-Aware Plugin

```python
from scitrera_app_framework.api import Plugin, Variables
from logging import Logger

class DatabasePlugin(Plugin):
    def extension_point_name(self, v: Variables) -> str:
        return 'database'

    def initialize(self, v: Variables, logger: Logger) -> dict:
        """Sync init: read config, prepare connection params."""
        self._config = {
            'host': v.environ('DB_HOST', default='localhost'),
            'port': v.environ('DB_PORT', default=5432, type_fn=int),
        }
        self._pool = None
        return self._config

    async def async_ready(self, v: Variables, logger: Logger, value: dict):
        """Async setup: establish connection pool."""
        import asyncpg
        self._pool = await asyncpg.create_pool(**self._config)
        logger.info('Database pool established')

    async def async_stopping(self, v: Variables, logger: Logger, value: dict):
        """Async teardown: gracefully close pool."""
        if self._pool:
            await self._pool.close()
            logger.info('Database pool closed')

    def shutdown(self, v: Variables, logger: Logger, value: dict) -> None:
        """Sync cleanup: any remaining cleanup."""
        self._pool = None
```

## Application Integration

### Manual Mode: Full Control (Recommended for Critical Apps)

Use explicit `await` calls when async initialization must complete before proceeding:

```python
import asyncio
from scitrera_app_framework.core import (
    init_framework, register_plugin, shutdown_all_plugins,
    async_plugins_ready, async_plugins_stopping,
)

async def main():
    # 1. Initialize framework (sync)
    v = init_framework('my-async-app')

    # 2. Register plugins (sync init happens here)
    register_plugin(DatabasePlugin, v, init=True)
    register_plugin(CachePlugin, v, init=True)

    # 3. Explicitly await async ready - guarantees completion before proceeding
    await async_plugins_ready(v)

    try:
        # 4. Run your application (all async resources are ready)
        await run_server()
    finally:
        # 5. Explicitly await async stopping - guarantees graceful cleanup
        await async_plugins_stopping(v)

        # 6. Sync shutdown
        shutdown_all_plugins(v)

if __name__ == '__main__':
    asyncio.run(main())
```

### Automatic Mode: Fire-and-Forget

For simpler cases where async initialization can happen in the background:

```python
import asyncio
from scitrera_app_framework.core import (
    init_framework, register_plugin, shutdown_all_plugins,
    capture_async_loop,
)

async def main():
    v = init_framework('my-async-app')

    # Capture the loop first - enables automatic async handling
    capture_async_loop(v)

    # Plugins registered after loop capture get async_ready scheduled automatically
    register_plugin(DatabasePlugin, v, init=True)  # async_ready fires in background
    register_plugin(CachePlugin, v, init=True)     # async_ready fires in background

    # Give tasks a moment to complete (or just proceed if not critical)
    await asyncio.sleep(0.1)

    try:
        await run_server()
    finally:
        # shutdown_all_plugins will schedule async_stopping automatically
        shutdown_all_plugins(v)
        await asyncio.sleep(0.1)  # Let cleanup tasks complete

if __name__ == '__main__':
    asyncio.run(main())
```

### Hybrid: Automatic with Manual Guarantee

Combine both approaches - automatic for convenience, manual for critical points:

```python
async def main():
    v = init_framework('my-async-app')
    capture_async_loop(v)

    # Register plugins - async_ready scheduled automatically (fire-and-forget)
    register_plugin(DatabasePlugin, v, init=True)
    register_plugin(CachePlugin, v, init=True)

    # Explicitly await to ensure all async_ready hooks complete
    # (Idempotent - skips any already completed by automatic handling)
    await async_plugins_ready(v)

    try:
        await run_server()
    finally:
        await async_plugins_stopping(v)  # Explicit await for clean shutdown
        shutdown_all_plugins(v)
```

### Mixed Sync/Async Environment

If your application has both sync and async components, you can still use async plugins:

```python
from scitrera_app_framework.core import (
    init_framework, register_plugin, shutdown_all_plugins,
    async_plugins_ready, async_plugins_stopping,
    schedule_async_shutdown, capture_async_loop,
)

def main():
    v = init_framework('mixed-app')
    register_plugin(DatabasePlugin, v, init=True)

    # Run async setup
    asyncio.run(async_plugins_ready(v))

    try:
        # Your sync application logic
        run_sync_app()
    finally:
        # Attempt async shutdown, fall back to sync-only
        asyncio.run(async_plugins_stopping(v))
        shutdown_all_plugins(v)
```

## API Reference

### Plugin Methods

#### `async async_ready(v, logger, value) -> None`

Optional async hook called after all plugins are initialized, when `async_plugins_ready()` is awaited.

- **v**: Variables instance
- **logger**: Logger for this plugin
- **value**: The return value from `initialize()`

Override this method to perform async setup. The default implementation does nothing.

#### `async async_stopping(v, logger, value) -> None`

Optional async hook called before shutdown begins, when `async_plugins_stopping()` is awaited.

- **v**: Variables instance
- **logger**: Logger for this plugin
- **value**: The extension point value

Override this method to perform async teardown. The default implementation does nothing.

### Framework Functions

#### `async_plugins_ready(v=None, *, capture_loop=True)`

Async function that signals all initialized plugins that the application is ready.

- **v**: Variables instance (uses default if None)
- **capture_loop**: Whether to capture the event loop for later use (default: True)

Calls `async_ready()` on each initialized plugin in startup order.

#### `async_plugins_stopping(v=None)`

Async function that signals all initialized plugins that the application is stopping.

- **v**: Variables instance (uses default if None)

Calls `async_stopping()` on each initialized plugin in reverse startup order.

#### `capture_async_loop(v=None, first_time_only=False) -> AbstractEventLoop | None`

Capture a reference to the currently running asyncio event loop. Call from within an async context.

- **v**: Variables instance (uses default if None). The loop is stored per-Variables instance.
- **first_time_only**: If True, only captures if no loop is already stored (default: False)
- **Returns**: The captured loop, or None if not in async context

Also captures the thread ID for automatic mode thread detection.

#### `get_captured_async_loop(v=None) -> AbstractEventLoop | None`

Get the previously captured event loop reference.

- **v**: Variables instance (uses default if None)
- **Returns**: The loop if captured and not closed, otherwise None

#### `clear_async_loop_ref(v=None)`

Clear the captured async loop reference and thread ID.

- **v**: Variables instance (uses default if None)

#### `schedule_async_shutdown(v=None, timeout=5.0) -> bool`

Attempt to schedule `async_plugins_stopping()` on the captured event loop from a sync context (e.g., signal handler).

- **v**: Variables instance (uses default if None)
- **timeout**: Maximum seconds to wait for async shutdown
- **Returns**: True if async shutdown completed, False otherwise

This is thread-safe and uses `run_coroutine_threadsafe`.

## Best Practices

1. **Keep sync init lightweight**: Do configuration and preparation in `initialize()`. Save heavy async work for `async_ready()`.

2. **Timeout awareness**: When using `schedule_async_shutdown()`, be aware that it has a timeout. Critical cleanup should also have sync fallbacks in `shutdown()`.

3. **Error isolation**: Exceptions in one plugin's async hook don't prevent other plugins from running. Errors are logged as warnings.

4. **Choose the right mode**:
   - Use **manual mode** (`await async_plugins_ready()`) when async initialization must complete before the application proceeds (e.g., database connections required for request handling).
   - Use **automatic mode** (fire-and-forget) for non-critical background setup that can complete asynchronously.
   - When in doubt, use manual mode for predictable behavior.

5. **Per-Variables instance storage**: The captured async loop is stored per-Variables instance. If you use multiple Variables instances, ensure you pass the correct one to async functions.

## Backwards Compatibility

- Existing plugins continue to work unchanged
- `async_ready()` and `async_stopping()` return `None` by default (no-op)
- Applications that do not implement async lifecycle hooks are unaffected
- The sync `initialize()` / `shutdown()` lifecycle is unaffected
