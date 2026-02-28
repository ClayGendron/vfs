"""Tests for EventBus and event types."""

from __future__ import annotations

import logging

import pytest

from grover.events import EventBus, EventType, FileEvent

# =========================================================================
# Helpers
# =========================================================================


async def _collecting_handler(events: list[FileEvent], event: FileEvent) -> None:
    """Append event to a list for assertion."""
    events.append(event)


async def _failing_handler(event: FileEvent) -> None:
    """Handler that always raises."""
    raise RuntimeError(f"boom on {event.path}")


# =========================================================================
# EventType
# =========================================================================


class TestEventType:
    def test_member_count(self) -> None:
        assert len(EventType) == 6

    def test_values(self) -> None:
        assert EventType.FILE_WRITTEN.value == "file_written"
        assert EventType.FILE_DELETED.value == "file_deleted"
        assert EventType.FILE_MOVED.value == "file_moved"
        assert EventType.FILE_RESTORED.value == "file_restored"

    def test_unique_values(self) -> None:
        values = [et.value for et in EventType]
        assert len(values) == len(set(values))


# =========================================================================
# FileEvent
# =========================================================================


class TestFileEvent:
    def test_construction(self) -> None:
        ev = FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt")
        assert ev.event_type is EventType.FILE_WRITTEN
        assert ev.path == "/a.txt"
        assert ev.old_path is None
        assert ev.content is None

    def test_with_content(self) -> None:
        ev = FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt", content="hello")
        assert ev.content == "hello"

    def test_move_event(self) -> None:
        ev = FileEvent(event_type=EventType.FILE_MOVED, path="/b.txt", old_path="/a.txt")
        assert ev.old_path == "/a.txt"
        assert ev.path == "/b.txt"

    def test_deleted_event(self) -> None:
        ev = FileEvent(event_type=EventType.FILE_DELETED, path="/gone.txt")
        assert ev.event_type is EventType.FILE_DELETED

    def test_restored_event(self) -> None:
        ev = FileEvent(event_type=EventType.FILE_RESTORED, path="/back.txt")
        assert ev.event_type is EventType.FILE_RESTORED

    def test_immutable(self) -> None:
        ev = FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt")
        with pytest.raises(AttributeError):
            ev.path = "/changed.txt"  # type: ignore[misc]


# =========================================================================
# EventBus Registration
# =========================================================================


class TestEventBusRegistration:
    def test_initial_handler_count(self) -> None:
        bus = EventBus()
        assert bus.handler_count == 0

    def test_register_increments_count(self) -> None:
        bus = EventBus()
        bus.register(EventType.FILE_WRITTEN, _failing_handler)
        assert bus.handler_count == 1

    def test_register_multiple_types(self) -> None:
        bus = EventBus()
        bus.register(EventType.FILE_WRITTEN, _failing_handler)
        bus.register(EventType.FILE_DELETED, _failing_handler)
        assert bus.handler_count == 2

    def test_register_multiple_handlers_same_type(self) -> None:
        bus = EventBus()
        bus.register(EventType.FILE_WRITTEN, _failing_handler)

        async def another(event: FileEvent) -> None:
            pass

        bus.register(EventType.FILE_WRITTEN, another)
        assert bus.handler_count == 2

    def test_unregister_returns_true(self) -> None:
        bus = EventBus()
        bus.register(EventType.FILE_WRITTEN, _failing_handler)
        assert bus.unregister(EventType.FILE_WRITTEN, _failing_handler) is True
        assert bus.handler_count == 0

    def test_unregister_missing_returns_false(self) -> None:
        bus = EventBus()
        assert bus.unregister(EventType.FILE_WRITTEN, _failing_handler) is False

    def test_clear(self) -> None:
        bus = EventBus()
        bus.register(EventType.FILE_WRITTEN, _failing_handler)
        bus.register(EventType.FILE_DELETED, _failing_handler)
        bus.clear()
        assert bus.handler_count == 0


# =========================================================================
# EventBus Emit
# =========================================================================


class TestEventBusEmit:
    async def test_handler_called_with_event(self) -> None:
        bus = EventBus()
        collected: list[FileEvent] = []

        async def handler(event: FileEvent) -> None:
            await _collecting_handler(collected, event)

        bus.register(EventType.FILE_WRITTEN, handler)
        ev = FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt")
        await bus.emit(ev)
        await bus.drain()
        assert collected == [ev]

    async def test_multiple_handlers_called_in_order(self) -> None:
        bus = EventBus()
        order: list[int] = []

        async def first(event: FileEvent) -> None:
            order.append(1)

        async def second(event: FileEvent) -> None:
            order.append(2)

        bus.register(EventType.FILE_WRITTEN, first)
        bus.register(EventType.FILE_WRITTEN, second)
        await bus.emit(FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt"))
        await bus.drain()
        assert order == [1, 2]

    async def test_type_filtering(self) -> None:
        bus = EventBus()
        written: list[FileEvent] = []
        deleted: list[FileEvent] = []

        async def on_write(event: FileEvent) -> None:
            await _collecting_handler(written, event)

        async def on_delete(event: FileEvent) -> None:
            await _collecting_handler(deleted, event)

        bus.register(EventType.FILE_WRITTEN, on_write)
        bus.register(EventType.FILE_DELETED, on_delete)

        await bus.emit(FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt"))
        await bus.drain()
        assert len(written) == 1
        assert len(deleted) == 0

    async def test_no_handler_noop(self) -> None:
        bus = EventBus()
        await bus.emit(FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt"))

    async def test_error_isolation(self) -> None:
        bus = EventBus()
        collected: list[FileEvent] = []

        async def good_handler(event: FileEvent) -> None:
            await _collecting_handler(collected, event)

        bus.register(EventType.FILE_WRITTEN, _failing_handler)
        bus.register(EventType.FILE_WRITTEN, good_handler)

        await bus.emit(FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt"))
        await bus.drain()
        assert len(collected) == 1

    async def test_error_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        bus = EventBus()
        bus.register(EventType.FILE_WRITTEN, _failing_handler)

        with caplog.at_level(logging.WARNING, logger="grover.events"):
            await bus.emit(FileEvent(event_type=EventType.FILE_WRITTEN, path="/a.txt"))
            await bus.drain()

        assert "failed" in caplog.text
        assert "file_written" in caplog.text
        assert "/a.txt" in caplog.text
