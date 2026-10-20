"""Config flow for the Delta Chat integration."""

from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_EMAIL, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    QrCodeSelector,
    QrCodeSelectorConfig,
    QrErrorCorrectionLevel,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .bot import ConfigurationFailed, DeltaChatClient
from .const import (
    CONF_ACCOUNT_ID,
    CONF_DELTACHAT_RELAY,
    CONF_INVITE,
    DEFAULT_RELAY,
    DOMAIN,
    SUBENTRY_RECIPIENT,
)

_LOGGER = logging.getLogger(__name__)

CONF_CONTACT = "contact"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DELTACHAT_RELAY, default=DEFAULT_RELAY): cv.string,
    }
)


def _create_account(data_dir: str, relay: str) -> tuple[int, str, str]:
    """Create the bot account and return its id, invite link and address."""
    client = DeltaChatClient(data_dir)
    try:
        client.start()
        account_id = client.setup_account(relay)
        return account_id, client.get_invite(account_id), client.get_address(account_id)
    finally:
        client.close()


def _invite_field(invite: str) -> dict[vol.Marker, Any]:
    """Return a form field that shows the invite as a QR code."""
    return {
        vol.Optional(CONF_INVITE): QrCodeSelector(
            QrCodeSelectorConfig(
                data=invite,
                scale=5,
                error_correction_level=QrErrorCorrectionLevel.QUARTILE,
            )
        )
    }


class DeltaChatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Delta Chat."""

    VERSION = 1

    data: dict[str, Any]
    address: str
    invite: str

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types the integration supports."""
        return {SUBENTRY_RECIPIENT: RecipientSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        # Check before creating an account, so an aborted flow leaves none behind.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            relay = user_input[CONF_DELTACHAT_RELAY].strip()
            try:
                (
                    account_id,
                    self.invite,
                    self.address,
                ) = await self.hass.async_add_executor_job(
                    _create_account, self.hass.config.path(DOMAIN), relay
                )
            except ConfigurationFailed as err:
                _LOGGER.warning("Could not create a Delta Chat account: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.data = {CONF_DELTACHAT_RELAY: relay, CONF_ACCOUNT_ID: account_id}
                return await self.async_step_invite()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_invite(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the bot's invite, then create the entry."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Delta Chat ({self.address})", data=self.data
            )

        return self.async_show_form(
            step_id="invite",
            data_schema=vol.Schema(_invite_field(self.invite)),
            description_placeholders={"invite": self.invite},
        )


class RecipientSubentryFlow(ConfigSubentryFlow):
    """Add a recipient from the people who joined the bot."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Pick a contact of the bot."""
        entry: ConfigEntry = self.hass.config_entries.async_get_known_entry(
            self.handler[0]
        )
        if entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="not_loaded")
        client: DeltaChatClient = entry.runtime_data.client
        account_id: int = entry.runtime_data.account_id

        recipients = {
            subentry.unique_id
            for subentry in entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_RECIPIENT
        }
        contacts = {
            contact.address: contact
            for contact in await self.hass.async_add_executor_job(
                client.get_contacts, account_id
            )
            if contact.address.lower() not in recipients
        }

        errors: dict[str, str] = {}
        if user_input is not None:
            if (contact := contacts.get(user_input.get(CONF_CONTACT, ""))) is not None:
                return self.async_create_entry(
                    title=contact.name,
                    data={CONF_EMAIL: contact.address, CONF_NAME: contact.name},
                    unique_id=contact.address.lower(),
                )
            if not contacts:
                errors["base"] = "no_contacts"

        invite = await self.hass.async_add_executor_job(client.get_invite, account_id)
        schema: dict[vol.Marker, Any] = _invite_field(invite)
        if contacts:
            schema[vol.Required(CONF_CONTACT)] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            value=contact.address,
                            label=f"{contact.name} ({contact.address})",
                        )
                        for contact in contacts.values()
                    ]
                )
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"invite": invite},
        )
