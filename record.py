from pynput import mouse, keyboard
import time
import json
import sys
import os
import cv2
import numpy as np
import pyautogui
import threading
from datetime import datetime

# Global storage for events
storage = []
current_text = ""  # Accumulate keypresses into a single text
record_all = False
recording = True  # Control video recording

# Initialize screenshot index
screenshot_index = 0

def validate_args(args):
    """Validate and parse command-line arguments."""
    if len(args) > 2:
        exit("Only takes one optional argument - record-all")
    
    record_all = len(args) == 2 and args[1] == "record-all"
    if len(args) == 2 and not record_all:
        exit("The second argument must be 'record-all' if provided.")
    
    return record_all

def create_folders():
    """Create a unique folder for this recording based on the current date and time."""
    # Generate folder name as yyyy-mm-dd-HH-MM-SS
    folder_name = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    folder_path = os.path.join('data', folder_name)
    
    # Create subfolders for recording, images, and annotations
    os.makedirs(os.path.join(folder_path, 'recording'), exist_ok=True)
    os.makedirs(os.path.join(folder_path, 'images'), exist_ok=True)
    os.makedirs(os.path.join(folder_path, 'annotations'), exist_ok=True)
    
    return folder_path

def minimize_all_windows():
    """Simulate pressing Windows + D to minimize all applications."""
    pyautogui.hotkey('win', 'd')
    time.sleep(1)  # Wait for the desktop to show

def take_screenshot(folder_path):
    """Take a screenshot and save it with a timestamp-based index filename."""
    global screenshot_index
    screenshot_index += 1  # Increment the screenshot index
    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    screenshot_filename = f"{timestamp}-{screenshot_index}.png"
    screenshot_path = os.path.join(folder_path, 'images', screenshot_filename)

    # Take screenshot and save it
    screenshot = pyautogui.screenshot()
    screenshot.save(screenshot_path)
    print(f"Screenshot saved as {screenshot_filename}")

    return screenshot_path  # Return the path of the screenshot

def start_video_recording(folder_path):
    """Record the screen into a video file."""
    global recording
    screen_size = pyautogui.size()  # Get screen size
    print(f"Recording video with screen size: {screen_size}")
    
    # Use 'mp4v' codec for .mp4 format, or use 'XVID' codec if 'mp4v' causes issues
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # Use 'XVID' if 'mp4v' doesn't work
    video_writer = cv2.VideoWriter(os.path.join(folder_path, 'recording', 'screen_recording.mp4'), fourcc, 20.0, screen_size)

    while recording:
        img = pyautogui.screenshot()  # Capture screen as an image
        frame = np.array(img)  # Convert to a NumPy array
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)  # Convert RGB to BGR for OpenCV compatibility

        # Check the frame size before writing to video
        if frame.shape[1] != screen_size[0] or frame.shape[0] != screen_size[1]:
            print(f"Frame size mismatch! Expected: {screen_size}, Got: {frame.shape[:2]}")
            continue
        
        video_writer.write(frame)  # Write the frame to the video

        time.sleep(0.05)  # Adjust frame rate for better performance
    
    video_writer.release()  # Release the video writer when done

def on_press(key, keyboard_listener, mouse_listener, folder_path):
    """Handle key press events."""
    global current_text
    try:
        if hasattr(key, 'char') and key.char:  # Check if key has a char attribute
            current_text += key.char
        elif key == keyboard.Key.space:
            current_text += " "  # Add space for the space key
        elif key == keyboard.Key.enter:
            # Log the accumulated text
            storage.append({'action': 'typed_text', 'text': current_text, '_time': time.time()})
            current_text = ""  # Reset the text buffer
            screenshot_path = take_screenshot(folder_path)  # Take a screenshot after pressing Enter
            storage[-1]['screenshot_path'] = screenshot_path  # Store the screenshot path
        elif key == keyboard.Key.esc:
            # Save the recording and stop both listeners
            save_to_json(folder_path)
            stop_recording()
            keyboard_listener.stop()
            mouse_listener.stop()
            return False
    except AttributeError:
        pass

def on_release(key):
    """Handle key release events.""" 
    pass

def on_move(x, y, folder_path):
    """Handle mouse move events."""
    if record_all:
        if len(storage) >= 1:
            if storage[-1]['action'] != "moved" or (time.time() - storage[-1]['_time'] > 0.02):
                json_object = {'action': 'moved', 'x': x, 'y': y, '_time': time.time()}
                storage.append(json_object)
        else:
            json_object = {'action': 'moved', 'x': x, 'y': y, '_time': time.time()}
            storage.append(json_object)
        screenshot_path = take_screenshot(folder_path)  # Take a screenshot after a mouse move event
        storage[-1]['screenshot_path'] = screenshot_path  # Store the screenshot path

# Global variable to track last click time and button
last_click_time = 0
last_button = None
double_click_threshold = 0.5  # Time threshold for double-click in seconds
double_click_detected = False

def on_click(x, y, button, pressed, folder_path):
    """Handle mouse click events."""
    global last_click_time, last_button  # Access the global variables for last click time and button
    global double_click_detected  # Track whether a double-click is detected
    
    current_time = time.time()  # Get the current time
    is_double_click = False

    # Check if the click is a double-click
    if pressed and (current_time - last_click_time) < double_click_threshold and button == last_button:
        is_double_click = True
        double_click_detected = True  # Set the flag for double-click
        print(f"Double-click detected: {button}")
    
    # Update the last click time and button to the current one
    last_click_time = current_time
    last_button = button

    # Log the click action and whether it's a double-click
    if is_double_click:
        # Log double-click action only
        json_object = {
            'action': 'double_click',
            'button': str(button),
            'x': x,
            'y': y,
            '_time': current_time
        }
        storage.append(json_object)
        
        # Take a screenshot after double-click
        screenshot_path = take_screenshot(folder_path)
        storage[-1]['screenshot_path'] = screenshot_path  # Store the screenshot path

        # Clear the last two clicks to avoid counting them
        if len(storage) > 2:
            storage[-2] = {'action': 'ignored', 'x': storage[-2]['x'], 'y': storage[-2]['y'], '_time': storage[-2]['_time']}
            storage[-3] = {'action': 'ignored', 'x': storage[-3]['x'], 'y': storage[-3]['y'], '_time': storage[-3]['_time']}

    elif pressed and not double_click_detected:
        # Log regular click action if no double-click was detected
        json_object = {
            'action': 'pressed',
            'button': str(button),
            'x': x,
            'y': y,
            '_time': current_time
        }
        storage.append(json_object)
        
        # Take a screenshot after regular click
        screenshot_path = take_screenshot(folder_path)
        storage[-1]['screenshot_path'] = screenshot_path  # Store the screenshot path

    # Reset double-click flag after logging the action
    double_click_detected = False
    
    # Check to stop recording if right-click held for more than 2 seconds
    if len(storage) > 1:
        if storage[-1]['action'] == 'released' and storage[-1]['button'] == 'Button.right' and \
           storage[-1]['_time'] - storage[-2]['_time'] > 2:
            save_to_json(folder_path)
            stop_recording()
            return False


def on_scroll(x, y, dx, dy, folder_path):
    """Handle mouse scroll events."""
    json_object = {'action': 'scroll', 'vertical_direction': int(dy), 'horizontal_direction': int(dx), 'x': x, 'y': y, '_time': time.time()}
    storage.append(json_object)
    screenshot_path = take_screenshot(folder_path)  # Take a screenshot after scrolling
    storage[-1]['screenshot_path'] = screenshot_path  # Store the screenshot path

def save_to_json(folder_path):
    """Save recorded data to a JSON file."""
    with open(os.path.join(folder_path, 'annotations', 'annotations.json'), 'w') as outfile:
        json.dump(storage, outfile, indent=4)
    print(f"Recording saved to '{os.path.join(folder_path, 'annotations', 'annotations.json')}'.")

def stop_recording():
    """Stop video recording."""
    global recording
    recording = False

def main():
    """Main function to run the recording."""
    global record_all
    record_all = validate_args(sys.argv)

    print("Instructions:")
    print("- Hold right-click for more than 2 seconds to end the mouse recording.")
    print("- Press Esc to end the keyboard recording.")
    print("- Take screenshots automatically.")

    folder_path = create_folders()
    minimize_all_windows()

    # Start video recording in a separate thread
    video_thread = threading.Thread(target=start_video_recording, args=(folder_path,))
    video_thread.start()

    # Start mouse and keyboard listeners
    with keyboard.Listener(on_press=lambda key: on_press(key, keyboard_listener, mouse_listener, folder_path),
                           on_release=on_release) as keyboard_listener, \
         mouse.Listener(on_move=lambda x, y: on_move(x, y, folder_path),
                        on_click=lambda x, y, button, pressed: on_click(x, y, button, pressed, folder_path),
                        on_scroll=lambda x, y, dx, dy: on_scroll(x, y, dx, dy, folder_path)) as mouse_listener:
        keyboard_listener.join()
        mouse_listener.join()

if __name__ == "__main__":
    main()
