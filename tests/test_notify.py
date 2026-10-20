"""Test the Delta Chat notify platform."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.notify import (
    ATTR_MESSAGE,
    ATTR_TITLE,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.components.notify.const import DOMAIN as NOTIFY_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_chat.bot import ContactNotFound
from custom_components.delta_chat.const import SEND_TIMEOUT

ENTITY_ID = "notify.delta_chat_alice"


@pytest.fixture(autouse=True)
async def setup_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Set up the integration."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_entities(hass: HomeAssistant) -> None:
    """Test there is a named entity per recipient."""
    assert hass.states.get(ENTITY_ID).attributes[ATTR_FRIENDLY_NAME] == (
        "Delta Chat Alice"
    )
    assert hass.states.get("notify.delta_chat_bob") is not None


async def test_send_message(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test a message is sent to the recipient."""
    await hass.services.async_call(
        NOTIFY_DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MESSAGE: "hello"},
        blocking=True,
    )
    mock_client.send_message.assert_called_once_with(
        1, "alice@example.org", "hello", SEND_TIMEOUT
    )


async def test_send_message_with_title(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Test the title is prepended to the message."""
    await hass.services.async_call(
        NOTIFY_DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MESSAGE: "hello", ATTR_TITLE: "Door"},
        blocking=True,
    )
    mock_client.send_message.assert_called_once_with(
        1, "alice@example.org", "Door\n\nhello", SEND_TIMEOUT
    )


async def test_send_message_error(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test client errors are raised to the caller."""
    mock_client.send_message.side_effect = ContactNotFound("not a contact")
    with pytest.raises(HomeAssistantError, match="not a contact"):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MESSAGE: "hello"},
            blocking=True,
        )
