"""Config flow for the Delta Chat integration."""

from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_NAME
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .bot import ConfigurationFailed, DeltaChatClient
from .const import (
    CONF_ACCOUNT_ID,
    CONF_ADD_ANOTHER,
    CONF_DELTACHAT_RELAY,
    CONF_INVITE,
    CONF_RECIPIENTS,
    DEFAULT_RELAY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DELTACHAT_RELAY, default=DEFAULT_RELAY): cv.string,
    }
)

STEP_EMAIL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ADD_ANOTHER): cv.boolean,
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


def _add_recipient(
    recipients: list[dict[str, str]], user_input: dict[str, Any], errors: dict[str, str]
) -> None:
    """Add the recipient from user_input, or set an error."""
    email = user_input[CONF_EMAIL].strip()
    if "@" not in email:
        errors[CONF_EMAIL] = "invalid_email"
    elif any(r["email"].lower() == email.lower() for r in recipients):
        errors[CONF_EMAIL] = "already_added"
    else:
        recipients.append({"email": email, "name": user_input.get(CONF_NAME) or email})


class DeltaChatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Delta Chat."""

    VERSION = 1

    data: dict[str, Any]
    address: str
    recipients: list[dict[str, str]]

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
                    invite,
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
                self.data = {
                    CONF_DELTACHAT_RELAY: relay,
                    CONF_ACCOUNT_ID: account_id,
                    CONF_INVITE: invite,
                }
                self.recipients = []
                return await self.async_step_email()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second step in config flow to add emails to notify."""
        errors: dict[str, str] = {}
        if user_input is not None:
            _add_recipient(self.recipients, user_input, errors)
            # If user ticked the box show this form again so they can add an
            # additional email.
            if not errors and not user_input.get(CONF_ADD_ANOTHER, False):
                return self.async_create_entry(
                    title=f"Delta Chat ({self.address})",
                    data={**self.data, CONF_EMAIL: self.recipients},
                )

        return self.async_show_form(
            step_id="email",
            data_schema=STEP_EMAIL_SCHEMA,
            errors=errors,
            description_placeholders={"invite": self.data[CONF_INVITE]},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add or remove recipients."""
        entry = self._get_reconfigure_entry()
        if not hasattr(self, "recipients"):
            self.recipients = list(entry.data[CONF_EMAIL])

        errors: dict[str, str] = {}
        if user_input is not None:
            keep = set(user_input.get(CONF_RECIPIENTS, []))
            self.recipients = [r for r in self.recipients if r["email"] in keep]
            if user_input.get(CONF_EMAIL):
                _add_recipient(self.recipients, user_input, errors)
            if not errors and not user_input.get(CONF_ADD_ANOTHER, False):
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_EMAIL: self.recipients}
                )

        options = [
            SelectOptionDict(value=r["email"], label=f"{r['name']} <{r['email']}>")
            for r in self.recipients
        ]
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RECIPIENTS, default=[r["email"] for r in self.recipients]
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(CONF_EMAIL): cv.string,
                vol.Optional(CONF_NAME): cv.string,
                vol.Optional(CONF_ADD_ANOTHER): cv.boolean,
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders={"invite": entry.data.get(CONF_INVITE, "")},
        )
