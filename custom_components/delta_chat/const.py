"""Constants for the Delta Chat integration."""

from typing import Final

DOMAIN: Final = "delta_chat"

CONF_DELTACHAT_RELAY: Final = "relay"
CONF_ACCOUNT_ID: Final = "account_id"
CONF_INVITE: Final = "qrdata"
CONF_ADD_ANOTHER: Final = "add another"
CONF_RECIPIENTS: Final = "recipients"
DEFAULT_RELAY: Final = "nine.testrun.org"

# Seconds to wait for a message to be delivered before giving up waiting.
SEND_TIMEOUT: Final = 60
