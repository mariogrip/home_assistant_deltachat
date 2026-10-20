"""Common fixtures for the Delta Chat tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_EMAIL, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_chat.const import (
    CONF_ACCOUNT_ID,
    CONF_DELTACHAT_RELAY,
    DEFAULT_RELAY,
    DOMAIN,
    SUBENTRY_RECIPIENT,
)

INVITE = "https://i.delta.chat/#ABCDEF"
BOT_ADDRESS = "bot@nine.testrun.org"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.delta_chat.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Mock the Delta Chat client used by the integration."""
    with patch(
        "custom_components.delta_chat.DeltaChatClient", autospec=True
    ) as client_cls:
        client = client_cls.return_value
        client.is_configured.return_value = True
        client.get_invite.return_value = INVITE
        client.get_contacts.return_value = []
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry with two recipients."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title=f"Delta Chat ({BOT_ADDRESS})",
        data={CONF_DELTACHAT_RELAY: DEFAULT_RELAY, CONF_ACCOUNT_ID: 1},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_RECIPIENT,
                title=name,
                unique_id=email,
                data={CONF_EMAIL: email, CONF_NAME: name},
            )
            for email, name in (
                ("alice@example.org", "Alice"),
                ("bob@example.org", "Bob"),
            )
        ],
    )
