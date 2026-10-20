"""Common fixtures for the Delta Chat tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_EMAIL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delta_chat.const import (
    CONF_ACCOUNT_ID,
    CONF_DELTACHAT_RELAY,
    CONF_INVITE,
    DEFAULT_RELAY,
    DOMAIN,
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
        client.first_configured_account.return_value = 1
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry with two recipients."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title=f"Delta Chat ({BOT_ADDRESS})",
        data={
            CONF_DELTACHAT_RELAY: DEFAULT_RELAY,
            CONF_ACCOUNT_ID: 1,
            CONF_INVITE: INVITE,
            CONF_EMAIL: [
                {"email": "alice@example.org", "name": "Alice"},
                {"email": "bob@example.org", "name": "Bob"},
            ],
        },
    )
