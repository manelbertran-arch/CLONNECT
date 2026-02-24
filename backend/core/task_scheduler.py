"""Centralized background task scheduler with health monitoring."""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    name: str
    func: Callable
    interval_seconds: int
    initial_delay_seconds: int = 0
    last_run: Optional[datetime] = None
    last_error: Optional[str] = None
    run_count: int = 0
    error_count: int = 0
    is_running: bool = False
    _task: Optional[asyncio.Task] = field(default=None, repr=False)


class TaskScheduler:
    """Manages background tasks with health tracking and graceful shutdown."""

    def __init__(self):
        self._tasks: Dict[str, ScheduledTask] = {}
        self._shutdown_event = asyncio.Event()

    def register(
        self,
        name: str,
        func: Callable,
        interval_seconds: int,
        initial_delay_seconds: int = 0,
    ) -> None:
        """Register a task to run on a schedule."""
        self._tasks[name] = ScheduledTask(
            name=name,
            func=func,
            interval_seconds=interval_seconds,
            initial_delay_seconds=initial_delay_seconds,
        )

    async def start_all(self) -> None:
        """Start all registered tasks."""
        for name, task_info in self._tasks.items():
            task_info._task = asyncio.create_task(
                self._run_task_loop(task_info),
                name=f"scheduler:{name}",
            )
            logger.info(f"Started scheduled task: {name} (every {task_info.interval_seconds}s)")

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Gracefully stop all tasks."""
        logger.info("Shutting down task scheduler...")
        self._shutdown_event.set()

        tasks = [t._task for t in self._tasks.values() if t._task and not t._task.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)
            for task in tasks:
                if not task.done():
                    task.cancel()

        logger.info("Task scheduler shutdown complete")

    def health_report(self) -> Dict:
        """Return health status of all tasks."""
        return {
            name: {
                "is_running": t.is_running,
                "run_count": t.run_count,
                "error_count": t.error_count,
                "last_run": t.last_run.isoformat() if t.last_run else None,
                "last_error": t.last_error,
                "interval_seconds": t.interval_seconds,
            }
            for name, t in self._tasks.items()
        }

    async def _run_task_loop(self, task_info: ScheduledTask) -> None:
        """Run a single task on its schedule."""
        if task_info.initial_delay_seconds > 0:
            await self._interruptible_sleep(task_info.initial_delay_seconds)

        while not self._shutdown_event.is_set():
            task_info.is_running = True
            try:
                await task_info.func()
                task_info.run_count += 1
                task_info.last_run = datetime.now(timezone.utc)
                task_info.last_error = None
            except Exception as e:
                task_info.error_count += 1
                task_info.last_error = str(e)
                logger.error(f"Task {task_info.name} error: {e}", exc_info=True)
            finally:
                task_info.is_running = False

            await self._interruptible_sleep(task_info.interval_seconds)

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep that can be interrupted by shutdown."""
        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass  # Normal — timeout means shutdown wasn't triggered


# Global singleton
scheduler = TaskScheduler()
