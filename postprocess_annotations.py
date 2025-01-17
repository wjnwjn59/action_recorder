import json
import os

# Define the list of modifier key prefixes for hotkeys
HOTKEY_MODIFIER_PREFIXES = ["Key.shift", "Key.ctrl", "Key.alt", "Key.cmd"]

def is_modifier_key(key):
    return any(key.startswith(prefix) for prefix in HOTKEY_MODIFIER_PREFIXES)

def is_alphanumeric(key):
    if key.startswith("'") and key.endswith("'"):
        char = key.strip("'")
        return char.isalnum() 
    elif key == " ":
        return True
    return False

def are_same_coordinates(action1, action2, delta=5):
    is_x_same = abs(action1['x_start'] - action2['x_start']) <= delta
    is_y_same = abs(action1['y_start'] - action2['y_start']) <= delta
    return is_x_same and is_y_same

def same_scroll_direction(action1, action2):
    is_x_same = action1['dx'] == action2['dx']
    is_y_same = action1['dy'] == action2['dy']
    return is_x_same and is_y_same

def time_difference(action1, action2):
    return action2['timestamp'] - action1['timestamp']

def post_process_actions(actions):
    processed_actions = []
    i = 0
    n = len(actions)

    # To track all image paths used in processed actions
    used_image_paths = set()

    while i < n:
        current_action = actions[i]

        # Rule 1: Hotkey merging
        if current_action['action'] == 'press' and is_modifier_key(current_action['value'][0]):
            hotkey_keys = [current_action['value'][0]]  # Start with the modifier key
            hotkey_before_frame = current_action['before_frame']
            hotkey_after_frame = current_action['after_frame']
            j = i + 1

            # Loop through subsequent actions to form the hotkey
            while j < n:
                next_action = actions[j]
                if (
                    next_action['action'] == 'press' and
                    time_difference(current_action, next_action) <= 1.0
                ):
                    hotkey_keys.append(next_action['value'][0])
                    hotkey_after_frame = next_action['after_frame']
                    j += 1
                else:
                    break

            # If only the modifier key exists and no subsequent actions within time window
            if len(hotkey_keys) == 1:
                hotkey_action = {
                    "action": "press",
                    "button": None,
                    "x_start": None,
                    "y_start": None,
                    "x_end": None,
                    "y_end": None,
                    "n_scrolls": None,
                    "value": hotkey_keys,
                    "before_frame": hotkey_before_frame,
                    "after_frame": hotkey_after_frame
                }
                processed_actions.append(hotkey_action)
                print(f"Processed single modifier key press at index {i}: {hotkey_keys}.")
            else:
                # Create a combined hotkey action
                hotkey_action = {
                    "action": "hotkey",
                    "button": None,
                    "x_start": None,
                    "y_start": None,
                    "x_end": None,
                    "y_end": None,
                    "n_scrolls": None,
                    "value": hotkey_keys,
                    "before_frame": hotkey_before_frame,
                    "after_frame": hotkey_after_frame
                }
                processed_actions.append(hotkey_action)
                print(f"Merged actions from index {i} to {j-1} into hotkey: {hotkey_keys}.")

            # Move to the next unprocessed action
            i = j
            continue

        # Rule 2: Merge two consecutive single clicks into a double click
        if (current_action['action'] == 'single_click') and (i + 1 < n):
            next_action = actions[i + 1]
            if (next_action['action'] == 'single_click' and
                are_same_coordinates(current_action, next_action) and
                time_difference(current_action, next_action) <= 2.0):

                # Create double_click action
                double_click_action = {
                    "action": "double_click",
                    "button": current_action['button'],
                    "x_start": current_action['x_start'],
                    "y_start": current_action['y_start'],
                    "x_end": None,
                    "y_end": None,
                    "n_scrolls": None,
                    "value": None,
                    "before_frame": current_action['before_frame'],
                    "after_frame": next_action['after_frame']
                }
                processed_actions.append(double_click_action)
                print(f"Merged actions at index {i} and {i+1} into double_click.")

                # Mark used images
                used_image_paths.add(current_action['before_frame'])
                used_image_paths.add(next_action['after_frame'])

                i += 2  # Skip the next action as it's merged
                continue

        # Rule 3: Merge single click followed by drag into a single drag
        if (current_action['action'] == 'single_click') and (i + 1 < n):
            next_action = actions[i + 1]
            if (next_action['action'] == 'drag' and
                are_same_coordinates(current_action, {'x_start': next_action['x_start'], 'y_start': next_action['y_start']}, delta=5) and
                time_difference(current_action, next_action) <= 2.0):

                # Merge into drag
                merged_drag_action = {
                    "action": "drag",
                    "button": next_action['button'],
                    "x_start": next_action['x_start'],
                    "y_start": next_action['y_start'],
                    "x_end": next_action['x_end'],
                    "y_end": next_action['y_end'],
                    "n_scrolls": None,
                    "value": None,
                    "before_frame": current_action['before_frame'],
                    "after_frame": next_action['after_frame']
                }
                processed_actions.append(merged_drag_action)
                print(f"Merged actions at index {i} and {i+1} into drag.")

                # Mark used images
                used_image_paths.add(current_action['before_frame'])
                used_image_paths.add(next_action['after_frame'])

                i += 2
                continue

        # Rule 4: Merge consecutive scrolls with same direction and within 1.5s
        if current_action['action'] == 'vscroll':
            scroll_count = current_action['dy']
            scroll_before_frame = current_action['before_frame']
            scroll_after_frame = current_action['after_frame']
            j = i + 1

            while j < n:
                next_action = actions[j]
                if (
                    next_action['action'] == 'vscroll'
                    and same_scroll_direction(current_action, next_action)
                    and time_difference(current_action, next_action) <= 1.5
                ):
                    # Accumulate scrolls
                    scroll_count += next_action['dy']  # Add the dy value (positive or negative)
                    scroll_after_frame = next_action['after_frame']
                    current_action = next_action
                    j += 1
                else:
                    break

            # If merged scrolls, create a new scroll action with the net scroll count
            if abs(scroll_count) > 1:  # Check for multiple scrolls
                merged_scroll_action = {
                    "action": "vscroll",
                    "button": None,
                    "x_start": None,
                    "y_start": None,
                    "x_end": None,
                    "y_end": None,
                    "n_scrolls": scroll_count,  # Positive for up, negative for down
                    "value": None,
                    "before_frame": scroll_before_frame,
                    "after_frame": scroll_after_frame,
                }
                processed_actions.append(merged_scroll_action)
                print(
                    f"Merged {abs(scroll_count)} scrolls {'up' if scroll_count > 0 else 'down'} starting at index {i} into a single scroll with count."
                )

                # Mark used images
                used_image_paths.add(scroll_before_frame)
                used_image_paths.add(scroll_after_frame)

                i = j
                continue

            else:
                # Single scroll, mark its images as used
                used_image_paths.add(current_action['before_frame'])
                used_image_paths.add(current_action['after_frame'])


        # Rule 5: Merge consecutive alphanumerics into "type"
        if current_action['action'] == 'press' and is_alphanumeric(current_action['value'][0]):
            # Initialize typed string
            typed_string = current_action['value'][0].strip("'")
            typed_before_frame = current_action['before_frame']
            typed_after_frame = current_action['after_frame']
            j = i +1

            while j < n:
                next_action = actions[j]
                if (next_action['action'] == 'press' and is_alphanumeric(next_action['value'][0]) and
                    time_difference(current_action, next_action) <= 1.5):

                    # Append character to typed string
                    typed_string += next_action['value'][0].strip("'")
                    typed_after_frame = next_action['after_frame']
                    current_action = next_action
                    j +=1
                else:
                    break

            # Create typed string action
            typed_action = {
                "action": "type",
                "button": None,
                "x_start": None,
                "y_start": None,
                "x_end": None,
                "y_end": None,
                "n_scrolls": None,
                "value": [typed_string],
                "before_frame": typed_before_frame,
                "after_frame": typed_after_frame
            }
            processed_actions.append(typed_action)
            print(f"Merged actions from index {i} to {j-1} into type: '{typed_string}'.")

            # Mark used images
            used_image_paths.add(typed_before_frame)
            used_image_paths.add(typed_after_frame)

            i = j
            continue

        # If none of the rules apply, keep the action as is and mark its images as used
        current_action.pop('timestamp', None)  
        processed_actions.append(current_action)
        used_image_paths.add(current_action['before_frame'])
        used_image_paths.add(current_action['after_frame'])
        i +=1

    return processed_actions

def delete_unused_images(original_actions, processed_actions):
    # Collect all image paths from original actions
    original_image_paths = set()
    for action in original_actions:
        if 'before_frame' in action and action['before_frame']:
            original_image_paths.add(action['before_frame'])
        if 'after_frame' in action and action['after_frame']:
            original_image_paths.add(action['after_frame'])

    # Collect all image paths used in processed actions
    used_image_paths = set()
    for action in processed_actions:
        if 'before_frame' in action and action['before_frame']:
            used_image_paths.add(action['before_frame'])
        if 'after_frame' in action and action['after_frame']:
            used_image_paths.add(action['after_frame'])

    # Determine unused images
    unused_image_paths = original_image_paths - used_image_paths

    # Delete unused images
    for image_path in unused_image_paths:
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
                print(f"Deleted unused image: {image_path}")
            except Exception as e:
                print(f"Failed to delete {image_path}: {e}")
        else:
            print(f"Image not found, skipping deletion: {image_path}")

### Note: Only run this function for demonstration purposes
def main_post_processing():
    # Path to your annotations.json
    annotations_json_path = "data/2024-12-30-09-51-08/annotations/annotations.json"

    # Load actions from JSON
    with open(annotations_json_path, 'r', encoding='utf-8') as f:
        original_actions = json.load(f)

    # Process actions
    processed_actions = post_process_actions(original_actions)

    # Save processed actions to a new JSON file
    processed_annotations_path = os.path.join(os.path.dirname(annotations_json_path), "processed_annotations.json")
    with open(processed_annotations_path, 'w', encoding='utf-8') as f:
        json.dump(processed_actions, f, indent=4)

    print(f"Post-processing complete. Processed annotations saved at: {processed_annotations_path}")

    # Delete unused images
    delete_unused_images(original_actions, processed_actions)

if __name__ == "__main__":
    main_post_processing()
