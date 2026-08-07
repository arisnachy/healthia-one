import asyncio

from healthia_one.config import Settings
from healthia_one.service import HealthIAService


def test_chat_publishes_message_and_state_refresh_events() -> None:
    service = HealthIAService(
        Settings(
            llm_backend="mock",
            store_backend="memory",
            proactive_enabled=False,
        )
    )
    published: list[dict] = []

    async def capture(payload: dict) -> None:
        published.append(payload)

    service.broker.publish = capture
    asyncio.run(service.add_patient_message("Hola"))

    assert [item["type"] for item in published] == ["message", "state"]
    assert published[1] == {"type": "state", "section": "chat"}
