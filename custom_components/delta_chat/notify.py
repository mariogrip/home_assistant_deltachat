"""DeltaChat for notify component."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.const import CONF_EMAIL, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeltaChatConfigEntry
from .const import DOMAIN, SEND_TIMEOUT, SUBENTRY_RECIPIENT


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DeltaChatConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a notify entity for each recipient."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_RECIPIENT:
            continue
        async_add_entities(
            [
                DeltaChatNotify(
                    config_entry, subentry.data[CONF_EMAIL], subentry.data[CONF_NAME]
                )
            ],
            config_subentry_id=subentry.subentry_id,
        )


class DeltaChatNotify(NotifyEntity):
    """Representation of a notification entity service that can send messages using DeltaChat."""

    _attr_has_entity_name = True

    def __init__(self, config: DeltaChatConfigEntry, email: str, name: str) -> None:
        """Initialize a DeltaChat notification."""
        self._attr_unique_id = email
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config.entry_id)},
            name="Delta Chat",
            manufacturer="Delta Chat",
            entry_type=DeviceEntryType.SERVICE,
        )
        self.contact = email
        self.data = config.runtime_data

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a message."""
        text = f"{title}\n\n{message}" if title else message
        await self.hass.async_add_executor_job(
            self.data.client.send_message,
            self.data.account_id,
            self.contact,
            text,
            SEND_TIMEOUT,
        )
