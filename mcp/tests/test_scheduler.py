import asyncio
import errno
import unittest

from telethon.errors import FloodWaitError

from telegram_mcp.errors import ToolContractError
from telegram_mcp.scheduler import TelegramOperationScheduler


def _run(awaitable):
    return asyncio.run(awaitable)


class SchedulerTests(unittest.TestCase):
    def test_scheduler_serializes_single_lane(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
            )
            first_started = asyncio.Event()
            release_first = asyncio.Event()
            order: list[str] = []

            async def first():
                order.append("first:start")
                first_started.set()
                await release_first.wait()
                order.append("first:end")
                return "first"

            async def second():
                order.append("second:start")
                return "second"

            first_task = asyncio.create_task(
                scheduler.run("read", "first", 5.0, first)
            )
            await first_started.wait()
            second_task = asyncio.create_task(
                scheduler.run("read", "second", 5.0, second)
            )
            await asyncio.sleep(0)

            snapshot = scheduler.snapshot()["read"]
            self.assertEqual(snapshot["active"], 1)
            self.assertEqual(snapshot["queued"], 1)

            release_first.set()
            result = await asyncio.gather(first_task, second_task)

            self.assertEqual(result, ["first", "second"])
            self.assertEqual(
                order,
                ["first:start", "first:end", "second:start"],
            )

        _run(scenario())

    def test_scheduler_timeout_reports_contract_error(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
            )

            async def blocked():
                await asyncio.sleep(1)

            with self.assertRaises(ToolContractError) as ctx:
                await scheduler.run("media", "download_media", 0.01, blocked)

            self.assertEqual(ctx.exception.code, "operation_timeout")
            snapshot = scheduler.snapshot()["media"]
            self.assertEqual(snapshot["timed_out"], 1)
            self.assertEqual(snapshot["active"], 0)

        _run(scenario())

    def test_scheduler_converts_flood_wait_to_rate_limited(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
            )

            async def rate_limited():
                exc = FloodWaitError(None)
                exc.seconds = 42
                raise exc

            with self.assertRaises(ToolContractError) as ctx:
                await scheduler.run("write", "send_message", 1.0, rate_limited)

            self.assertEqual(ctx.exception.code, "rate_limited")
            snapshot = scheduler.snapshot()["write"]
            self.assertEqual(snapshot["rate_limited"], 1)
            self.assertEqual(snapshot["last_flood_wait_seconds"], 42)
            self.assertEqual(
                snapshot["circuit_breakers"]["flood_wait"]["state"],
                "open",
            )

        _run(scenario())

    def test_scheduler_fast_fails_open_flood_wait_circuit_without_factory(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
            )
            factory_calls = 0

            async def rate_limited():
                nonlocal factory_calls
                factory_calls += 1
                exc = FloodWaitError(None)
                exc.seconds = 30
                raise exc

            with self.assertRaises(ToolContractError):
                await scheduler.run("write", "send_message", 1.0, rate_limited)

            async def should_not_run():
                nonlocal factory_calls
                factory_calls += 1

            with self.assertRaises(ToolContractError) as ctx:
                await scheduler.run("write", "edit_message", 1.0, should_not_run)

            self.assertEqual(ctx.exception.code, "rate_limited")
            self.assertEqual(factory_calls, 1)
            snapshot = scheduler.snapshot()["write"]
            self.assertEqual(snapshot["labels"]["edit_message"]["failed"], 1)
            self.assertEqual(
                snapshot["recent_events"][-1]["status"],
                "circuit_open",
            )

        _run(scenario())

    def test_scheduler_does_not_open_circuit_for_user_contract_errors(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
            )

            async def forbidden():
                raise ToolContractError("permission_denied", "not allowed")

            with self.assertRaises(ToolContractError):
                await scheduler.run("write", "delete_messages", 1.0, forbidden)

            snapshot = scheduler.snapshot()["write"]
            self.assertEqual(snapshot["circuit_breakers"], {})

        _run(scenario())

    def test_scheduler_opens_transport_circuit_after_threshold(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
                circuit_breaker_failure_threshold=2,
            )

            async def connection_lost():
                raise ConnectionError("network down")

            for _ in range(2):
                with self.assertRaises(ConnectionError):
                    await scheduler.run("read", "list_chats", 1.0, connection_lost)

            snapshot = scheduler.snapshot()["read"]
            self.assertEqual(
                snapshot["circuit_breakers"]["transport"]["state"],
                "open",
            )

        _run(scenario())

    def test_scheduler_opens_transport_circuit_for_network_oserror_errno(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
                circuit_breaker_failure_threshold=2,
            )

            async def network_reset():
                raise OSError(errno.ECONNRESET, "connection reset")

            for _ in range(2):
                with self.assertRaises(OSError):
                    await scheduler.run("media", "download_media", 1.0, network_reset)

            snapshot = scheduler.snapshot()["media"]
            self.assertEqual(
                snapshot["circuit_breakers"]["transport"]["state"],
                "open",
            )

        _run(scenario())

    def test_scheduler_does_not_open_circuit_for_local_file_input_errors(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
                circuit_breaker_failure_threshold=2,
            )

            async def missing_file():
                raise FileNotFoundError("/tmp/missing.oga")

            for _ in range(2):
                with self.assertRaises(FileNotFoundError):
                    await scheduler.run("media", "send_voice", 1.0, missing_file)

            snapshot = scheduler.snapshot()["media"]
            self.assertEqual(snapshot["circuit_breakers"], {})

            async def valid_media_call():
                return "ok"

            result = await scheduler.run("media", "send_file", 1.0, valid_media_call)

            self.assertEqual(result, "ok")
            self.assertEqual(scheduler.snapshot()["media"]["completed"], 1)

        _run(scenario())

    def test_scheduler_records_bounded_label_metrics_and_events(self):
        async def scenario():
            scheduler = TelegramOperationScheduler(
                read_concurrency=1,
                write_concurrency=1,
                media_concurrency=1,
                transcribe_concurrency=1,
                enrich_concurrency=1,
                label_limit=2,
                event_limit=2,
            )

            async def ok():
                return "ok"

            self.assertEqual(await scheduler.run("enrich", "first", 1.0, ok), "ok")
            self.assertEqual(await scheduler.run("enrich", "second", 1.0, ok), "ok")
            self.assertEqual(await scheduler.run("enrich", "third", 1.0, ok), "ok")

            snapshot = scheduler.snapshot()["enrich"]
            self.assertEqual(snapshot["completed"], 3)
            self.assertEqual(snapshot["active"], 0)
            self.assertEqual(list(snapshot["labels"]), ["second", "third"])
            self.assertEqual(snapshot["labels"]["third"]["succeeded"], 1)
            self.assertIsNotNone(snapshot["labels"]["third"]["p95_duration_ms"])
            self.assertEqual(
                [event["label"] for event in snapshot["recent_events"]],
                ["second", "third"],
            )

        _run(scenario())
