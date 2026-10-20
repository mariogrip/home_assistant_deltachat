# Delta Chat for Home Assistant

A [HACS](https://hacs.xyz) custom integration that sends Home Assistant notifications over [Delta Chat](https://delta.chat).

> **Status:** early and experimental.

## Inspired by

This integration is inspired by the Delta Chat integration that [@MichaelBitard](https://github.com/MichaelBitard) started for Home Assistant core, on the [`add-delta-chat` branch](https://github.com/MichaelBitard/core/tree/add-delta-chat) of their fork. It started as a port of that code and has since been mostly rewritten. The main change is that the bot now runs continuously in the background instead of only while it sends a message.

## How it works

During setup, the integration creates a Delta Chat bot account on a chatmail relay (default `nine.testrun.org`). While Home Assistant runs, the bot stays connected, so it can handle invites and report whether each message was delivered.

Recipients are people who joined the bot by scanning its invite QR code in Delta Chat. You pick them by name, so you don't need to know their Delta Chat address. Each recipient becomes a `notify` entity, such as `notify.delta_chat_alice`. Calling `notify.send_message` on that entity sends an end-to-end encrypted message from the bot to that recipient. If you set a title, it's sent as the first line of the message.

When someone joins, Home Assistant shows a notification. People who join are never added as recipients automatically, so a leaked invite can't be used to read your notifications.

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
3. Scan the QR code that's shown in Delta Chat on each phone that should get notifications.
4. On the Delta Chat integration page, choose **Add recipient** and pick a person from the list. The QR code is shown there too, so you can invite more people later.

To remove a recipient, delete it from the integration page.

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
- Requires Home Assistant 2025.3 or newer.
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
