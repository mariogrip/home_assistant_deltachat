"""Constants for the Delta Chat integration."""

from typing import Final

DOMAIN: Final = "delta_chat"

CONF_DELTACHAT_RELAY: Final = "relay"
CONF_ACCOUNT_ID: Final = "account_id"
CONF_INVITE: Final = "invite"
DEFAULT_RELAY: Final = "nine.testrun.org"

SUBENTRY_RECIPIENT: Final = "recipient"

# Seconds to wait for a message to be delivered before giving up waiting.
SEND_TIMEOUT: Final = 60
