# Delta Chat for Home Assistant

A [HACS](https://hacs.xyz) custom integration that sends Home Assistant notifications over [Delta Chat](https://delta.chat).

> **Status:** early and experimental.

## Inspired by

This integration is inspired by the Delta Chat integration that [@MichaelBitard](https://github.com/MichaelBitard) started for Home Assistant core, on the [`add-delta-chat` branch](https://github.com/MichaelBitard/core/tree/add-delta-chat) of their fork. It started as a port of that code and has since been mostly rewritten. The main change is that the bot now runs continuously in the background instead of only while it sends a message.

## How it works

During setup, the integration creates a Delta Chat bot account on a chatmail relay (default `nine.testrun.org`). While Home Assistant runs, the bot stays connected, so it can handle invites and report whether each message was delivered.

Each recipient you add becomes a `notify` entity, such as `notify.delta_chat_alice`. Calling `notify.send_message` on that entity sends an end-to-end encrypted message from the bot to that recipient. If you set a title, it's sent as the first line of the message.

Recipients must be **contacts of the bot** before they can receive messages. Open the bot's invite link (`https://i.delta.chat/...`) in Delta Chat, or scan its QR code. The link is shown during setup and when you reconfigure the integration. If you open it on a computer, the page shows a QR code that you can scan with your phone. If a recipient isn't a contact yet, the action fails with an error saying so.

The bot's account data is stored in `<config>/delta_chat/`. It's deleted when you remove the integration.

## Installation

### HACS

1. In HACS, open the menu, choose **Custom repositories**, and add this repository with the category **Integration**.
2. Install **Delta Chat** and restart Home Assistant.

### Manual

Copy `custom_components/delta_chat` into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & services → Add integration** and pick **Delta Chat**.
2. Enter the relay. Keep the default unless you run your own.
3. Open the invite link that's shown, from each recipient's Delta Chat app.
4. Add one or more recipient addresses. Tick **Add another recipient** to add more.

To add or remove recipients later, use **Reconfigure** on the integration entry.

## Example

```yaml
action: notify.send_message
target:
  entity_id: notify.delta_chat_alice
data:
  title: Front door
  message: "The front door was opened"
```

## Known limitations

- Only one Delta Chat bot can be set up per Home Assistant instance.
- If delivery isn't confirmed within 60 seconds, the action returns without an error. The message stays queued and the bot keeps retrying.
- The bot only sends messages. Replies to it are ignored.

## Development

```sh
uv venv -p 3.13 .venv
uv pip install -p .venv/bin/python -r requirements_test.txt
.venv/bin/pytest
```

## License

The code that inspired this integration was written for Home Assistant core, which is licensed under Apache-2.0.
