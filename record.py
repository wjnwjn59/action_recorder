import argparse
import time
import os
import cv2
import json
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import numpy as np
import pyautogui
import pygetwindow as gw
import win32gui
import win32con
from pynput import mouse, keyboard

from postprocess_annotations import post_process_actions, merge_typewrite_actions, delete_unused_images
from postprocess_annotations import replace_all_before_frames

import logging
import string
import shutil

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

is_running = True
mouse_listener = None
keyboard_listener = None
actions = []

resolution = (1920, 1080)
codec = cv2.VideoWriter_fourcc(*"mp4v")
recording_filename = "screen_recording.mp4"
fps = 30.0

session_id = None

base_dir = None
images_dir = None
annotations_file_path = None
recording_path = None

is_mouse_pressed = False
drag_start_position = (0, 0)
caps_lock_on = False

start_time = time.time()

executor = ThreadPoolExecutor(max_workers=4)

# Global variable that holds the latest captured screenshot (as a relative path)
last_frame = None

def setup_directories():
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

def create_recording_writer():
    return cv2.VideoWriter(recording_path, codec, fps, resolution)

def take_screenshot(label):
    unique_id = uuid.uuid4().hex
    filename = f"{session_id}_{label}_{unique_id}.png"
    filepath = os.path.join(images_dir, filename)
    try:
        img = pyautogui.screenshot()
        img.save(filepath)
    except Exception as e:
        logging.error(f"Error taking screenshot: {e}")
        raise
    return Path(filepath).relative_to("data").as_posix()

def attach_screenshot(record, after_label, action_msg):
    # Set delay based on action type.
    if record.get("action") in ("drag", "vscroll"):
        delay = 0.3
    elif record.get("action") == "press":
        if record.get("value") and record["value"][0].lower() != "enter":
            delay = 0.1
        else:
            delay = 1.0
    else:
        delay = 1.0

    global last_frame
    try:
        # Use the global last_frame as the before_frame.
        record["before_frame"] = last_frame
        time.sleep(delay)
        after_frame = take_screenshot(after_label)
        record["after_frame"] = after_frame
        # Update last_frame for the next action.
        last_frame = after_frame
        actions.append(record)
        logging.info(action_msg)
    except Exception as e:
        logging.error(f"Screenshot error: {e}")

def on_click(x, y, button, pressed):
    global is_mouse_pressed, drag_start_position
    if pressed:
        is_mouse_pressed = True
        drag_start_position = (x, y)
        record = {
            "action": "single_click",
            "button": str(button).split(".")[1],
            "x": x,
            "y": y,
            "n_scrolls": None,
            "value": [],
            "timestamp": time.time() - start_time,
            "before_frame": None,
            "after_frame": None
        }
        attach_screenshot(record, "after", f"Single Click at ({x}, {y}) with {button}")
    else:
        if is_mouse_pressed:
            if ((drag_start_position[0] - x)**2 + (drag_start_position[1] - y)**2)**0.5 > 5:
                record = {
                    "action": "drag",
                    "button": str(button).split(".")[1],
                    "x_start": drag_start_position[0],
                    "y_start": drag_start_position[1],
                    "x_end": x,
                    "y_end": y,
                    "timestamp": time.time() - start_time,
                    "before_frame": None,
                    "after_frame": None
                }
                attach_screenshot(record, "after", f"Drag from {drag_start_position} to ({x}, {y})")
            else:
                logging.info(f"Released at ({x}, {y}) with minimal movement")
            is_mouse_pressed = False

def on_scroll(x, y, dx, dy):
    record = {
        "action": "vscroll",
        "x": x,
        "y": y,
        "dx": dx,
        "dy": dy,
        "count": 1,
        "timestamp": time.time() - start_time,
        "before_frame": None,
        "after_frame": None
    }
    attach_screenshot(record, "after", f"Scroll at ({x},{y}) dx={dx}, dy={dy}")

def on_move(x, y):
    pass

def on_press_key(key):
    global is_running, mouse_listener, keyboard_listener, caps_lock_on
    if key == keyboard.Key.caps_lock:
        caps_lock_on = not caps_lock_on
        return
    special_keys = {
        keyboard.Key.backspace: "backspace",
        keyboard.Key.enter: "enter",
        keyboard.Key.tab: "tab",
        keyboard.Key.esc: "esc",
    }
    try:
        if key == keyboard.Key.esc:
            logging.info("Esc key pressed. Stopping the program...")
            is_running = False
            if mouse_listener is not None:
                mouse_listener.stop()
            if keyboard_listener is not None:
                keyboard_listener.stop()
            return False
        else:
            if isinstance(key, keyboard.KeyCode):
                if key.char is not None:
                    key_str = key.char.upper() if caps_lock_on else key.char
                else:
                    key_str = str(key)
            elif isinstance(key, keyboard.Key):
                key_str = special_keys.get(key, key.name)
            else:
                key_str = str(key)
            if key_str.startswith("Key."):
                key_str = key_str[4:]
            if key_str in ("ctrl_l", "ctrl_r"):
                key_str = "ctrl"
            if key_str in ("alt_l", "alt_r"):
                key_str = "alt"
            record = {
                "action": "press",
                "button": None,
                "x": None,
                "y": None,
                "n_scrolls": None,
                "value": [key_str],
                "timestamp": time.time() - start_time,
                "before_frame": None,
                "after_frame": None
            }
            attach_screenshot(record, "after", f"Key Press: {key_str}")
    except AttributeError:
        pass

def start_listeners():
    global mouse_listener, keyboard_listener
    mouse_listener = mouse.Listener(
        on_click=on_click,
        on_scroll=on_scroll,
        on_move=on_move
    )
    keyboard_listener = keyboard.Listener(on_press=on_press_key)
    mouse_listener.start()
    keyboard_listener.start()

def record_screen(out):
    while is_running:
        frame_start = time.time()
        try:
            img = pyautogui.screenshot()
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            out.write(frame)
        except Exception as e:
            logging.error(f"Screen recording error: {e}")
        frame_duration = time.time() - frame_start
        sleep_time = max(0, (1.0 / fps) - frame_duration)
        time.sleep(sleep_time)
    out.release()
    cv2.destroyAllWindows()

def minimize_current_window():
    active_window = gw.getActiveWindow()
    if active_window is not None:
        hwnd = active_window._hWnd
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        logging.info(f"Minimized: {active_window.title}")
    else:
        logging.info("No active window found.")

def distance(a, b):
    return ((a[0] - b[0])**2 + (a[1] - b[1])**2)**0.5

def main():
    global session_id, base_dir, images_dir, annotations_file_path, recording_path, last_frame
    parser = argparse.ArgumentParser(description="Mouse and Keyboard Recording Program")
    parser.add_argument("--id", type=str, help="ID for folder naming and screenshot labeling", required=True)
    args = parser.parse_args()
    session_id = args.id
    base_dir = os.path.join("data", session_id)
    images_dir = os.path.join(base_dir, "images")
    annotations_file_path = os.path.join(base_dir, "annotations.json")
    recording_path = os.path.join(base_dir, recording_filename)
    if os.path.exists(base_dir):
        logging.error(f"Directory {base_dir} already exists. Please choose a different ID.")
        sys.exit(1)
    setup_directories()
    minimize_current_window()
    # Capture an initial screenshot to be used as the before_frame for the first action.
    time.sleep(1)
    last_frame = take_screenshot("before")
    time.sleep(1)
    start_listeners()
    out = create_recording_writer()
    screen_recording_thread = ThreadPoolExecutor(max_workers=1).submit(record_screen, out)
    mouse_listener.join()
    keyboard_listener.join()
    executor.shutdown(wait=True)
    screen_recording_thread.result()
    post_processed_actions = post_process_actions(actions)
    post_processed_actions = merge_typewrite_actions(post_processed_actions)
    # Replace the before_frame of each typewrite action (except the first) with a copy
    # of the previous action's after_frame (with a new UUID).
    post_processed_actions = replace_all_before_frames(post_processed_actions)
    with open(annotations_file_path, 'w', encoding='utf-8') as f:
        json.dump(post_processed_actions, f, indent=4)
    delete_unused_images(post_processed_actions, images_dir)
    logging.info(f"Annotations saved at: {annotations_file_path}")

if __name__ == '__main__':
    main()
