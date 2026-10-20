"""Code related to the Delta Chat bot."""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from os import makedirs, path
from threading import Condition, Thread
from typing import Any

import deltachat_rpc_server
from deltachat2 import IOTransport, JsonRpcError, MsgData, Rpc
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

EVENT_MSG_DELIVERED = "MsgDelivered"
EVENT_MSG_FAILED = "MsgFailed"

# The binary ships inside the package; don't rely on its script being on PATH.
RPC_SERVER = path.join(
    path.dirname(deltachat_rpc_server.__file__), "deltachat-rpc-server"
)

# Keep at most this many delivery results that nobody is waiting for any more.
_MAX_PENDING_RESULTS = 100


class _Transport(IOTransport):
    """IOTransport that does not hang forever when the RPC server exits."""

    def _reader_loop(self) -> None:
        super()._reader_loop()
        # The server exited, so no more responses will come: fail the
        # requests still waiting instead of blocking their threads forever.
        for result in list(self.pending_results.values()):
            result.set({"error": {"message": "deltachat-rpc-server exited"}})
        self.pending_results.clear()

    def call(self, method: str, *args: Any) -> Any:
        if not self.reader_thread.is_alive():
            raise JsonRpcError({"message": "deltachat-rpc-server is not running"})
        return super().call(method, *args)


class DeltaChatClient:
    """A running Delta Chat core (deltachat-rpc-server) for one data directory.

    All methods do blocking I/O, so they must be run in the executor.
    """

    def __init__(
        self,
        data_dir: str,
        on_died: Callable[[], None] | None = None,
        on_joined: Callable[[Contact], None] | None = None,
    ) -> None:
        """Client constructor.

        on_died is called when the core stops unexpectedly, and on_joined when
        someone joins the bot with its invite. Both run in the event thread.
        """
        self.data_dir = data_dir
        self._on_died = on_died
        self._on_joined = on_joined
        self._transport: _Transport | None = None
        self.rpc: Rpc
        self._closing = False
        self._event_thread: Thread | None = None
        self._results: OrderedDict[int, str] = OrderedDict()
        self._results_cond = Condition()

    def start(self) -> None:
        """Start the RPC server and the event processing thread."""
        if not path.exists(self.data_dir):
            makedirs(self.data_dir)
        self._transport = _Transport(
            accounts_dir=path.join(self.data_dir, "accounts"), executable=RPC_SERVER
        )
        self._transport.start()
        self.rpc = Rpc(self._transport)
        _LOGGER.debug(
            "Running deltachat core %s",
            self.rpc.get_system_info().deltachat_core_version,
        )
        self._event_thread = Thread(
            target=self._event_loop, name="delta_chat_events", daemon=True
        )
        self._event_thread.start()

    def close(self) -> None:
        """Stop the RPC server."""
        self._closing = True
        transport = self._transport
        if transport is None:
            return
        if transport.process.poll() is None and transport.reader_thread.is_alive():
            transport.close()
        else:
            # The server already exited; stop the writer thread and reap it.
            transport.request_queue.put(None)
            transport.writer_thread.join(timeout=10)
            transport.process.wait(timeout=10)
        if self._event_thread is not None:
            self._event_thread.join(timeout=10)

    def _event_loop(self) -> None:
        """Process core events until the client is closed."""
        while not self._closing:
            try:
                raw_event = self.rpc.get_next_event()
            except JsonRpcError:
                if not self._closing:
                    _LOGGER.error("Delta Chat core stopped unexpectedly")
                    if self._on_died is not None:
                        self._on_died()
                return
            event = raw_event.event
            kind = event.kind
            if kind in (EVENT_MSG_DELIVERED, EVENT_MSG_FAILED):
                with self._results_cond:
                    self._results[event.msg_id] = kind
                    while len(self._results) > _MAX_PENDING_RESULTS:
                        self._results.popitem(last=False)
                    self._results_cond.notify_all()
            elif kind == "SecurejoinInviterProgress" and event.progress == 1000:
                _LOGGER.info("A new contact joined the bot")
                if self._on_joined is not None:
                    try:
                        contact = self.rpc.get_contact(
                            raw_event.context_id, event.contact_id
                        )
                        self._on_joined(_to_contact(contact))
                    except Exception:
                        _LOGGER.exception("Error handling a new contact")
            elif kind == "Warning":
                _LOGGER.debug("Delta Chat core: %s", event.msg)
            elif kind == "Error":
                _LOGGER.warning("Delta Chat core: %s", event.msg)

    def setup_account(self, relay: str) -> int:
        """Return a configured account on the relay, creating it if needed.

        Accounts left over from aborted or failed setups are removed.
        """
        account_id = None
        for accid in self.rpc.get_all_account_ids():
            if (
                account_id is None
                and self.rpc.is_configured(accid)
                and any(
                    addr.endswith(f"@{relay}") for addr in self._get_addresses(accid)
                )
            ):
                account_id = accid
                continue
            _LOGGER.debug("Removing unused account %s", accid)
            self.rpc.remove_account(accid)
        if account_id is not None:
            _LOGGER.debug("Reusing account %s", account_id)
            return account_id

        account_id = self.rpc.add_account()
        _LOGGER.debug("Configuring account %s on %s", account_id, relay)
        self.rpc.set_config(account_id, "bot", "1")
        self.rpc.set_config(account_id, "displayname", "Home Assistant")
        try:
            self.rpc.add_transport_from_qr(account_id, f"DCACCOUNT:https://{relay}/new")
        except JsonRpcError as err:
            self.rpc.remove_account(account_id)
            raise ConfigurationFailed(str(err)) from err
        return account_id

    def first_configured_account(self) -> int | None:
        """Return the first configured account, if any."""
        for accid in self.rpc.get_all_account_ids():
            if self.rpc.is_configured(accid):
                return accid
        return None

    def is_configured(self, account_id: int) -> bool:
        """Return whether the account exists and is configured."""
        if account_id not in self.rpc.get_all_account_ids():
            return False
        return self.rpc.is_configured(account_id)

    def start_account(self, account_id: int) -> None:
        """Connect the account so it receives and sends messages."""
        self.rpc.start_io(account_id)

    def get_invite(self, account_id: int) -> str:
        """Return the bot's invite link."""
        return self.rpc.get_chat_securejoin_qr_code(account_id, None)

    def get_address(self, account_id: int) -> str:
        """Return the bot's address."""
        return self._get_addresses(account_id)[0]

    def _get_addresses(self, account_id: int) -> list[str]:
        return [params["addr"] for params in self.rpc.list_transports(account_id)]

    def get_contacts(self, account_id: int) -> list[Contact]:
        """Return the bot's contacts, such as people who joined with its invite."""
        return [_to_contact(c) for c in self.rpc.get_contacts(account_id, 0, "")]

    def send_message(
        self, account_id: int, target: str, text: str, timeout: float
    ) -> None:
        """Send a message and wait up to timeout seconds for it to be delivered."""
        contacts = [
            contact
            for contact in self.rpc.get_contacts(account_id, 0, target)
            if contact.address.lower() == target.lower()
        ]
        if not contacts:
            raise ContactNotFound(
                f"{target} is not a contact of the bot; "
                "scan the bot's invite link from Delta Chat first"
            )
        # Prefer a contact that was verified by scanning the invite.
        contact = max(contacts, key=lambda contact: contact.is_verified)
        chat_id = self.rpc.create_chat_by_contact_id(account_id, contact.id)
        msg_id = self.rpc.send_msg(account_id, chat_id, MsgData(text=text))

        with self._results_cond:
            delivered = self._results_cond.wait_for(
                lambda: msg_id in self._results, timeout
            )
            result = self._results.pop(msg_id, None)
        if not delivered:
            _LOGGER.warning(
                "Message to %s not delivered within %s seconds, "
                "it stays queued and will be retried",
                target,
                timeout,
            )
            return
        if result == EVENT_MSG_FAILED:
            error = self.rpc.get_message(account_id, msg_id).error
            raise SendFailed(f"Sending to {target} failed: {error or 'unknown error'}")


@dataclass(frozen=True)
class Contact:
    """A Delta Chat contact."""

    address: str
    name: str


def _to_contact(contact: Any) -> Contact:
    return Contact(contact.address, contact.display_name)


class ContactNotFound(HomeAssistantError):
    """The target is not a contact of the bot."""


class SendFailed(HomeAssistantError):
    """The message could not be delivered."""


class ConfigurationFailed(HomeAssistantError):
    """The configuration failed."""
