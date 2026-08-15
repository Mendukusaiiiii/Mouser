import tkinter as tk
from tkinter import ttk
import ctypes
import ctypes.wintypes
import math
import threading
import time
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

# Windows API
user32 = ctypes.windll.user32

# Global hotkeys
HOTKEY_IDS = {
    1: ord('Z'),
    2: ord('X'),
    3: ord('C'),
    4: ord('V'),
}
hotkey_thread = None
hotkey_thread_id = None

# Custom tray icon path
ICON_PATH = Path(__file__).with_name("tray_icon.png")

# Mouse position structure
class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long)
    ]

def get_mouse_position():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

# Global variables
running = False
movement_thread = None
clicking = False
click_thread = None

def auto_clicker():
    global clicking

    try:
        interval = float(click_interval_var.get())
        if interval <= 0:
            raise ValueError
    except ValueError:
        set_status("Status: Invalid Click Interval", fg="red")
        clicking = False
        return

    min_interval = 0.001
    if interval < min_interval:
        interval = min_interval
        set_status(f"Status: Interval too low, using {min_interval:.3f}s", fg="orange")

    next_click = time.perf_counter()
    while clicking:
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

        next_click += interval
        sleep_time = next_click - time.perf_counter()
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            next_click = time.perf_counter()


def start_clicker(event=None):
    global clicking, click_thread

    if clicking:
        return

    clicking = True
    click_thread = threading.Thread(target=auto_clicker, daemon=True)
    click_thread.start()
    set_status("Status: Autoclicker Running", fg="green")


def stop_clicker(event=None):
    global clicking

    clicking = False
    set_status("Status: Autoclicker Stopped", fg="gray")


def infinity_motion():
    global running

    # Use current cursor position as the center
    center_x, center_y = get_mouse_position()

    try:
        width = int(width_var.get())
        height = int(height_var.get())
        speed = float(speed_var.get())
    except ValueError:
        set_status("Status: Invalid Input", fg="red")
        running = False
        return

    t = 0.0

    while running:
        # Infinity (∞) path
        x = int(center_x + width * math.sin(t))
        y = int(center_y + height * math.sin(2 * t))

        user32.SetCursorPos(x, y)

        t += speed
        time.sleep(0.005)

def start_motion(event=None):
    global running, movement_thread

    if running:
        return

    running = True

    movement_thread = threading.Thread(
        target=infinity_motion,
        daemon=True
    )
    movement_thread.start()

    if autoclick_var.get() and not clicking:
        start_clicker()

    set_status("Status: Running", fg="green")

def stop_motion(event=None):
    global running

    running = False
    if clicking:
        stop_clicker()
    set_status("Status: Stopped", fg="gray")


def unregister_hotkeys():
    for hotkey_id in HOTKEY_IDS:
        try:
            user32.UnregisterHotKey(None, hotkey_id)
        except Exception:
            pass


def hotkey_listener():
    global hotkey_thread_id
    hotkey_thread_id = user32.GetCurrentThreadId()

    # Ensure the thread has a Windows message queue before registering hotkeys.
    # The message queue is created when the thread calls a user/GDI function
    # such as PeekMessage or GetMessage. Calling PeekMessage with PM_NOREMOVE
    # forces the queue to be created so RegisterHotKey will succeed.
    try:
        msg = ctypes.wintypes.MSG()
        PM_NOREMOVE = 0x0000
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
    except Exception:
        pass

    for hotkey_id, vk in HOTKEY_IDS.items():
        if not user32.RegisterHotKey(None, hotkey_id, 0, vk):
            print(f"Warning: could not register hotkey id {hotkey_id}")

    msg = ctypes.wintypes.MSG()
    while True:
        ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret == 0 or ret == -1:
            break
        if msg.message == 0x0312:  # WM_HOTKEY
            if msg.wParam == 1:
                root.after(0, start_motion)
            elif msg.wParam == 2:
                root.after(0, stop_motion)
            elif msg.wParam == 3:
                root.after(0, start_clicker)
            elif msg.wParam == 4:
                root.after(0, stop_clicker)
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    unregister_hotkeys()


def register_hotkeys():
    global hotkey_thread
    hotkey_thread = threading.Thread(target=hotkey_listener, daemon=True)
    hotkey_thread.start()

# GUI
root = tk.Tk()
root.title("Mouser")
root.geometry("650x420")
root.resizable(False, False)


def set_window_icon():
    if ICON_PATH.exists():
        try:
            icon_image = tk.PhotoImage(file=str(ICON_PATH))
            root.iconphoto(False, icon_image)
            root._icon_image = icon_image
        except Exception as e:
            print(f"Warning: could not set window icon from {ICON_PATH}: {e}")

set_window_icon()

title = ttk.Label(
    root,
    text="Mouser",
    font=("Arial", 14, "bold")
)
title.pack(pady=10)

main_frame = ttk.Frame(root)
main_frame.pack(padx=10, pady=10, fill="x")

left_frame = ttk.LabelFrame(main_frame, text="Autoclicker", padding=10)
left_frame.pack(side="left", padx=10, pady=5, fill="both", expand=True)

right_frame = ttk.LabelFrame(main_frame, text="Motion", padding=10)
right_frame.pack(side="right", padx=10, pady=5, fill="both", expand=True)


autoclick_var = tk.BooleanVar(value=False)

ctk = ttk.Checkbutton(
    left_frame,
    text="Autoclicker",
    variable=autoclick_var
)
ctk.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="w")

ttk.Label(left_frame, text="Interval (s, min 0.01):").grid(
    row=1, column=0, padx=5, pady=5, sticky="w"
)

click_interval_var = tk.StringVar(value="0.1")

ttk.Entry(
    left_frame,
    textvariable=click_interval_var,
    width=12
).grid(row=1, column=1, padx=5, pady=5)

ttk.Button(
    left_frame,
    text="Start Clicker (C)",
    command=start_clicker
).grid(row=2, column=0, padx=5, pady=10, sticky="ew")

ttk.Button(
    left_frame,
    text="Stop Clicker (V)",
    command=stop_clicker
).grid(row=2, column=1, padx=5, pady=10, sticky="ew")

# Motion
width_var = tk.StringVar(value="250")
height_var = tk.StringVar(value="125")
speed_var = tk.StringVar(value="0.02")

ttk.Label(right_frame, text="Width:").grid(
    row=0, column=0, padx=5, pady=5, sticky="w"
)

ttk.Entry(
    right_frame,
    textvariable=width_var,
    width=12
).grid(row=0, column=1, padx=5, pady=5)

# Height
ttk.Label(right_frame, text="Height:").grid(
    row=1, column=0, padx=5, pady=5, sticky="w"
)

ttk.Entry(
    right_frame,
    textvariable=height_var,
    width=12
).grid(row=1, column=1, padx=5, pady=5)

# Speed
ttk.Label(right_frame, text="Speed:").grid(
    row=2, column=0, padx=5, pady=5, sticky="w"
)

ttk.Entry(
    right_frame,
    textvariable=speed_var,
    width=12
).grid(row=2, column=1, padx=5, pady=5)

ttk.Button(
    right_frame,
    text="Start Motion (Z)",
    command=start_motion
).grid(row=3, column=0, padx=5, pady=10, sticky="ew")

ttk.Button(
    right_frame,
    text="Stop Motion (X)",
    command=stop_motion
).grid(row=3, column=1, padx=5, pady=10, sticky="ew")

# Status
status_label = tk.Label(
    root,
    text="Status: Stopped",
    font=("Arial", 10),
    fg="gray"
)
status_label.pack(pady=10)

def set_status(text, fg="black"):
    status_label.config(text=text, fg=fg)

# Instructions
instructions = ttk.Label(
    root,
    text=(
        "© 2026 Mendukusai. All Rights Reserved.\n"
        "Close the window to hide to tray. Use the tray icon to restore, start/stop, or exit the app."
    ),
    justify="center"
)
instructions.pack()

# Keyboard shortcuts (use bind_all so keys work even if a child widget has focus)
for key, callback in (
    ("z", start_motion),
    ("x", stop_motion),
    ("c", start_clicker),
    ("v", stop_clicker),
):
    root.bind_all(f"<KeyPress-{key}>", callback)
    root.bind_all(f"<KeyPress-{key.upper()}>", callback)

# Ensure window receives keyboard input
root.focus_force()
register_hotkeys()

# Tray icon helpers

def create_tray_image():
    if ICON_PATH.exists():
        try:
            image = Image.open(ICON_PATH)
            image = image.convert("RGBA")
            image = image.resize((64, 64), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS)
            return image
        except Exception as e:
            print(f"Warning: could not load tray icon {ICON_PATH}: {e}")

    image = Image.new("RGB", (64, 64), color=(0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([16, 16, 28, 48], fill="white")
    draw.rectangle([36, 16, 48, 48], fill="white")
    return image


def show_window(icon=None, item=None):
    root.after(0, root.deiconify)
    root.after(0, root.lift)
    root.after(0, root.focus_force)


def hide_window(icon=None, item=None):
    root.after(0, root.withdraw)
    set_status("Status: Running in tray", fg="orange")


def quit_app(icon=None, item=None):
    global running, clicking
    running = False
    clicking = False
    try:
        icon.stop()
    except Exception:
        pass
    try:
        if hotkey_thread_id is not None:
            user32.PostThreadMessageW(hotkey_thread_id, 0x0012, 0, 0)
    except Exception:
        pass
    unregister_hotkeys()
    root.after(0, root.destroy)


def setup_tray():
    menu = pystray.Menu(
        pystray.MenuItem("Show", show_window),
        pystray.MenuItem("Start motion", start_motion),
        pystray.MenuItem("Stop motion", stop_motion),
        pystray.MenuItem("Start clicker", start_clicker),
        pystray.MenuItem("Stop clicker", stop_clicker),
        pystray.MenuItem("Exit", quit_app)
    )
    icon = pystray.Icon("Mouser", create_tray_image(), "Mouser", menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon

tray_icon = setup_tray()

root.protocol("WM_DELETE_WINDOW", hide_window)

root.mainloop()