import json
import os
import string
import shutil
import uuid
from pathlib import Path

HOTKEY_MODIFIER_PREFIXES = ["shift", "ctrl", "alt", "cmd"]
DISALLOWED_HOTKEY_KEYS = {"backspace", "enter", "return", "tab"}

def normalize_key(key_str, shift_active=False):
    special_mapping = {
        "\u0008": "backspace",
        "\u0009": "tab",
        "\u000d": "enter",
        "\u001b": "esc"
    }
    if key_str in special_mapping:
        return special_mapping[key_str]
    if len(key_str) == 1:
        code = ord(key_str)
        if 1 <= code <= 26:
            letter = chr(code + 96)
            return letter.upper() if shift_active else letter
    if key_str.startswith("Key."):
        return key_str[4:]
    return key_str

def is_modifier_key(key):
    return any(key.startswith(prefix) for prefix in HOTKEY_MODIFIER_PREFIXES)

def is_typable_character(key):
    if key == "space":
        return True
    if len(key) == 1 and (key.isalnum() or key in string.punctuation):
        return True
    return False

def are_same_coordinates(action1, action2, delta=5):
    return abs(action1['x'] - action2['x']) <= delta and abs(action1['y'] - action2['y']) <= delta

def time_difference(action1, action2):
    return action2['timestamp'] - action1['timestamp']

# Helper function to copy an image file to a new file with a new UUID.
def copy_image_file(rel_path):
    src = os.path.join("data", rel_path)
    p = Path(rel_path)
    session_id = p.stem.split("_")[0]
    new_uuid = uuid.uuid4().hex
    new_filename = f"{session_id}_before_action_{new_uuid}{p.suffix}"
    dst = p.parent / new_filename
    dst_full = os.path.join("data", str(dst))
    os.makedirs(os.path.join("data", str(p.parent)), exist_ok=True)
    shutil.copyfile(src, dst_full)
    return Path(dst).as_posix()

def post_process_actions(actions):
    processed_actions = []
    i = 0
    n = len(actions)
    
    while i < n:
        current_action = actions[i]
        
        # Rule 1: Hotkey merging (only for non-shift modifiers)
        if (current_action['action'] == 'press' and 
            is_modifier_key(current_action['value'][0]) and 
            current_action['value'][0].lower() not in {"shift", "shift_l", "shift_r"}):
            hotkey_keys = [current_action['value'][0]]
            hotkey_before_frame = current_action['before_frame']
            hotkey_after_frame = current_action['after_frame']
            shift_active = "shift" in hotkey_keys
            j = i + 1
            while j < n:
                next_action = actions[j]
                if (next_action['action'] == 'press' and
                    time_difference(current_action, next_action) <= 1.0 and
                    next_action['value'][0] not in DISALLOWED_HOTKEY_KEYS):
                    normalized = normalize_key(next_action['value'][0], shift_active)
                    hotkey_keys.append(normalized)
                    hotkey_after_frame = next_action['after_frame']
                    j += 1
                else:
                    break
            if len(hotkey_keys) == 1:
                processed_actions.append({
                    "action": "press",
                    "button": None,
                    "x": None,
                    "y": None,
                    "n_scrolls": None,
                    "value": hotkey_keys,
                    "before_frame": hotkey_before_frame,
                    "after_frame": hotkey_after_frame
                })
            else:
                processed_actions.append({
                    "action": "hotkey",
                    "button": None,
                    "x": None,
                    "y": None,
                    "n_scrolls": None,
                    "value": hotkey_keys,
                    "before_frame": hotkey_before_frame,
                    "after_frame": hotkey_after_frame
                })
            i = j
            continue

        # Rule 2: Merge two consecutive single clicks into a double click
        if current_action['action'] == 'single_click' and (i + 1 < n):
            next_action = actions[i+1]
            if (next_action['action'] == 'single_click' and
                are_same_coordinates(current_action, next_action) and
                time_difference(current_action, next_action) <= 2.0):
                processed_actions.append({
                    "action": "double_click",
                    "button": current_action['button'],
                    "x": current_action['x'],
                    "y": current_action['y'],
                    "n_scrolls": None,
                    "value": [],
                    "before_frame": current_action['before_frame'],
                    "after_frame": next_action['after_frame']
                })
                i += 2
                continue

        # Rule 3: Split drag into moveTo and dragTo actions.
        if current_action['action'] == 'single_click' and (i + 1 < n):
            next_action = actions[i+1]
            if next_action['action'] == 'drag' and are_same_coordinates(current_action, {'x': next_action['x_start'], 'y': next_action['y_start']}):
                move_action = {
                    "action": "moveTo",
                    "button": None,
                    "x": current_action['x'],
                    "y": current_action['y'],
                    "n_scrolls": None,
                    "value": [],
                    "before_frame": current_action['before_frame'],
                    "after_frame": current_action['after_frame']
                }
                processed_actions.append(move_action)
                new_drag_before = copy_image_file(move_action['after_frame'])
                drag_action = {
                    "action": "dragTo",
                    "button": next_action['button'],
                    "x": next_action['x_end'],
                    "y": next_action['y_end'],
                    "n_scrolls": None,
                    "value": [],
                    "before_frame": new_drag_before,
                    "after_frame": next_action['after_frame']
                }
                processed_actions.append(drag_action)
                i += 2
                continue

        # Rule 4: Merge consecutive vscroll events based on dy sign (ignore timestamps)
        if current_action['action'] == 'vscroll':
            merged_dy = current_action.get('dy', 0)
            scroll_before_frame = current_action['before_frame']
            scroll_after_frame = current_action['after_frame']
            j = i + 1
            while j < n:
                next_action = actions[j]
                if next_action['action'] == 'vscroll':
                    next_dy = next_action.get('dy', 0)
                    if merged_dy * next_dy > 0:
                        merged_dy += next_dy
                        scroll_after_frame = next_action['after_frame']
                        j += 1
                    else:
                        break
                else:
                    break
            processed_actions.append({
                "action": "vscroll",
                "button": None,
                "x": None,
                "y": None,
                "n_scrolls": merged_dy,
                "value": [],
                "before_frame": scroll_before_frame,
                "after_frame": scroll_after_frame,
            })
            i = j
            continue

        # Rule 5: Merge eligible press/typewrite events if they are typable characters.
        if current_action['action'] in {"press", "typewrite"} and is_typable_character(current_action['value'][0]):
            # Skip if the current event is a shift key.
            if current_action['value'][0].lower() in {"shift", "shift_l", "shift_r"}:
                i += 1
                continue
            base_press = current_action.copy()  # copy the first event (base)
            typed_string = base_press['value'][0]
            if typed_string == "space":
                typed_string = " "
            typed_before_frame = base_press['before_frame']
            # Instead of always comparing to the base_press, we now update a prev_event.
            prev_event = base_press
            last_after_frame = base_press['after_frame']
            j = i + 1
            merge_count = 0
            while j < n:
                next_action = actions[j]
                if next_action['action'] in {"press", "typewrite"} and time_difference(prev_event, next_action) <= 1.5:
                    key_val = next_action['value'][0]
                    if key_val.lower() in {"shift", "shift_l", "shift_r"}:
                        j += 1
                        continue
                    if is_typable_character(key_val):
                        # Append the character; if it's "space", append a space.
                        typed_string += key_val if key_val != "space" else " "
                        last_after_frame = next_action['after_frame']
                        merge_count += 1
                        prev_event = next_action
                        j += 1
                    else:
                        break
                else:
                    break
            if merge_count == 0:
                processed_actions.append(base_press)
            else:
                merged_event = {
                    "action": "typewrite" if len(typed_string) > 1 else "press",
                    "button": None,
                    "x": None,
                    "y": None,
                    "n_scrolls": None,
                    "value": [typed_string],
                    "before_frame": typed_before_frame,
                    "after_frame": last_after_frame
                }
                processed_actions.append(merged_event)
            i = j
            continue

        # Default: Remove timestamp and append the event.
        if current_action['action'] == 'press' and current_action['value'][0].lower() in {"shift", "shift_l", "shift_r"}:
            i += 1
            continue
        current_action.pop('timestamp', None)
        processed_actions.append(current_action)
        i += 1

    return processed_actions

def merge_typewrite_actions(actions):
    merged_actions = []
    i = 0
    n = len(actions)
    while i < n:
        current_action = actions[i]
        if current_action['action'] == 'typewrite':
            merged_value = current_action['value'][0]
            first_before = current_action['before_frame']
            last_after = current_action['after_frame']
            i += 1
            while i < n and actions[i]['action'] == 'typewrite':
                merged_value += actions[i]['value'][0]
                last_after = actions[i]['after_frame']
                i += 1
            merged_actions.append({
                "action": "typewrite",
                "button": None,
                "x": None,
                "y": None,
                "n_scrolls": None,
                "value": [merged_value],
                "before_frame": first_before,
                "after_frame": last_after
            })
        else:
            merged_actions.append(current_action)
            i += 1
    return merged_actions

def delete_unused_images(processed_actions, session_images_dir):
    used_image_paths = set()
    for action in processed_actions:
        if action.get('before_frame'):
            used_image_paths.add(action['before_frame'])
        if action.get('after_frame'):
            used_image_paths.add(action['after_frame'])
    # Walk through the session images folder and delete any PNG file not referenced.
    for root, dirs, files in os.walk(session_images_dir):
        for file in files:
            if file.lower().endswith(".png"):
                full_path = os.path.join(root, file)
                try:
                    rel_path = Path(full_path).relative_to("data").as_posix()
                except Exception:
                    continue
                if rel_path not in used_image_paths:
                    try:
                        os.remove(full_path)
                        print(f"Deleted unused image: {full_path}")
                    except Exception as e:
                        print(f"Failed to delete {full_path}: {e}")

def replace_typewrite_before_frames(processed_actions):
    for idx in range(1, len(processed_actions)):
        current_action = processed_actions[idx]
        if current_action.get("action") == "typewrite":
            prev_action = processed_actions[idx - 1]
            if prev_action.get("after_frame"):
                # Copy the previous action's after_frame to generate a new image file.
                new_before = copy_image_file(prev_action["after_frame"])
                current_action["before_frame"] = new_before
    return processed_actions


def main_post_processing():
    annotations_json_path = "data/2024-12-30-09-51-08/annotations/annotations.json"
    with open(annotations_json_path, 'r', encoding='utf-8') as f:
        original_actions = json.load(f)
    processed_actions = post_process_actions(original_actions)
    processed_annotations_path = os.path.join(os.path.dirname(annotations_json_path), "processed_annotations.json")
    with open(processed_annotations_path, 'w', encoding='utf-8') as f:
        json.dump(processed_actions, f, indent=4)
    print(f"Post-processing complete. Processed annotations saved at: {processed_annotations_path}")
    
    # Determine the session folder as the parent of the annotations folder.
    session_folder = os.path.dirname(os.path.dirname(annotations_json_path))
    session_images_dir = os.path.join(session_folder, "images")
    delete_unused_images(processed_actions, session_images_dir)

if __name__ == "__main__":
    main_post_processing()
