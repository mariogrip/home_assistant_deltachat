"""Test the Delta Chat client."""

from threading import Event, Thread
from unittest.mock import MagicMock

import pytest
from deltachat2 import JsonRpcError
from deltachat2._utils import to_attrdict

from custom_components.delta_chat.bot import (
    ConfigurationFailed,
    Contact,
    ContactNotFound,
    DeltaChatClient,
    SendFailed,
)


def _event(kind: str, **fields) -> dict:
    return to_attrdict({"contextId": 1, "event": {"kind": kind, **fields}})


@pytest.fixture
def client(tmp_path) -> DeltaChatClient:
    """Return a client with a mocked RPC connection."""
    client = DeltaChatClient(str(tmp_path))
    client.rpc = MagicMock()
    client.rpc.get_contacts.return_value = to_attrdict(
        [{"id": 10, "address": "Alice@example.org", "isVerified": True}]
    )
    client.rpc.create_chat_by_contact_id.return_value = 20
    client.rpc.send_msg.return_value = 30
    return client


def _run_events(client: DeltaChatClient, *events: dict) -> None:
    """Feed events to the client's event loop until it runs out."""
    client.rpc.get_next_event.side_effect = [*events, JsonRpcError("closed")]
    client._closing = False
    client._event_loop()


def test_send_message_delivered(client: DeltaChatClient) -> None:
    """Test sending waits for the delivery event."""
    client.rpc.send_msg.side_effect = lambda *_: (
        _run_events(client, _event("MsgDelivered", chatId=20, msgId=30)) or 30
    )
    client.send_message(1, "alice@example.org", "hello", timeout=1)

    client.rpc.create_chat_by_contact_id.assert_called_once_with(1, 10)
    assert client.rpc.send_msg.call_args.args[2].text == "hello"


def test_send_message_failed(client: DeltaChatClient) -> None:
    """Test a failed delivery raises with the core's error."""
    client.rpc.send_msg.side_effect = lambda *_: (
        _run_events(client, _event("MsgFailed", chatId=20, msgId=30)) or 30
    )
    client.rpc.get_message.return_value = to_attrdict({"error": "quota exceeded"})

    with pytest.raises(SendFailed, match="quota exceeded"):
        client.send_message(1, "alice@example.org", "hello", timeout=1)


def test_send_message_waits_for_event_from_other_thread(
    client: DeltaChatClient,
) -> None:
    """Test a delivery event arriving later wakes up the sender."""
    sent = Event()
    client.rpc.send_msg.side_effect = lambda *_: sent.set() or 30

    def deliver() -> None:
        sent.wait()
        _run_events(client, _event("MsgDelivered", chatId=20, msgId=30))

    thread = Thread(target=deliver)
    thread.start()
    client.send_message(1, "alice@example.org", "hello", timeout=5)
    thread.join()


def test_send_message_timeout(client: DeltaChatClient) -> None:
    """Test a message that is not delivered in time does not raise."""
    client.send_message(1, "alice@example.org", "hello", timeout=0.01)


def test_send_message_unknown_contact(client: DeltaChatClient) -> None:
    """Test sending to an address that is not a contact."""
    with pytest.raises(ContactNotFound, match="bob@example.org"):
        client.send_message(1, "bob@example.org", "hello", timeout=1)
    client.rpc.send_msg.assert_not_called()


def test_event_loop_reports_death(client: DeltaChatClient) -> None:
    """Test the on_died callback runs when the core stops unexpectedly."""
    on_died = MagicMock()
    client._on_died = on_died
    _run_events(client)
    on_died.assert_called_once()


def test_setup_account_reuses_and_cleans_up(client: DeltaChatClient) -> None:
    """Test a configured account on the relay is reused and others removed."""
    client.rpc.get_all_account_ids.return_value = [1, 2, 3]
    client.rpc.is_configured.side_effect = lambda accid: accid != 1
    client.rpc.list_transports.side_effect = lambda accid: [
        {"addr": "a@other.relay" if accid == 2 else "b@nine.testrun.org"}
    ]

    assert client.setup_account("nine.testrun.org") == 3
    assert [c.args for c in client.rpc.remove_account.call_args_list] == [(1,), (2,)]
    client.rpc.add_account.assert_not_called()


def test_setup_account_creates(client: DeltaChatClient) -> None:
    """Test a new account is created and configured as a bot."""
    client.rpc.get_all_account_ids.return_value = []
    client.rpc.add_account.return_value = 5

    assert client.setup_account("nine.testrun.org") == 5
    client.rpc.set_config.assert_any_call(5, "bot", "1")
    client.rpc.add_transport_from_qr.assert_called_once_with(
        5, "DCACCOUNT:https://nine.testrun.org/new"
    )


def test_setup_account_failure_removes_account(client: DeltaChatClient) -> None:
    """Test a failed configuration does not leave an account behind."""
    client.rpc.get_all_account_ids.return_value = []
    client.rpc.add_account.return_value = 5
    client.rpc.add_transport_from_qr.side_effect = JsonRpcError("no network")

    with pytest.raises(ConfigurationFailed):
        client.setup_account("nine.testrun.org")
    client.rpc.remove_account.assert_called_once_with(5)


def test_real_core_start_and_close(tmp_path) -> None:
    """Test the real deltachat-rpc-server starts and shuts down cleanly."""
    client = DeltaChatClient(str(tmp_path / "data"))
    client.start()
    accid = client.rpc.add_account()
    assert not client.is_configured(accid)
    assert client.first_configured_account() is None
    client.close()

    assert not client._event_thread.is_alive()
    assert client._transport.process.wait(timeout=10) is not None


def test_real_core_crash(tmp_path) -> None:
    """Test a crashed core is reported and calls fail instead of hanging."""
    died = Event()
    client = DeltaChatClient(str(tmp_path / "data"), on_died=died.set)
    client.start()
    client._transport.process.kill()

    assert died.wait(timeout=10)
    with pytest.raises(JsonRpcError):
        client.rpc.get_all_account_ids()
    client.close()


def test_get_contacts(client: DeltaChatClient) -> None:
    """Test contacts are returned with their display name."""
    client.rpc.get_contacts.return_value = to_attrdict(
        [{"id": 10, "address": "alice@example.org", "displayName": "Alice"}]
    )
    assert client.get_contacts(1) == [Contact("alice@example.org", "Alice")]
    client.rpc.get_contacts.assert_called_once_with(1, 0, "")


def test_event_loop_reports_joined(client: DeltaChatClient) -> None:
    """Test on_joined is called with the contact that finished joining."""
    on_joined = MagicMock()
    client._on_joined = on_joined
    client.rpc.get_contact.return_value = to_attrdict(
        {"id": 10, "address": "carol@example.org", "displayName": "Carol"}
    )
    _run_events(
        client,
        _event("SecurejoinInviterProgress", contactId=10, progress=400),
        _event("SecurejoinInviterProgress", contactId=10, progress=1000),
    )
    on_joined.assert_called_once_with(Contact("carol@example.org", "Carol"))
    client.rpc.get_contact.assert_called_once_with(1, 10)
