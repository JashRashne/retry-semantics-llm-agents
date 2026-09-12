from __future__ import annotations

import pytest

from retry_semantics.environments.ticket import FrozenExecutableRequest


@pytest.fixture
def make_request():
    def factory(
        *,
        tool: str = "create_ticket",
        tool_call_id: str = "call-001",
        customer_id: str = "CUST-001",
        title: str = "Login page timeout",
        description: str = "The login page times out after 30 seconds.",
        arguments: dict | None = None,
    ) -> FrozenExecutableRequest:
        if arguments is None:
            arguments = (
                {
                    "customer_id": customer_id,
                    "title": title,
                    "description": description,
                }
                if tool == "create_ticket"
                else {}
            )
        return FrozenExecutableRequest.from_value(
            {
                "tool_call_id": tool_call_id,
                "tool": tool,
                "arguments": arguments,
            }
        )

    return factory

