# Mouser

A lightweight Windows utility that combines an **autoclicker** with an **automated mouse motion** tool.

## Features

- **Autoclicker** - well obviously.
- **Infinity motion** - moves the mouse cursor along a infinite path around its current position, with configurable width, height, and speed.
- **Combined mode** - optionally trigger the autoclicker automatically whenever motion starts.
- **System tray integration** - closing the main window sends the app to the tray instead of quitting.
- **Self-click protection** - the autoclicker checks the cursor position before each synthetic click and skips clicking if the cursor is currently over Mouser's own panel(s), so it can't accidentally spam its own buttons.
- **Motion self-stop** - if you manually grab and move the mouse while the motion is running, motion detects the interference and stops automatically instead of fighting you for control.

## Requirements

- Windows (uses the Win32 API via `ctypes`, so it will **not** run on macOS/Linux)
- Python 3.8+
- Dependencies:
  ```
  pip install pystray pillow
  ```
  (`tkinter` ships with standard Python on Windows.)

## Running

```
python Mouser.py
```


## Usage

1. Launch the app - the main window opens with two panels: **Autoclicker** and **Motion**.
2. **Autoclicker panel** - set the click interval (seconds, minimum ~0.001s) and press **Start**. Starting the clicker automatically opens the small mini-mode panel and hides the main window.
3. **Motion panel** - set width, height, and speed, then press **Start**. The cursor will trace a figure-eight centered on wherever it was when you started. Motion stops automatically if you manually move the mouse yourself.
4. Check **"Autoclicker"** in the left panel before starting motion to have clicking start automatically alongside it.
5. Closing the main window sends Mouser to the **system tray** rather than quitting, use the tray icon's **Show** to bring it back, or **Exit** to fully close the app.

## Disclaimer

This tool automates mouse input. Automated clicking/movement may violate the terms of service of some applications or games, use responsibly and at your own risk.

© Mendukusai. All Rights Reserved.
