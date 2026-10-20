"""The Delta Chat integration."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .bot import Contact, DeltaChatClient
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

    def on_joined(contact: Contact) -> None:
        hass.loop.call_soon_threadsafe(_notify_joined, hass, contact)

    client = DeltaChatClient(
        hass.config.path(DOMAIN),
        on_died=lambda: hass.loop.call_soon_threadsafe(
            hass.config_entries.async_schedule_reload, entry.entry_id
        ),
        on_joined=on_joined,
    )
    try:
        await hass.async_add_executor_job(client.start)
    except Exception as ex:
        await hass.async_add_executor_job(client.close)
        raise ConfigEntryNotReady(f"Could not start Delta Chat: {ex}") from ex

    try:
        account_id = entry.data[CONF_ACCOUNT_ID]
        if not await hass.async_add_executor_job(client.is_configured, account_id):
            raise ConfigEntryError(
                "The Delta Chat bot account is missing, "
                "remove and re-add the integration"
            )
        await hass.async_add_executor_job(client.start_account, account_id)
    except BaseException:
        await hass.async_add_executor_job(client.close)
        raise

    entry.runtime_data = DeltaChatData(client, account_id)
    # Adding or removing a recipient updates the entry; reload to apply it.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    return True


def _notify_joined(hass: HomeAssistant, contact: Contact) -> None:
    """Tell the user that someone can now be added as a recipient."""
    persistent_notification.async_create(
        hass,
        f"**{contact.name}** ({contact.address}) joined the Delta Chat bot. "
        "To send them notifications, open the "
        "[Delta Chat integration](/config/integrations/integration/delta_chat) "
        "and choose **Add recipient**.",
        title="Delta Chat",
        notification_id=f"{DOMAIN}_joined_{contact.address}",
    )


async def _async_reload(hass: HomeAssistant, entry: DeltaChatConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


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
