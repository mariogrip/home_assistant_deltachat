"""Test the Delta Chat config flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_chat.bot import ConfigurationFailed, Contact
from custom_components.delta_chat.const import (
    CONF_ACCOUNT_ID,
    CONF_DELTACHAT_RELAY,
    DEFAULT_RELAY,
    DOMAIN,
    SUBENTRY_RECIPIENT,
)

from .conftest import BOT_ADDRESS, INVITE

FLOW_CLIENT = "custom_components.delta_chat.config_flow.DeltaChatClient"


@pytest.fixture
def flow_client() -> Generator[MagicMock]:
    """Mock the client the config flow runs during setup."""
    with patch(FLOW_CLIENT, autospec=True) as client_cls:
        client = client_cls.return_value
        client.setup_account.return_value = 1
        client.get_invite.return_value = INVITE
        client.get_address.return_value = BOT_ADDRESS
        client.get_contacts.return_value = []
        yield client


async def _start_flow(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DELTACHAT_RELAY: f" {DEFAULT_RELAY} "}
    )


async def test_form(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, flow_client: MagicMock
) -> None:
    """Test creating the bot and picking a recipient who joined during setup."""
    result = await _start_flow(hass)

    flow_client.setup_account.assert_called_once_with(DEFAULT_RELAY)
    # The bot is connected so people can join while the invite is shown.
    flow_client.start_account.assert_called_once_with(1)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "invite"
    assert result["description_placeholders"] == {"invite": INVITE}
    assert "recipients" not in result["data_schema"].schema

    # Submitting before anyone joined asks to scan first.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "no_contacts"}
    flow_client.close.assert_not_called()

    # Alice and Bob join; submitting again refreshes the list.
    flow_client.get_contacts.return_value = [
        Contact("alice@example.org", "Alice"),
        Contact("bob@example.org", "Bob"),
    ]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}
    options = result["data_schema"].schema["recipients"].config["options"]
    assert [option["label"] for option in options] == [
        "Alice (alice@example.org)",
        "Bob (bob@example.org)",
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"recipients": ["alice@example.org"]}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Delta Chat ({BOT_ADDRESS})"
    assert result["data"] == {CONF_DELTACHAT_RELAY: DEFAULT_RELAY, CONF_ACCOUNT_ID: 1}
    entry = result["result"]
    assert [
        (s.subentry_type, s.title, s.unique_id, dict(s.data))
        for s in entry.subentries.values()
    ] == [
        (
            SUBENTRY_RECIPIENT,
            "Alice",
            "alice@example.org",
            {CONF_EMAIL: "alice@example.org", CONF_NAME: "Alice"},
        )
    ]
    # Stopped before the entry starts its own client on the same data.
    flow_client.close.assert_called_once()
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_skip_recipients(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, flow_client: MagicMock
) -> None:
    """Test finishing setup without recipients."""
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"skip": True}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not result["result"].subentries
    flow_client.close.assert_called_once()


async def test_form_closed_stops_client(
    hass: HomeAssistant, flow_client: MagicMock
) -> None:
    """Test closing the dialog during setup stops the bot."""
    result = await _start_flow(hass)
    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()

    flow_client.close.assert_called_once()


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [(ConfigurationFailed("nope"), "cannot_connect"), (RuntimeError, "unknown")],
)
async def test_form_errors(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    flow_client: MagicMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test we handle account creation errors and can recover."""
    flow_client.setup_account.side_effect = side_effect
    result = await _start_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    flow_client.close.assert_called_once()

    flow_client.setup_account.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DELTACHAT_RELAY: DEFAULT_RELAY}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"skip": True}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(mock_setup_entry.mock_calls) == 1


async def test_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry, flow_client: MagicMock
) -> None:
    """Test a second setup aborts without creating an account."""
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    flow_client.setup_account.assert_not_called()


async def _start_recipient_flow(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> dict:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, SUBENTRY_RECIPIENT),
        context={"source": config_entries.SOURCE_USER},
    )


async def test_add_recipient(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test adding a recipient from the bot's contacts."""
    mock_client.get_contacts.return_value = [
        Contact("alice@example.org", "Alice"),
        Contact("carol@example.org", "Carol"),
    ]
    result = await _start_recipient_flow(hass, config_entry)

    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {"invite": INVITE}
    # Alice is already a recipient, so only Carol can be picked.
    options = result["data_schema"].schema["contact"].config["options"]
    assert [option["value"] for option in options] == ["carol@example.org"]

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"contact": "carol@example.org"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(s for s in config_entry.subentries.values() if s.title == "Carol")
    assert subentry.unique_id == "carol@example.org"
    assert subentry.data == {CONF_EMAIL: "carol@example.org", CONF_NAME: "Carol"}
    # The entry was reloaded, so the new recipient has an entity.
    assert hass.states.get("notify.delta_chat_carol") is not None


async def test_add_recipient_nobody_joined(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test the form asks to scan the invite when nobody new joined."""
    result = await _start_recipient_flow(hass, config_entry)
    assert result["type"] is FlowResultType.FORM
    assert "contact" not in result["data_schema"].schema

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "no_contacts"}

    # Someone joins, and submitting again lists them.
    mock_client.get_contacts.return_value = [Contact("carol@example.org", "Carol")]
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    assert result["errors"] == {}
    assert "contact" in result["data_schema"].schema


async def test_add_recipient_not_loaded(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Test recipients can't be added while the integration isn't loaded."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, SUBENTRY_RECIPIENT),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_loaded"
