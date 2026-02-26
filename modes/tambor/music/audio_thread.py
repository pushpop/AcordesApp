"""ABOUTME: Thread-safe infrastructure for non-blocking audio operations.
ABOUTME: Provides pattern loading/saving and audio event queueing without blocking UI."""

import queue
import concurrent.futures
from typing import Dict, List, Any, Callable, Optional
from .pattern_manager import PatternManager


class AudioQueue:
    """Thread-safe queue for audio parameter changes and events."""

    def __init__(self, maxsize: int = 100):
        """Initialize audio event queue.

        Args:
            maxsize: Maximum queue size before dropping events
        """
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)

    def put(self, event: Dict[str, Any]) -> bool:
        """Send event to audio thread (non-blocking).

        Args:
            event: Event dict with 'event' key and parameter keys

        Returns:
            True if event was queued, False if queue was full (event dropped)
        """
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            # Queue is full - drop event to prevent blocking
            return False

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all pending events (audio thread only).

        Returns:
            List of all queued events, empty list if queue is empty
        """
        events = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def clear(self) -> None:
        """Clear all pending events."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


class PatternLoader:
    """Load patterns in background thread without blocking UI."""

    def __init__(self, pattern_manager: PatternManager, max_workers: int = 2):
        """Initialize pattern loader.

        Args:
            pattern_manager: PatternManager instance to load from
            max_workers: Max background threads (2 for parallel loading)
        """
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._pattern_manager = pattern_manager
        self._pending_loads: Dict[int, concurrent.futures.Future] = {}

    def load_async(
        self,
        pattern_num: int,
        drum_names: List[str],
        callback: Callable[[Optional[Dict]], None],
    ) -> None:
        """Load pattern asynchronously, call callback when ready.

        Args:
            pattern_num: Pattern number to load
            drum_names: Drum name list for pattern context
            callback: Function called with loaded data or None if failed
        """

        def _load():
            """Load pattern in background thread."""
            try:
                return self._pattern_manager.load_pattern(pattern_num, drum_names)
            except Exception as e:
                print(f"Error loading pattern {pattern_num}: {e}")
                return None

        future = self._executor.submit(_load)
        self._pending_loads[pattern_num] = future

        def _on_complete(f):
            """Callback when load completes."""
            try:
                result = f.result()
                callback(result)
            finally:
                self._pending_loads.pop(pattern_num, None)

        future.add_done_callback(_on_complete)

    def is_loading(self, pattern_num: int) -> bool:
        """Check if pattern is currently loading.

        Args:
            pattern_num: Pattern number to check

        Returns:
            True if load is in progress, False otherwise
        """
        if pattern_num not in self._pending_loads:
            return False
        return not self._pending_loads[pattern_num].done()

    def cancel_all(self) -> None:
        """Cancel all pending load operations."""
        for future in self._pending_loads.values():
            future.cancel()
        self._pending_loads.clear()

    def shutdown(self) -> None:
        """Shutdown executor and cancel pending operations."""
        self.cancel_all()
        self._executor.shutdown(wait=False)


class PatternSaver:
    """Save patterns in background thread without blocking UI."""

    def __init__(self, pattern_manager: PatternManager, max_workers: int = 1):
        """Initialize pattern saver.

        Args:
            pattern_manager: PatternManager instance to save to
            max_workers: Max background threads (1 to avoid file contention)
        """
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._save_queue: queue.Queue = queue.Queue()
        self._pattern_manager = pattern_manager
        self._pending_futures: List[concurrent.futures.Future] = []

    def queue_save(
        self,
        pattern_num: int,
        pattern_data: Dict[str, Any],
        drum_names: List[str],
        **kwargs,
    ) -> bool:
        """Queue a pattern for saving (non-blocking).

        Args:
            pattern_num: Pattern number to save
            pattern_data: Pattern data (drum steps)
            drum_names: Drum names for context
            **kwargs: Additional save parameters (bpm, num_steps, pre_scale, etc.)

        Returns:
            True if queued, False if queue is full
        """
        try:
            self._save_queue.put_nowait((pattern_num, pattern_data, drum_names, kwargs))
            return True
        except queue.Full:
            return False

    def flush(self, wait: bool = False) -> None:
        """Flush all queued saves to disk in background.

        Args:
            wait: If True, block until all saves complete (for testing)
        """
        queued_saves = []
        while not self._save_queue.empty():
            try:
                queued_saves.append(self._save_queue.get_nowait())
            except queue.Empty:
                break

        new_futures = []
        for pattern_num, pattern_data, drum_names, kwargs in queued_saves:
            future = self._executor.submit(
                self._pattern_manager.save_pattern,
                pattern_num,
                pattern_data,
                drum_names,
                **kwargs,
            )
            new_futures.append(future)
            self._pending_futures.append(future)

        # Wait for all saves to complete if requested
        if wait:
            # Wait for all pending futures (both queued and previous)
            if self._pending_futures:
                concurrent.futures.wait(self._pending_futures)
                self._pending_futures.clear()

    def wait_for_saves(self) -> None:
        """Wait for all pending save operations to complete."""
        if self._pending_futures:
            concurrent.futures.wait(self._pending_futures)
            self._pending_futures.clear()

    def get_queued_count(self) -> int:
        """Get number of patterns queued for saving.

        Returns:
            Count of patterns in save queue
        """
        return self._save_queue.qsize()

    def shutdown(self) -> None:
        """Shutdown executor and flush remaining saves."""
        self.flush()
        self._executor.shutdown(wait=True)  # Wait for saves to complete
