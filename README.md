# WoW Horde Character Generator Macro (macOS port)

Keeps clicking **Finish** on the WoW character-creation screen. When the
"population imbalance" popup appears it clicks **Okay**, then goes back to Finish.
If neither button is visible for longer than `GRACE_SECONDS` (1.5 s), it pauses
for `PAUSE_SECONDS` (10 s) and then checks again. If both are still missing after
that pause, it assumes the character was created, sends a Telegram message and stops.

If the game drops to the login screen ("You have been disconnected from the
server", detected by the red Menu / Create Account buttons bottom right), it
sends a "disconnected, action needed" Telegram message and stops without clicking.

This is a macOS port of the original Windows script: detection and Telegram are
unchanged, window lookup / capture / clicks / hotkeys use Quartz (pyobjc).

## Run

Double-click **`WoW Macro.command`**. On the first run it creates `.venv/` and
installs the dependencies, then starts the macro in Terminal. You have 3 seconds
to switch to WoW (Cmd+Tab). Tip: drag the file to the Dock for one-click start.

Hotkeys: **fn+F7** Telegram test, **fn+F8** pause/resume, **fn+F10** quit
(Ctrl+C in Terminal also works). Mac F-keys are media keys by default, hence
`fn`. While it runs the macro owns the mouse cursor, so use fn+F8 to get it back.
Clicks only happen while WoW is the frontmost window.

## Permissions (first run)

macOS asks for two permissions for **Terminal**:

1. System Settings > Privacy & Security > **Screen & System Audio Recording** > Terminal on
2. System Settings > Privacy & Security > **Accessibility** > Terminal on

Quit Terminal (Cmd+Q) and double-click `WoW Macro.command` again. The macro
refuses to start until both are granted. If fn+F-keys do nothing, also enable
Terminal under **Input Monitoring**.

## Telegram

Copy `.env.example` to `.env` next to the script and fill it in (never share or
commit `.env`; it is git-ignored):

```
<bot token>
<chat id>
```

Line 1 is the bot token and line 2 is the chat id (`KEY=value` lines also work).
**fn+F7** sends a test message. Without a valid `.env` the macro still runs and skips messages.

## Manual setup / run

```bash
/usr/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python wow_finish_macro.py
```

## Check detection

```bash
.venv/bin/python wow_finish_macro.py --debug
```

Saves `debug.png` of the game's content area with the detection boxes (green)
and click points (magenta), and prints the scores. Run it with WoW on the
character screen to confirm the boxes sit on the buttons.

```bash
.venv/bin/python test_detection.py
```

Runs detection on the reference screenshots in `samples/`.

## Known limits

- Positions are scaled from a 2000x1125 (16:9) reference by the game's height.
  A different in-game **UI Scale** or a 16:10 MacBook screen can move the
  buttons; check with `--debug`.
- Fullscreen is recommended. In windowed mode a 28 pt title bar is assumed
  (`TITLE_BAR_PT`); if the boxes are shifted vertically, adjust that constant.
- Tunables (timings, pause, focus guard) are constants at the top of the script.
