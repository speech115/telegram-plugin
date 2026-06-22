import unittest

from telegram_mcp.prometheus_registry import (
    PrometheusRegistry,
    record_prometheus_from_event,
    reset_prometheus_registry_for_tests,
)


class PrometheusRegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_prometheus_registry_for_tests()

    def test_renders_counters_and_histogram(self) -> None:
        registry = PrometheusRegistry()
        registry.observe_tool_call(tool="telegram_read", status="ok", duration_ms=120.0, source="mcp_tool")
        registry.observe_tool_call(tool="telegram_read", status="ok", duration_ms=40.0, source="mcp_tool")
        text = registry.render()
        self.assertIn("telegram_mcp_tool_calls_total", text)
        self.assertIn('tool="telegram_read"', text)
        self.assertIn("telegram_mcp_tool_duration_ms_bucket", text)
        self.assertIn(
            'telegram_mcp_tool_duration_ms_bucket{le="25",tool="telegram_read",source="mcp_tool"}',
            text,
        )
        self.assertNotIn('}{tool="telegram_read"', text)

    def test_records_write_operation_metrics(self) -> None:
        record_prometheus_from_event(
            "write_operation",
            {
                "operation": "send_message",
                "status": "error",
                "duration_ms": 80.0,
                "source": "mcp_server",
            },
        )

        text = PrometheusRegistry().render()
        self.assertNotIn("telegram_mcp_write_operations_total", text)

        from telegram_mcp.prometheus_registry import get_prometheus_registry

        text = get_prometheus_registry().render()
        self.assertIn("telegram_mcp_write_operations_total", text)
        self.assertIn('operation="send_message"', text)
        self.assertIn('status="error"', text)
        self.assertIn("telegram_mcp_write_duration_ms_bucket", text)

    def test_preflight_violation_keeps_traffic_class_label(self) -> None:
        record_prometheus_from_event(
            "preflight_violation",
            {
                "tool": "get_me",
                "source": "control_plane",
                "traffic_class": "synthetic_probe",
            },
        )

        from telegram_mcp.prometheus_registry import get_prometheus_registry

        text = get_prometheus_registry().render()
        self.assertIn('event="preflight_violation"', text)
        self.assertIn('traffic_class="synthetic_probe"', text)


if __name__ == "__main__":
    unittest.main()
