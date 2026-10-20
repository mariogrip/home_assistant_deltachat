"""Test the Delta Chat setup."""

import os
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_chat.const import CONF_ACCOUNT_ID, DOMAIN


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


async def test_setup_migrates_account_id(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test entries without an account id use the first configured account."""
    data = dict(config_entry.data)
    del data[CONF_ACCOUNT_ID]
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=data)
    entry.add_to_hass(hass)
    mock_client.first_configured_account.return_value = 3

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.data[CONF_ACCOUNT_ID] == 3
    mock_client.start_account.assert_called_once_with(3)


async def test_stale_entities_removed(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Test entities of removed recipients are removed."""
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "notify", DOMAIN, "gone@example.org", config_entry=config_entry
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    unique_ids = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }
    assert unique_ids == {"alice@example.org", "bob@example.org"}


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
