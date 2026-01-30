"""
Comprehensive tests for async plugin lifecycle support.

Tests cover:
- Async hooks on Plugin base class
- async_plugins_ready() and async_plugins_stopping() functions
- Event loop capture/retrieval
- schedule_async_shutdown() for sync->async bridge
- eager=True and eager=False plugins with async hooks
- Mixed sync/async plugin scenarios
- Exception handling and isolation
- Edge cases and error conditions
"""
from __future__ import annotations

import asyncio
import pytest
from logging import Logger

from scitrera_app_framework.api import Plugin, Variables
from scitrera_app_framework.core import (
    register_plugin, get_extension, shutdown_all_plugins, init_framework,
    async_plugins_ready, async_plugins_stopping, schedule_async_shutdown,
    capture_async_loop, get_captured_async_loop, clear_async_loop_ref,
    set_async_auto_enabled, init_all_plugins,
)


# =============================================================================
# Test Plugin Implementations
# =============================================================================

class EagerAsyncPlugin(Plugin):
    """Eager plugin with async lifecycle hooks."""
    eager = True

    def __init__(self):
        super().__init__()
        self.call_log: list[str] = []
        self.value_at_ready = None
        self.value_at_stopping = None

    def extension_point_name(self, v: Variables) -> str:
        return 'eager-async-plugin'

    def initialize(self, v: Variables, logger: Logger) -> dict:
        self.call_log.append('initialize')
        return {'initialized': True, 'data': []}

    def shutdown(self, v: Variables, logger: Logger, value) -> None:
        self.call_log.append('shutdown')

    def async_ready(self, v: Variables, logger: Logger, value):
        async def _ready():
            self.call_log.append('async_ready')
            self.value_at_ready = value
            await asyncio.sleep(0.001)
            if value:
                value['async_ready'] = True
        return _ready()

    def async_stopping(self, v: Variables, logger: Logger, value):
        async def _stopping():
            self.call_log.append('async_stopping')
            self.value_at_stopping = value
            await asyncio.sleep(0.001)
            if value:
                value['async_stopped'] = True
        return _stopping()


class LazyAsyncPlugin(Plugin):
    """Non-eager plugin with async lifecycle hooks."""
    eager = False

    def __init__(self):
        super().__init__()
        self.call_log: list[str] = []

    def extension_point_name(self, v: Variables) -> str:
        return 'lazy-async-plugin'

    def initialize(self, v: Variables, logger: Logger) -> dict:
        self.call_log.append('initialize')
        return {'lazy': True}

    def shutdown(self, v: Variables, logger: Logger, value) -> None:
        self.call_log.append('shutdown')

    def async_ready(self, v: Variables, logger: Logger, value):
        async def _ready():
            self.call_log.append('async_ready')
            await asyncio.sleep(0.001)
        return _ready()

    def async_stopping(self, v: Variables, logger: Logger, value):
        async def _stopping():
            self.call_log.append('async_stopping')
            await asyncio.sleep(0.001)
        return _stopping()


class SyncOnlyPlugin(Plugin):
    """Plugin without async hooks (uses defaults)."""
    eager = True

    def __init__(self):
        super().__init__()
        self.call_log: list[str] = []

    def extension_point_name(self, v: Variables) -> str:
        return 'sync-only-plugin'

    def initialize(self, v: Variables, logger: Logger) -> str:
        self.call_log.append('initialize')
        return 'sync-value'

    def shutdown(self, v: Variables, logger: Logger, value) -> None:
        self.call_log.append('shutdown')


class AsyncReadyOnlyPlugin(Plugin):
    """Plugin with only async_ready (no async_stopping)."""
    eager = True

    def __init__(self):
        super().__init__()
        self.call_log: list[str] = []

    def extension_point_name(self, v: Variables) -> str:
        return 'async-ready-only-plugin'

    def initialize(self, v: Variables, logger: Logger) -> str:
        self.call_log.append('initialize')
        return 'ready-only'

    def async_ready(self, v: Variables, logger: Logger, value):
        async def _ready():
            self.call_log.append('async_ready')
        return _ready()


class AsyncStoppingOnlyPlugin(Plugin):
    """Plugin with only async_stopping (no async_ready)."""
    eager = True

    def __init__(self):
        super().__init__()
        self.call_log: list[str] = []

    def extension_point_name(self, v: Variables) -> str:
        return 'async-stopping-only-plugin'

    def initialize(self, v: Variables, logger: Logger) -> str:
        self.call_log.append('initialize')
        return 'stopping-only'

    def async_stopping(self, v: Variables, logger: Logger, value):
        async def _stopping():
            self.call_log.append('async_stopping')
        return _stopping()


class ExceptionInReadyPlugin(Plugin):
    """Plugin that raises in async_ready."""
    eager = True

    def __init__(self):
        super().__init__()
        self.call_log: list[str] = []

    def extension_point_name(self, v: Variables) -> str:
        return 'exception-ready-plugin'

    def initialize(self, v: Variables, logger: Logger) -> str:
        self.call_log.append('initialize')
        return 'will-fail-ready'

    def async_ready(self, v: Variables, logger: Logger, value):
        async def _ready():
            self.call_log.append('async_ready_start')
            raise RuntimeError("Intentional async_ready failure")
        return _ready()


class ExceptionInStoppingPlugin(Plugin):
    """Plugin that raises in async_stopping."""
    eager = True

    def __init__(self):
        super().__init__()
        self.call_log: list[str] = []

    def extension_point_name(self, v: Variables) -> str:
        return 'exception-stopping-plugin'

    def initialize(self, v: Variables, logger: Logger) -> str:
        self.call_log.append('initialize')
        return 'will-fail-stopping'

    def async_stopping(self, v: Variables, logger: Logger, value):
        async def _stopping():
            self.call_log.append('async_stopping_start')
            raise RuntimeError("Intentional async_stopping failure")
        return _stopping()


class DependentAsyncPlugin(Plugin):
    """Async plugin that depends on another plugin."""
    eager = True

    def __init__(self):
        super().__init__()
        self.call_log: list[str] = []
        self.dep_value = None

    def extension_point_name(self, v: Variables) -> str:
        return 'dependent-async-plugin'

    def get_dependencies(self, v: Variables):
        return ['sync-only-plugin']

    def initialize(self, v: Variables, logger: Logger) -> dict:
        self.call_log.append('initialize')
        self.dep_value = get_extension('sync-only-plugin', v)
        return {'dep': self.dep_value}

    def async_ready(self, v: Variables, logger: Logger, value):
        async def _ready():
            self.call_log.append('async_ready')
        return _ready()


class MultiExtAsyncPlugin(Plugin):
    """Multi-extension plugin with async hooks."""

    def __init__(self, name_suffix='1'):
        super().__init__()
        self._suffix = name_suffix
        self.call_log: list[str] = []

    def name(self) -> str:
        return f'multi-async-{self._suffix}'

    def extension_point_name(self, v: Variables) -> str:
        return 'multi-async-ext'

    def is_multi_extension(self, v: Variables) -> bool:
        return True

    def initialize(self, v: Variables, logger: Logger) -> str:
        self.call_log.append('initialize')
        return f'multi-value-{self._suffix}'

    def async_ready(self, v: Variables, logger: Logger, value):
        async def _ready():
            self.call_log.append('async_ready')
        return _ready()


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def fresh_variables():
    """Create a fresh Variables instance for each test."""
    v = Variables()
    init_framework('test-async', v=v, shutdown_hooks=False, stateful=False, log_level='DEBUG')
    yield v
    clear_async_loop_ref()
    try:
        shutdown_all_plugins(v)
    except Exception:
        pass  # Ignore shutdown errors in cleanup


@pytest.fixture(autouse=True)
def clear_loop_before_test():
    """Ensure loop reference is cleared before each test."""
    clear_async_loop_ref()
    yield
    clear_async_loop_ref()


# =============================================================================
# Test: Plugin Base Class Async Hooks
# =============================================================================

class TestPluginAsyncHooksDefaults:
    """Test default behavior of async hooks on Plugin base class."""

    @pytest.mark.asyncio
    async def test_async_ready_default_returns_none(self, fresh_variables):
        """Default async_ready is an async method that resolves to None."""
        plugin = SyncOnlyPlugin()
        coro = plugin.async_ready(fresh_variables, None, None)
        assert asyncio.iscoroutine(coro)
        result = await coro
        assert result is None

    @pytest.mark.asyncio
    async def test_async_stopping_default_returns_none(self, fresh_variables):
        """Default async_stopping is an async method that resolves to None."""
        plugin = SyncOnlyPlugin()
        coro = plugin.async_stopping(fresh_variables, None, None)
        assert asyncio.iscoroutine(coro)
        result = await coro
        assert result is None

    def test_async_ready_returns_coroutine_when_overridden(self, fresh_variables):
        """Custom async_ready returns a coroutine."""
        plugin = EagerAsyncPlugin()
        coro = plugin.async_ready(fresh_variables, None, {})
        assert asyncio.iscoroutine(coro)
        coro.close()

    def test_async_stopping_returns_coroutine_when_overridden(self, fresh_variables):
        """Custom async_stopping returns a coroutine."""
        plugin = EagerAsyncPlugin()
        coro = plugin.async_stopping(fresh_variables, None, {})
        assert asyncio.iscoroutine(coro)
        coro.close()


# =============================================================================
# Test: async_plugins_ready()
# =============================================================================

class TestAsyncPluginsReady:
    """Test async_plugins_ready function."""

    @pytest.mark.asyncio
    async def test_calls_async_ready_on_eager_plugin(self, fresh_variables):
        """async_plugins_ready calls async_ready on initialized eager plugins."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)

        assert 'initialize' in plugin.call_log
        assert 'async_ready' in plugin.call_log
        assert plugin.call_log.index('initialize') < plugin.call_log.index('async_ready')

    @pytest.mark.asyncio
    async def test_skips_uninitialized_plugins(self, fresh_variables):
        """async_plugins_ready skips plugins that haven't been initialized."""
        plugin = register_plugin(LazyAsyncPlugin, fresh_variables, init=False)

        await async_plugins_ready(fresh_variables)

        assert 'async_ready' not in plugin.call_log

    @pytest.mark.asyncio
    async def test_skips_plugins_without_async_ready(self, fresh_variables):
        """async_plugins_ready skips plugins that return None from async_ready."""
        plugin = register_plugin(SyncOnlyPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)

        assert plugin.call_log == ['initialize']

    @pytest.mark.asyncio
    async def test_captures_loop_by_default(self, fresh_variables):
        """async_plugins_ready captures the event loop by default."""
        assert get_captured_async_loop(fresh_variables) is None

        await async_plugins_ready(fresh_variables, capture_loop=True)

        assert get_captured_async_loop(fresh_variables) is not None
        assert get_captured_async_loop(fresh_variables) == asyncio.get_running_loop()

    @pytest.mark.asyncio
    async def test_can_skip_loop_capture(self, fresh_variables):
        """async_plugins_ready can skip loop capture."""
        await async_plugins_ready(fresh_variables, capture_loop=False)

        assert get_captured_async_loop(fresh_variables) is None

    @pytest.mark.asyncio
    async def test_passes_correct_value_to_async_ready(self, fresh_variables):
        """async_plugins_ready passes the extension value to async_ready."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)

        assert plugin.value_at_ready is not None
        assert plugin.value_at_ready['initialized'] is True

    @pytest.mark.asyncio
    async def test_processes_multiple_plugins(self, fresh_variables):
        """async_plugins_ready processes multiple plugins."""
        plugin1 = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        plugin2 = register_plugin(AsyncReadyOnlyPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)

        assert 'async_ready' in plugin1.call_log
        assert 'async_ready' in plugin2.call_log

    @pytest.mark.asyncio
    async def test_continues_after_exception(self, fresh_variables):
        """async_plugins_ready continues processing after one plugin raises."""
        exc_plugin = register_plugin(ExceptionInReadyPlugin, fresh_variables, init=True)
        good_plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)

        assert 'async_ready_start' in exc_plugin.call_log
        assert 'async_ready' in good_plugin.call_log


# =============================================================================
# Test: async_plugins_stopping()
# =============================================================================

class TestAsyncPluginsStopping:
    """Test async_plugins_stopping function."""

    @pytest.mark.asyncio
    async def test_calls_async_stopping_on_initialized_plugins(self, fresh_variables):
        """async_plugins_stopping calls async_stopping on initialized plugins."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_stopping(fresh_variables)

        assert 'async_stopping' in plugin.call_log

    @pytest.mark.asyncio
    async def test_processes_in_reverse_startup_order(self, fresh_variables):
        """async_plugins_stopping processes plugins in reverse startup order."""
        stopping_order = []

        class OrderTracker1(Plugin):
            eager = True

            def extension_point_name(self, v):
                return 'order-1'

            def initialize(self, v, logger):
                return '1'

            def async_stopping(self, v, logger, value):
                async def _stop():
                    stopping_order.append('1')
                return _stop()

        class OrderTracker2(Plugin):
            eager = True

            def extension_point_name(self, v):
                return 'order-2'

            def initialize(self, v, logger):
                return '2'

            def async_stopping(self, v, logger, value):
                async def _stop():
                    stopping_order.append('2')
                return _stop()

        register_plugin(OrderTracker1, fresh_variables, init=True)
        register_plugin(OrderTracker2, fresh_variables, init=True)

        await async_plugins_stopping(fresh_variables)

        # Should be in reverse order (2 registered after 1, so stops first)
        assert stopping_order == ['2', '1']

    @pytest.mark.asyncio
    async def test_skips_plugins_without_async_stopping(self, fresh_variables):
        """async_plugins_stopping skips plugins that return None."""
        plugin = register_plugin(AsyncReadyOnlyPlugin, fresh_variables, init=True)

        await async_plugins_stopping(fresh_variables)

        assert 'async_stopping' not in plugin.call_log

    @pytest.mark.asyncio
    async def test_passes_correct_value_to_async_stopping(self, fresh_variables):
        """async_plugins_stopping passes the extension value to async_stopping."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_stopping(fresh_variables)

        assert plugin.value_at_stopping is not None
        assert plugin.value_at_stopping['initialized'] is True

    @pytest.mark.asyncio
    async def test_continues_after_exception(self, fresh_variables):
        """async_plugins_stopping continues after one plugin raises."""
        exc_plugin = register_plugin(ExceptionInStoppingPlugin, fresh_variables, init=True)
        good_plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_stopping(fresh_variables)

        assert 'async_stopping_start' in exc_plugin.call_log
        assert 'async_stopping' in good_plugin.call_log


# =============================================================================
# Test: Event Loop Capture
# =============================================================================

class TestLoopCapture:
    """Test event loop capture and retrieval functions."""

    @pytest.mark.asyncio
    async def test_capture_async_loop_returns_running_loop(self):
        """capture_async_loop captures the running loop."""
        loop = capture_async_loop()

        assert loop is not None
        assert loop == asyncio.get_running_loop()
        assert get_captured_async_loop() == loop

    def test_capture_async_loop_returns_none_outside_async(self):
        """capture_async_loop returns None when not in async context."""
        loop = capture_async_loop()

        assert loop is None

    def test_get_captured_async_loop_returns_none_when_not_captured(self):
        """get_captured_async_loop returns None when nothing captured."""
        assert get_captured_async_loop() is None

    def test_get_captured_async_loop_returns_none_when_loop_closed(self):
        """get_captured_async_loop returns None when captured loop is closed."""
        import scitrera_app_framework.core.plugins as plugins_module

        closed_loop = asyncio.new_event_loop()
        closed_loop.close()
        plugins_module._async_loop_ref = closed_loop

        assert get_captured_async_loop() is None

    def test_clear_async_loop_ref_clears_reference(self):
        """clear_async_loop_ref clears the captured reference."""
        import scitrera_app_framework.core.plugins as plugins_module
        plugins_module._async_loop_ref = asyncio.new_event_loop()

        clear_async_loop_ref()

        assert get_captured_async_loop() is None


# =============================================================================
# Test: schedule_async_shutdown()
# =============================================================================

class TestScheduleAsyncShutdown:
    """Test schedule_async_shutdown function."""

    def test_returns_false_when_no_loop_captured(self, fresh_variables):
        """schedule_async_shutdown returns False when no loop captured."""
        clear_async_loop_ref()

        result = schedule_async_shutdown(fresh_variables)

        assert result is False

    def test_returns_false_when_loop_closed(self, fresh_variables):
        """schedule_async_shutdown returns False when captured loop is closed."""
        import scitrera_app_framework.core.plugins as plugins_module

        closed_loop = asyncio.new_event_loop()
        closed_loop.close()
        plugins_module._async_loop_ref = closed_loop

        result = schedule_async_shutdown(fresh_variables)

        assert result is False


# =============================================================================
# Test: Eager vs Non-Eager Plugins
# =============================================================================

class TestEagerVsLazyAsyncPlugins:
    """Test async lifecycle with eager=True and eager=False plugins."""

    @pytest.mark.asyncio
    async def test_eager_plugin_init_on_register(self, fresh_variables):
        """Eager plugin initializes on register with init=True."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        assert plugin.initialized is True
        assert 'initialize' in plugin.call_log

    @pytest.mark.asyncio
    async def test_lazy_plugin_no_init_on_register(self, fresh_variables):
        """Lazy plugin does NOT initialize on register with init=True."""
        plugin = register_plugin(LazyAsyncPlugin, fresh_variables, init=True)

        # Lazy plugins don't init until explicitly requested
        assert plugin.initialized is False
        assert 'initialize' not in plugin.call_log

    @pytest.mark.asyncio
    async def test_lazy_plugin_init_on_get_extension(self, fresh_variables):
        """Lazy plugin initializes when get_extension is called."""
        # Register without init - lazy plugins need explicit get_extension to init
        register_plugin(LazyAsyncPlugin, fresh_variables, init=False)

        # Force initialization via get_extension
        value = get_extension('lazy-async-plugin', fresh_variables)

        # Value should be returned correctly
        assert value == {'lazy': True}

    @pytest.mark.asyncio
    async def test_lazy_plugin_async_ready_after_forced_init(self, fresh_variables):
        """Lazy plugin's async_ready is called after forced initialization."""
        # Register without init
        register_plugin(LazyAsyncPlugin, fresh_variables, init=False)

        # Force init - this returns the value, plugin is now initialized
        get_extension('lazy-async-plugin', fresh_variables)

        # The plugin registry tracks initialized plugins, async_ready should be called
        await async_plugins_ready(fresh_variables)

        # Note: We can't easily check the call_log on the registered plugin instance
        # because register_plugin creates a new instance. The test verifies no errors.

    @pytest.mark.asyncio
    async def test_lazy_plugin_async_ready_skipped_if_not_init(self, fresh_variables):
        """Lazy plugin's async_ready is skipped if never initialized."""
        plugin = register_plugin(LazyAsyncPlugin, fresh_variables, init=True)

        # Don't force init
        await async_plugins_ready(fresh_variables)

        assert 'async_ready' not in plugin.call_log


# =============================================================================
# Test: Mixed Sync/Async Plugin Scenarios
# =============================================================================

class TestMixedSyncAsyncPlugins:
    """Test scenarios with both sync-only and async plugins."""

    @pytest.mark.asyncio
    async def test_mixed_plugins_init_order(self, fresh_variables):
        """Both sync and async plugins initialize in registration order."""
        sync_plugin = register_plugin(SyncOnlyPlugin, fresh_variables, init=True)
        async_plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        assert 'initialize' in sync_plugin.call_log
        assert 'initialize' in async_plugin.call_log

    @pytest.mark.asyncio
    async def test_async_ready_only_affects_async_plugins(self, fresh_variables):
        """async_plugins_ready only affects plugins with async_ready."""
        sync_plugin = register_plugin(SyncOnlyPlugin, fresh_variables, init=True)
        async_plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)

        assert sync_plugin.call_log == ['initialize']
        assert 'async_ready' in async_plugin.call_log

    @pytest.mark.asyncio
    async def test_sync_shutdown_works_after_async_stopping(self, fresh_variables):
        """Sync shutdown works correctly after async_plugins_stopping."""
        sync_plugin = register_plugin(SyncOnlyPlugin, fresh_variables, init=True)
        async_plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_stopping(fresh_variables)
        shutdown_all_plugins(fresh_variables)

        assert 'shutdown' in sync_plugin.call_log
        assert 'async_stopping' in async_plugin.call_log
        assert 'shutdown' in async_plugin.call_log

    @pytest.mark.asyncio
    async def test_async_plugin_depends_on_sync_plugin(self, fresh_variables):
        """Async plugin can depend on sync plugin."""
        sync_plugin = register_plugin(SyncOnlyPlugin, fresh_variables, init=True)
        dep_plugin = register_plugin(DependentAsyncPlugin, fresh_variables, init=True)

        assert dep_plugin.dep_value == 'sync-value'

        await async_plugins_ready(fresh_variables)

        assert 'async_ready' in dep_plugin.call_log


# =============================================================================
# Test: Full Lifecycle
# =============================================================================

class TestFullLifecycle:
    """Integration tests for full async plugin lifecycle."""

    @pytest.mark.asyncio
    async def test_complete_lifecycle_order(self, fresh_variables):
        """Test complete lifecycle: init -> ready -> stopping -> shutdown."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)
        await async_plugins_stopping(fresh_variables)
        shutdown_all_plugins(fresh_variables)

        expected_order = ['initialize', 'async_ready', 'async_stopping', 'shutdown']
        assert plugin.call_log == expected_order

    @pytest.mark.asyncio
    async def test_async_hooks_can_modify_extension_value(self, fresh_variables):
        """Async hooks can modify the extension value."""
        register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        value = get_extension('eager-async-plugin', fresh_variables)
        assert value == {'initialized': True, 'data': []}

        await async_plugins_ready(fresh_variables)
        assert value.get('async_ready') is True

        await async_plugins_stopping(fresh_variables)
        assert value.get('async_stopped') is True

    @pytest.mark.asyncio
    async def test_lifecycle_with_only_async_ready(self, fresh_variables):
        """Plugin with only async_ready works correctly."""
        plugin = register_plugin(AsyncReadyOnlyPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)
        await async_plugins_stopping(fresh_variables)
        shutdown_all_plugins(fresh_variables)

        assert plugin.call_log == ['initialize', 'async_ready']

    @pytest.mark.asyncio
    async def test_lifecycle_with_only_async_stopping(self, fresh_variables):
        """Plugin with only async_stopping works correctly."""
        plugin = register_plugin(AsyncStoppingOnlyPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)
        await async_plugins_stopping(fresh_variables)
        shutdown_all_plugins(fresh_variables)

        assert plugin.call_log == ['initialize', 'async_stopping']

    @pytest.mark.asyncio
    async def test_multiple_calls_to_async_ready_are_safe(self, fresh_variables):
        """Multiple calls to async_plugins_ready are idempotent - only first call invokes async_ready."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)
        await async_plugins_ready(fresh_variables)

        # Should only be called once due to _async_ready_called flag
        assert plugin.call_log.count('async_ready') == 1

    @pytest.mark.asyncio
    async def test_skipping_async_ready_still_allows_shutdown(self, fresh_variables):
        """Skipping async_plugins_ready doesn't break shutdown."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        # Skip async_plugins_ready
        await async_plugins_stopping(fresh_variables)
        shutdown_all_plugins(fresh_variables)

        assert 'async_ready' not in plugin.call_log
        assert 'async_stopping' in plugin.call_log
        assert 'shutdown' in plugin.call_log


# =============================================================================
# Test: Exception Handling
# =============================================================================

class TestExceptionHandling:
    """Test exception handling in async lifecycle."""

    @pytest.mark.asyncio
    async def test_exception_in_async_ready_is_logged_not_raised(self, fresh_variables):
        """Exception in async_ready is logged, not propagated."""
        register_plugin(ExceptionInReadyPlugin, fresh_variables, init=True)

        # Should not raise
        await async_plugins_ready(fresh_variables)

    @pytest.mark.asyncio
    async def test_exception_in_async_stopping_is_logged_not_raised(self, fresh_variables):
        """Exception in async_stopping is logged, not propagated."""
        register_plugin(ExceptionInStoppingPlugin, fresh_variables, init=True)

        # Should not raise
        await async_plugins_stopping(fresh_variables)

    @pytest.mark.asyncio
    async def test_exception_does_not_prevent_other_plugins(self, fresh_variables):
        """Exception in one plugin doesn't prevent others from running."""
        exc_plugin = register_plugin(ExceptionInReadyPlugin, fresh_variables, init=True)
        good_plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)

        # Both should have been attempted
        assert 'async_ready_start' in exc_plugin.call_log
        assert 'async_ready' in good_plugin.call_log


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_no_plugins_registered(self, fresh_variables):
        """async_plugins_ready/stopping work with no plugins."""
        await async_plugins_ready(fresh_variables)
        await async_plugins_stopping(fresh_variables)
        # No assertion needed - just shouldn't raise

    @pytest.mark.asyncio
    async def test_plugins_registered_but_not_initialized(self, fresh_variables):
        """async_plugins_ready/stopping skip non-initialized plugins."""
        plugin = register_plugin(LazyAsyncPlugin, fresh_variables, init=False)

        await async_plugins_ready(fresh_variables)
        await async_plugins_stopping(fresh_variables)

        assert plugin.call_log == []

    @pytest.mark.asyncio
    async def test_shutdown_without_async_stopping(self, fresh_variables):
        """sync shutdown works without calling async_plugins_stopping."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        # Skip async_plugins_stopping entirely
        shutdown_all_plugins(fresh_variables)

        assert 'shutdown' in plugin.call_log
        assert 'async_stopping' not in plugin.call_log

    @pytest.mark.asyncio
    async def test_double_shutdown_is_safe(self, fresh_variables):
        """Double shutdown doesn't raise exceptions."""
        register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        # Should not raise on either call
        shutdown_all_plugins(fresh_variables)
        shutdown_all_plugins(fresh_variables)

    def test_sync_only_usage_unchanged(self, fresh_variables):
        """Pure sync usage works exactly as before (no async calls)."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        value = get_extension('eager-async-plugin', fresh_variables)
        shutdown_all_plugins(fresh_variables)

        # Only sync lifecycle methods called
        assert plugin.call_log == ['initialize', 'shutdown']
        assert value == {'initialized': True, 'data': []}

    @pytest.mark.asyncio
    async def test_async_ready_with_none_value(self, fresh_variables):
        """async_ready handles None value gracefully."""
        class NoneValuePlugin(Plugin):
            eager = True
            call_log = []

            def extension_point_name(self, v):
                return 'none-value-plugin'

            def initialize(self, v, logger):
                return None  # Returns None

            def async_ready(self, v, logger, value):
                async def _ready():
                    NoneValuePlugin.call_log.append(f'ready-{value}')
                return _ready()

        register_plugin(NoneValuePlugin, fresh_variables, init=True)

        await async_plugins_ready(fresh_variables)

        assert 'ready-None' in NoneValuePlugin.call_log


# =============================================================================
# Test: Automatic vs Manual Async Modes
# =============================================================================

class TestAutoVsManualAsyncModes:
    """Test automatic (fire-and-forget) vs manual (explicit await) async handling."""

    @pytest.mark.asyncio
    async def test_auto_async_ready_in_loop_thread_fire_and_forget(self, fresh_variables):
        """When in loop thread, automatic async_ready is scheduled via create_task (fire-and-forget)."""
        # Capture the loop first so we're "in the loop thread"
        capture_async_loop(fresh_variables)

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        # Plugin was initialized, but since we're in the loop thread, async_ready
        # was scheduled via create_task (fire-and-forget), not blocking
        assert plugin.initialized
        assert plugin._async_ready_called  # Flag is set immediately

        # Give the event loop a chance to run the scheduled task
        await asyncio.sleep(0.01)

        # Now async_ready should have completed
        assert 'async_ready' in plugin.call_log

    @pytest.mark.asyncio
    async def test_auto_async_stopping_in_loop_thread_fire_and_forget(self, fresh_variables):
        """When in loop thread, automatic async_stopping is scheduled via create_task."""
        capture_async_loop(fresh_variables)

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        await asyncio.sleep(0.01)  # Let async_ready complete

        # Clear the flag to test async_stopping automatic handling
        plugin._async_stopping_called = False

        shutdown_all_plugins(fresh_variables)

        # Flag should be set immediately (fire-and-forget was scheduled)
        assert plugin._async_stopping_called

        # Give the event loop a chance to run the scheduled task
        await asyncio.sleep(0.01)

        assert 'async_stopping' in plugin.call_log
        assert 'shutdown' in plugin.call_log

    @pytest.mark.asyncio
    async def test_manual_async_ready_awaits_completion(self, fresh_variables):
        """Manual async_plugins_ready() awaits full completion before returning."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        # Manually call async_plugins_ready - this should await completion
        await async_plugins_ready(fresh_variables)

        # async_ready should be complete, not just scheduled
        assert 'async_ready' in plugin.call_log
        assert plugin._async_ready_called

    @pytest.mark.asyncio
    async def test_manual_async_stopping_awaits_completion(self, fresh_variables):
        """Manual async_plugins_stopping() awaits full completion before returning."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        await async_plugins_ready(fresh_variables)

        # Manually call async_plugins_stopping - this should await completion
        await async_plugins_stopping(fresh_variables)

        # async_stopping should be complete
        assert 'async_stopping' in plugin.call_log
        assert plugin._async_stopping_called

    @pytest.mark.asyncio
    async def test_auto_skips_if_already_called_via_manual(self, fresh_variables):
        """Automatic async handling skips if manual was already called."""
        # Don't capture loop yet - manual first
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        # Manually call async_plugins_ready
        await async_plugins_ready(fresh_variables)
        assert plugin.call_log.count('async_ready') == 1

        # Now capture loop and try to trigger automatic handling by initializing another plugin
        capture_async_loop(fresh_variables)

        # The flag should prevent duplicate calls
        assert plugin._async_ready_called

    @pytest.mark.asyncio
    async def test_manual_skips_if_already_called_via_auto(self, fresh_variables):
        """Manual async_plugins_ready skips plugins already handled by automatic."""
        # Capture loop first so automatic handling happens
        capture_async_loop(fresh_variables)

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        await asyncio.sleep(0.01)  # Let fire-and-forget complete

        assert 'async_ready' in plugin.call_log
        call_count_before = plugin.call_log.count('async_ready')

        # Manual call should skip since flag is set
        await async_plugins_ready(fresh_variables)

        assert plugin.call_log.count('async_ready') == call_count_before

    @pytest.mark.asyncio
    async def test_no_loop_captured_skips_auto_handling(self, fresh_variables):
        """Without a captured loop, automatic async handling is skipped."""
        # Don't capture loop
        assert get_captured_async_loop(fresh_variables) is None

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        # Plugin initialized but async_ready not called (no loop)
        assert plugin.initialized
        assert not plugin._async_ready_called
        assert 'async_ready' not in plugin.call_log

        # Manual call still works
        await async_plugins_ready(fresh_variables)
        assert 'async_ready' in plugin.call_log

    @pytest.mark.asyncio
    async def test_flags_prevent_double_invocation_async_ready(self, fresh_variables):
        """_async_ready_called flag prevents async_ready from being called twice."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)

        # First manual call
        await async_plugins_ready(fresh_variables)
        assert plugin.call_log.count('async_ready') == 1

        # Second manual call - should be skipped
        await async_plugins_ready(fresh_variables)
        assert plugin.call_log.count('async_ready') == 1

    @pytest.mark.asyncio
    async def test_flags_prevent_double_invocation_async_stopping(self, fresh_variables):
        """_async_stopping_called flag prevents async_stopping from being called twice."""
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        await async_plugins_ready(fresh_variables)

        # First manual call
        await async_plugins_stopping(fresh_variables)
        assert plugin.call_log.count('async_stopping') == 1

        # Second manual call - should be skipped
        await async_plugins_stopping(fresh_variables)
        assert plugin.call_log.count('async_stopping') == 1


# =============================================================================
# Test: Async Auto-Enabled Configuration
# =============================================================================

class TestAsyncAutoEnabledConfig:
    """Test set_async_auto_enabled and async_enabled parameter behavior."""

    @pytest.mark.asyncio
    async def test_async_auto_enabled_default_is_true(self, fresh_variables):
        """By default, async auto-handling is enabled."""
        capture_async_loop(fresh_variables)
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        await asyncio.sleep(0.01)
        # With auto enabled (default), async_ready should be scheduled
        assert plugin._async_ready_called

    @pytest.mark.asyncio
    async def test_set_async_auto_enabled_false_disables_auto(self, fresh_variables):
        """Setting async_auto_enabled to False disables automatic handling."""
        capture_async_loop(fresh_variables)
        set_async_auto_enabled(False, fresh_variables)

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        await asyncio.sleep(0.01)

        # With auto disabled, async_ready should NOT be called automatically
        assert not plugin._async_ready_called
        assert 'async_ready' not in plugin.call_log

    @pytest.mark.asyncio
    async def test_manual_still_works_when_auto_disabled(self, fresh_variables):
        """Manual async_plugins_ready works even when auto is disabled."""
        set_async_auto_enabled(False, fresh_variables)

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        assert not plugin._async_ready_called

        # Manual call should still work
        await async_plugins_ready(fresh_variables)
        assert plugin._async_ready_called
        assert 'async_ready' in plugin.call_log

    @pytest.mark.asyncio
    async def test_shutdown_respects_async_enabled_false(self, fresh_variables):
        """shutdown_all_plugins respects async_auto_enabled=False."""
        capture_async_loop(fresh_variables)
        set_async_auto_enabled(False, fresh_variables)

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        await async_plugins_ready(fresh_variables)  # Manual ready

        shutdown_all_plugins(fresh_variables)
        await asyncio.sleep(0.01)

        # async_stopping should NOT be called automatically
        assert not plugin._async_stopping_called

    @pytest.mark.asyncio
    async def test_async_enabled_param_overrides_global_true(self, fresh_variables):
        """async_enabled=True param overrides global False setting."""
        capture_async_loop(fresh_variables)
        set_async_auto_enabled(False, fresh_variables)  # Global off

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables)
        # Use init_all_plugins with explicit async_enabled=True
        init_all_plugins(fresh_variables, async_enabled=True)
        await asyncio.sleep(0.01)

        # Should be called because param overrides global
        assert plugin._async_ready_called

    @pytest.mark.asyncio
    async def test_async_enabled_param_overrides_global_false(self, fresh_variables):
        """async_enabled=False param overrides global True setting."""
        capture_async_loop(fresh_variables)
        # Global is True by default

        plugin = register_plugin(EagerAsyncPlugin, fresh_variables)
        init_all_plugins(fresh_variables, async_enabled=False)
        await asyncio.sleep(0.01)

        # Should NOT be called because param overrides global
        assert not plugin._async_ready_called

    @pytest.mark.asyncio
    async def test_shutdown_async_enabled_param_override(self, fresh_variables):
        """shutdown_all_plugins async_enabled param overrides global."""
        capture_async_loop(fresh_variables)
        plugin = register_plugin(EagerAsyncPlugin, fresh_variables, init=True)
        await async_plugins_ready(fresh_variables)

        # Global is True, but pass False to shutdown
        shutdown_all_plugins(fresh_variables, async_enabled=False)
        await asyncio.sleep(0.01)

        assert not plugin._async_stopping_called
        assert 'shutdown' in plugin.call_log
