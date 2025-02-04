import asyncio
from typing import Coroutine, Any


def sync_await(coro: Coroutine) -> Any:
    """
    Provides a utility function to execute asynchronous coroutines in a synchronous-like manner.
    If an event loop is already running on this thread, it uses the current loop; otherwise, it
    falls back to asyncio.run to execute the coroutine. Either way, it will run the coroutine
    to completion before returning.

    N.B.: this may cause current thread event loop to block, so use this carefully in async contexts.

    Args:
        coro (Coroutine): The coroutine to be executed.

    Returns:
        Any: The result of the coroutine execution.

    """
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
