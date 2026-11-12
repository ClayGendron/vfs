"""The byte batcher: items cut by a byte budget, one flush law behind two doors."""

from __future__ import annotations

from vfs.batching import ByteBatcher, byte_chunked


class TestByteChunked:
    """The byte-bounded batcher's laws — one owner for every batching site."""

    def test_items_emit_exactly_once_in_order(self) -> None:
        items = ["aa", "bbb", "c", "dddd", "ee", "f"]
        batches = list(byte_chunked(items, len, 5))
        assert [item for batch in batches for item in batch] == items

    def test_multi_item_batches_respect_the_budget(self) -> None:
        items = ["aa", "bbb", "c", "dddd", "ee", "f"]
        for batch in byte_chunked(items, len, 5):
            if len(batch) > 1:
                assert sum(len(item) for item in batch) <= 5

    def test_an_oversized_item_rides_alone(self) -> None:
        items = ["aa", "way-over-budget", "bb"]
        batches = list(byte_chunked(items, len, 4))
        assert ["way-over-budget"] in batches
        assert all(sum(len(i) for i in b) <= 4 for b in batches if b != ["way-over-budget"])

    def test_the_flush_is_pre_add_never_post_add(self) -> None:
        # Post-add would pack ["aaa", "bb"] (5 > 4) into one batch before
        # flushing; the pre-add law flushes ["aaa"] and starts fresh.
        assert list(byte_chunked(["aaa", "bb"], len, 4)) == [["aaa"], ["bb"]]

    def test_the_tail_batch_is_emitted(self) -> None:
        assert list(byte_chunked(["aaa", "b"], len, 3)) == [["aaa"], ["b"]]

    def test_empty_items_yield_no_batches(self) -> None:
        assert list(byte_chunked([], len, 4)) == []

    def test_the_incremental_form_agrees_with_the_generator(self) -> None:
        # One flush law, two doors: a streaming producer feeding
        # ByteBatcher sees the same batches byte_chunked yields.
        items = ["aa", "bbb", "c", "dddd", "ee", "f", "gggggg"]
        batcher = ByteBatcher(len, 5)
        streamed = [full for item in items if (full := batcher.add(item)) is not None]
        if (final := batcher.flush()) is not None:
            streamed.append(final)
        assert streamed == list(byte_chunked(items, len, 5))
