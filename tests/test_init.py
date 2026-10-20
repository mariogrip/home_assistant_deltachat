"""Test the Delta Chat setup."""

import os
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_chat.bot import Contact
from custom_components.delta_chat.const import DOMAIN


async def test_setup_and_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test the client is started on setup and closed on unload."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    mock_client.start.assert_called_once()
    mock_client.start_account.assert_called_once_with(1)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    mock_client.close.assert_called_once()


async def test_setup_start_fails(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test setup is retried when the core can not start."""
    mock_client.start.side_effect = OSError("no deltachat-rpc-server")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_client.close.assert_called_once()


async def test_setup_account_missing(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test setup fails when the bot account is gone."""
    mock_client.is_configured.return_value = False
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    mock_client.close.assert_called_once()


async def test_joined_notification(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test a notification is shown when someone joins the bot."""
    config_entry.add_to_hass(hass)
    with patch("custom_components.delta_chat.DeltaChatClient") as client_cls:
        client_cls.return_value = mock_client
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    on_joined = client_cls.call_args.kwargs["on_joined"]

    with patch(
        "custom_components.delta_chat.persistent_notification.async_create"
    ) as create:
        await hass.async_add_executor_job(
            on_joined, Contact("carol@example.org", "Carol")
        )
        await hass.async_block_till_done()

    create.assert_called_once()
    assert "**Carol** (carol@example.org)" in create.call_args.args[1]
    assert create.call_args.kwargs["notification_id"] == (
        "delta_chat_joined_carol@example.org"
    )


async def test_removing_recipient_removes_entity(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test deleting a recipient removes its entity."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("notify.delta_chat_bob") is not None

    bob = next(s for s in config_entry.subentries.values() if s.title == "Bob")
    hass.config_entries.async_remove_subentry(config_entry, bob.subentry_id)
    await hass.async_block_till_done()

    assert hass.states.get("notify.delta_chat_bob") is None
    assert hass.states.get("notify.delta_chat_alice") is not None


async def test_remove_entry_deletes_data(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test removing the entry deletes the bot account data."""
    data_dir = hass.config.path(DOMAIN)
    await hass.async_add_executor_job(os.makedirs, os.path.join(data_dir, "accounts"))
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)

    await hass.config_entries.async_remove(config_entry.entry_id)

    assert not await hass.async_add_executor_job(os.path.exists, data_dir)
