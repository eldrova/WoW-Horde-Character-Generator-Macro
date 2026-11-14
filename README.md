# WoW Horde Character Generator Macro

Keeps clicking **Finish** on the WoW character-creation screen. When the
"population imbalance" popup appears it clicks **Okay**, then goes back to Finish.
If neither button is visible for longer than `GRACE_SECONDS` (1.5 s), it pauses
for `PAUSE_SECONDS` (10 s) and then checks again. If both are still missing after
that pause, it assumes the character was created, sends a Telegram message and stops.

If the game drops to the login screen ("You have been disconnected from the
server", detected by the red Menu / Create Account buttons bottom right), it
sends a "disconnected, action needed" Telegram message and stops without clicking.

## Telegram

Copy `.env.example` to `.env` next to the script and fill it in (never share or
commit `.env`; it is git-ignored):

```
<bot token>
<chat id>
```

Line 1 is the bot token and line 2 is the chat id (`KEY=value` lines also work).
**F7** sends a test message. Without a valid `.env` the macro still runs and skips messages.

## Setup

```bash
python -m pip install -r requirements.txt
```

## Run

```bash
python wow_finish_macro.py
```

Or double-click `run.bat`. You have 3 seconds to switch to WoW.
Hotkeys: **F7** Telegram test, **F8** pause/resume, **F10** quit
(Ctrl+C in the console also works). While it runs the macro owns the mouse
cursor, so use F8 to get it back. Clicks only happen while WoW is the active window.

## Check detection

```bash
python wow_finish_macro.py --debug
```

Saves `debug.png` of the game's client area with the detection boxes (green)
and click points (magenta), and prints the scores. Use it on the character
screen to confirm the boxes sit on the buttons.

```bash
python test_detection.py
```

Runs detection on the reference screenshots in `samples/`.

## Known limits

- Positions are scaled from a 2000x1125 reference by the game's height. A
  different in-game **UI Scale** moves the buttons; check with `--debug`.
- Exclusive fullscreen can produce black captures; use Windowed (Fullscreen).
- If WoW runs as administrator, the script must too, or Windows drops the clicks.
- Tunables (timings, pause, focus guard) are constants at the top of the script.
