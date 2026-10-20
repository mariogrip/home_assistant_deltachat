"""The Delta Chat integration."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .bot import DeltaChatClient
from .const import CONF_ACCOUNT_ID, DOMAIN

_PLATFORMS: list[Platform] = [Platform.NOTIFY]


@dataclass
class DeltaChatData:
    """DeltaChat runtime data."""

    client: DeltaChatClient
    account_id: int


type DeltaChatConfigEntry = ConfigEntry[DeltaChatData]


async def async_setup_entry(hass: HomeAssistant, entry: DeltaChatConfigEntry) -> bool:
    """Set up Delta Chat from a config entry."""
    client = DeltaChatClient(
        hass.config.path(DOMAIN),
        on_died=lambda: hass.loop.call_soon_threadsafe(
            hass.config_entries.async_schedule_reload, entry.entry_id
        ),
    )
    try:
        await hass.async_add_executor_job(client.start)
    except Exception as ex:
        await hass.async_add_executor_job(client.close)
        raise ConfigEntryNotReady(f"Could not start Delta Chat: {ex}") from ex

    try:
        account_id = await _async_get_account_id(hass, entry, client)
        await hass.async_add_executor_job(client.start_account, account_id)
    except BaseException:
        await hass.async_add_executor_job(client.close)
        raise

    entry.runtime_data = DeltaChatData(client, account_id)
    _remove_stale_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    return True


async def _async_get_account_id(
    hass: HomeAssistant, entry: DeltaChatConfigEntry, client: DeltaChatClient
) -> int:
    """Return the entry's bot account."""
    account_id = entry.data.get(CONF_ACCOUNT_ID)
    if account_id is None:
        # Entries created before the account id was stored used the first
        # configured account.
        account_id = await hass.async_add_executor_job(client.first_configured_account)
        if account_id is not None:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_ACCOUNT_ID: account_id}
            )
    if account_id is None or not await hass.async_add_executor_job(
        client.is_configured, account_id
    ):
        raise ConfigEntryError(
            "The Delta Chat bot account is missing, remove and re-add the integration"
        )
    return account_id


def _remove_stale_entities(hass: HomeAssistant, entry: DeltaChatConfigEntry) -> None:
    """Remove entities of recipients that are no longer configured."""
    recipients = {recipient["email"] for recipient in entry.data[CONF_EMAIL]}
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id not in recipients:
            registry.async_remove(entity.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: DeltaChatConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: DeltaChatConfigEntry) -> None:
    """Delete the bot account when the integration is removed.

    There is only one entry, so it owns the whole data directory.
    """
    await hass.async_add_executor_job(shutil.rmtree, hass.config.path(DOMAIN), True)
