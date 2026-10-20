"""Test the Delta Chat config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_chat.bot import ConfigurationFailed
from custom_components.delta_chat.const import (
    CONF_ACCOUNT_ID,
    CONF_ADD_ANOTHER,
    CONF_DELTACHAT_RELAY,
    CONF_INVITE,
    CONF_RECIPIENTS,
    DEFAULT_RELAY,
    DOMAIN,
)

from .conftest import BOT_ADDRESS, INVITE

CREATE_ACCOUNT = "custom_components.delta_chat.config_flow._create_account"


async def test_form(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test the full flow with two recipients."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch(CREATE_ACCOUNT, return_value=(1, INVITE, BOT_ADDRESS)) as create:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DELTACHAT_RELAY: f" {DEFAULT_RELAY} "}
        )
    create.assert_called_once_with(hass.config.path(DOMAIN), DEFAULT_RELAY)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "email"
    assert result["description_placeholders"] == {"invite": INVITE}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "alice@example.org", CONF_NAME: "Alice", CONF_ADD_ANOTHER: True},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "email"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "Alice@example.org"}
    )
    assert result["errors"] == {CONF_EMAIL: "already_added"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "not-an-address"}
    )
    assert result["errors"] == {CONF_EMAIL: "invalid_email"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "bob@example.org"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Delta Chat ({BOT_ADDRESS})"
    assert result["data"] == {
        CONF_DELTACHAT_RELAY: DEFAULT_RELAY,
        CONF_ACCOUNT_ID: 1,
        CONF_INVITE: INVITE,
        CONF_EMAIL: [
            {"email": "alice@example.org", "name": "Alice"},
            {"email": "bob@example.org", "name": "bob@example.org"},
        ],
    }
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [(ConfigurationFailed("nope"), "cannot_connect"), (RuntimeError, "unknown")],
)
async def test_form_errors(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test we handle account creation errors and can recover."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(CREATE_ACCOUNT, side_effect=side_effect):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DELTACHAT_RELAY: DEFAULT_RELAY}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    with patch(CREATE_ACCOUNT, return_value=(1, INVITE, BOT_ADDRESS)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DELTACHAT_RELAY: DEFAULT_RELAY}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "alice@example.org"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(mock_setup_entry.mock_calls) == 1


async def test_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Test a second setup aborts without creating an account."""
    config_entry.add_to_hass(hass)

    with patch(CREATE_ACCOUNT) as create:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    assert result["type"] is FlowResultType.ABORT
    create.assert_not_called()


async def test_reconfigure(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test reconfigure keeps, removes and adds recipients."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["description_placeholders"] == {"invite": INVITE}

    # Remove Bob, add Carol and ask to add another one.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_RECIPIENTS: ["alice@example.org"],
            CONF_EMAIL: "carol@example.org",
            CONF_NAME: "Carol",
            CONF_ADD_ANOTHER: True,
        },
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_RECIPIENTS: ["alice@example.org", "carol@example.org"]},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_EMAIL] == [
        {"email": "alice@example.org", "name": "Alice"},
        {"email": "carol@example.org", "name": "Carol"},
    ]
    assert config_entry.data[CONF_ACCOUNT_ID] == 1
