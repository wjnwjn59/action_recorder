from pynput import mouse, keyboard
import time
import os
import cv2
import numpy as np
import pyautogui
import pygetwindow as gw
import win32gui
import win32con
import json
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from postprocess_annotations import post_process_actions, merge_typewrite_actions, delete_unused_images

is_running = True
mouse_listener = None
keyboard_listener = None

# A list that will hold all the action dictionaries
actions = []

# Screen recording configs
resolution = (1920, 1080)
codec = cv2.VideoWriter_fourcc(*"mp4v")
recording_filename = "screen_recording.mp4"
fps = 30.0

# The directories for storing our data
timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
base_dir = os.path.join("data", timestamp)
recording_dir = os.path.join(base_dir, "recording")
images_dir = os.path.join(base_dir, "images")
annotations_dir = os.path.join(base_dir, "annotations")

# Paths to the annotation and recording files
annotations_file_path = os.path.join(annotations_dir, "annotations.json")
recording_path = os.path.join(recording_dir, recording_filename)

# For drag detection
is_mouse_pressed = False
drag_start_position = (0, 0)

# Start time
start_time = time.time()

# Initialize ThreadPoolExecutor for asynchronous screenshot capturing
executor = ThreadPoolExecutor(max_workers=4)

def setup_directories():
    os.makedirs(recording_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(annotations_dir, exist_ok=True)

def create_recording_writer():
    out = cv2.VideoWriter(recording_path, codec, fps, resolution)
    return out

def take_screenshot(label):
    unique_id = uuid.uuid4().hex
    filename = f"{label}_{unique_id}.png"
    filepath = os.path.join(images_dir, filename)
    
    # Capture screenshot and save
    img = pyautogui.screenshot()
    img.save(filepath)
    
    return filepath

def distance(a, b):
    return ((a[0] - b[0])**2 + (a[1] - b[1])**2)**0.5

def async_take_screenshot(label):
    return executor.submit(take_screenshot, label)

### Mouse Events

def on_click(x, y, button, pressed):
    global is_mouse_pressed, drag_start_position, actions

    if pressed:
        is_mouse_pressed = True
        drag_start_position = (x, y)
        before_future = async_take_screenshot("before_action")
        
        # Record a single click (on press)
        action_record = {
            "action": "single_click",
            "button": str(button).split(".")[1],
            "x": x,
            "y": y,
            "n_scrolls": None,
            "timestamp": time.time() - start_time,
            "before_frame": None,  # To be filled after screenshot
            "after_frame": None
        }

        # Once 'before' screenshot is done, capture 'after' screenshot
        def capture_after_before(before_future, record):
            try:
                before_path = before_future.result()
                record["before_frame"] = before_path

                # Asynchronously capture 'after' screenshot
                after_future = async_take_screenshot("after_action")
                after_path = after_future.result()
                record["after_frame"] = after_path

                actions.append(record)
                print(f"[ACTION] Single Click at ({x}, {y}) with {button}")
            except Exception as e:
                print(f"Screenshot error: {e}")

        # Attach callback to 'before' screenshot future
        before_future.add_done_callback(lambda fut: capture_after_before(fut, action_record))

    else:
        if is_mouse_pressed:
            end_position = (x, y)
            dist_dragged = distance(drag_start_position, end_position)

            if dist_dragged > 10:
                before_future = async_take_screenshot("before_action")

                # Prepare drag action record
                action_record = {
                    "action": "drag",
                    "button": str(button).split(".")[1],
                    "x_start": drag_start_position[0],
                    "y_start": drag_start_position[1],
                    "x_end": x,
                    "y_end": y,
                    "timestamp": time.time() - start_time,
                    "before_frame": None,  # To be filled after screenshot
                    "after_frame": None
                }

                def capture_after_drag(before_future, record):
                    try:
                        before_path = before_future.result()
                        record["before_frame"] = before_path

                        # Asynchronously capture 'after' screenshot
                        after_future = async_take_screenshot("after_action")
                        after_path = after_future.result()
                        record["after_frame"] = after_path

                        actions.append(record)
                        print(f"[ACTION] Drag from {record['x_start']}, {record['y_start']} to {record['x_end']}, {record['y_end']}")
                    except Exception as e:
                        print(f"Screenshot error: {e}")

                # Attach callback to 'before' screenshot future
                before_future.add_done_callback(lambda fut: capture_after_drag(fut, action_record))
            else:
                print(f"[INFO] Released at ({x}, {y}) with minimal movement")

            # Reset the pressed flag
            is_mouse_pressed = False

def on_scroll(x, y, dx, dy):
    global actions

    # Asynchronously capture 'before' screenshot
    before_future = async_take_screenshot("before_action")

    # Prepare scroll action record
    action_record = {
        "action": "vscroll",
        "x": x,
        "y": y,
        "dx": dx,
        "dy": dy,
        "count": 1,
        "timestamp": time.time() - start_time,
        "before_frame": None,  # To be filled after screenshot
        "after_frame": None
    }

    def capture_after_scroll(before_future, record):
        try:
            before_path = before_future.result()
            record["before_frame"] = before_path

            # Asynchronously capture 'after' screenshot
            after_future = async_take_screenshot("after_action")
            after_path = after_future.result()
            record["after_frame"] = after_path

            actions.append(record)
            print(f"[ACTION] Scroll at ({x},{y}) dx={dx}, dy={dy}")
        except Exception as e:
            print(f"Screenshot error: {e}")

    # Attach callback to 'before' screenshot future
    before_future.add_done_callback(lambda fut: capture_after_scroll(fut, action_record))

def on_move(x, y):
    pass

### Keyboard Events

def on_press_key(key):
    global is_running, mouse_listener, keyboard_listener, actions

    # Mapping for control characters (you can extend this as needed)
    control_char_map = {
        "\u0001": "A",
        "\u0003": "C",
        "\u0004": "D",
        "\u0008": "Backspace",
        "\u0013": "S",
        "\u0018": "X",
        "\u0016": "V",
        "\u001a": "Z",
        "\u001b": "Esc",
        "\u0009": "Tab",
        "\u000d": "Enter"
    }

    try:
        if key == keyboard.Key.esc:
            # If user presses ESC, stop everything
            print("Esc key pressed. Stopping the program...")
            is_running = False

            if mouse_listener is not None:
                mouse_listener.stop()
            if keyboard_listener is not None:
                keyboard_listener.stop()

            return False  # stops the keyboard listener immediately
        else:
            # Normalize the key representation
            if isinstance(key, keyboard.Key):
                key_str = str(key) # Convert special keys like Key.ctrl_l to 'ctrl_l'
            elif isinstance(key, keyboard.KeyCode):
                if key.char is not None:
                    # Decode control characters or printable characters
                    key_str = control_char_map.get(key.char, key.char)
                else:
                    key_str = str(key)
            else:
                key_str = str(key)

            # Asynchronously capture 'before' screenshot
            before_future = async_take_screenshot("before_key")

            # Prepare key press action record
            action_record = {
                "action": "press",
                "button": None,
                "x": None,
                "y": None,
                "n_scrolls": None,
                "value": [key_str],  # Use normalized key string
                "timestamp": time.time() - start_time,
                "before_frame": None,  # To be filled after screenshot
                "after_frame": None
            }

            def capture_after_key(before_future, record):
                try:
                    before_path = before_future.result()
                    record["before_frame"] = before_path

                    # Asynchronously capture 'after' screenshot
                    after_future = async_take_screenshot("after_key")
                    after_path = after_future.result()
                    record["after_frame"] = after_path

                    actions.append(record)
                    print(f"[ACTION] Key Press: {key_str}")
                except Exception as e:
                    print(f"Screenshot error: {e}")

            # Attach callback to 'before' screenshot future
            before_future.add_done_callback(lambda fut: capture_after_key(fut, action_record))

    except AttributeError:
        pass

def start_listeners():
    """
    Create and start both mouse and keyboard listeners.
    """
    global mouse_listener, keyboard_listener
    mouse_listener = mouse.Listener(
        on_click=on_click,
        on_scroll=on_scroll,
        on_move=on_move
    )
    keyboard_listener = keyboard.Listener(on_press=on_press_key)

    mouse_listener.start()
    keyboard_listener.start()

# Screen recording function

def record_screen(out):
    while is_running:
        img = pyautogui.screenshot()
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        out.write(frame)

    out.release()
    cv2.destroyAllWindows()

def minimize_current_window():
    # Get the current active window
    active_window = gw.getActiveWindow()
    if active_window is not None:
        hwnd = active_window._hWnd  # Get the handle of the window
        # Minimize the window
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        print(f"Minimized: {active_window.title}")
    else:
        print("No active window found.")

# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    setup_directories()

    # Optionally minimize all windows (Windows OS)
    # pyautogui.hotkey('win', 'd')
    minimize_current_window()

    time.sleep(1)

    start_listeners()

    out = create_recording_writer()

    # Start screen recording in a separate thread to avoid blocking
    screen_recording_thread = ThreadPoolExecutor(max_workers=4).submit(record_screen, out)

    # Wait for listeners to finish
    mouse_listener.join()
    keyboard_listener.join()

    # Shutdown the ThreadPoolExecutor for screenshots
    executor.shutdown(wait=True)

    # Optionally, wait for screen recording to finish
    screen_recording_thread.result()

    # Finally, write the actions JSON
    post_processed_actions = post_process_actions(actions)
    post_processed_actions = merge_typewrite_actions(post_processed_actions)
    with open(annotations_file_path, 'w', encoding='utf-8') as f:
        json.dump(post_processed_actions, f, indent=4)
    delete_unused_images(actions, post_processed_actions)

    print(f"Annotations saved at: {annotations_file_path}")

if __name__ == '__main__':
    main()
