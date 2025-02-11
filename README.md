# Action Recorder

# Action Recorder

## Description

**Action Recorder** is a Python utility designed to accelerate GUI action annotation on Windows OS. It monitors a variety of actions to help streamline the documentation process.

### Supported Actions

| Action Type    | Description                                      |
|----------------|--------------------------------------------------|
| `single_click` | Performs a single mouse click.                 |
| `double_click` | Performs a double mouse click.                 |
| `moveTo`       | Moves the cursor to a specified position.      |
| `dragTo`       | Drags an element from one position to another. |
| `vscroll`      | Scrolls vertically.                              |
| `typewrite`    | Types text as if entered via a keyboard.       |
| `press`        | Simulates pressing a single key.               |
| `hotkey`       | Executes a combination of keys as a shortcut.  |

## Installation

Follow these steps to set up Action Recorder:

1. **Create and activate a virtual environment:**

   ```bash
   uv venv record_env --python 3.11.6
   record_env\Scripts\activate


2. **Install required packages:**

    ```bash
    uv pip install -r requirements.txt

## Usage

### Starting the recorder
To begin recording, open PowerShell and run:

```bash
python record.py --id <task_id>
```

Replace `<task_id>` with the unique identifier for the task as listed in your sample tasks.

### Recording guidelines
1. Ending the Recording: Press the `Esc` key.
2. Initial Setup: When the program starts, the current window will be minimized. Please wait at least 2 seconds before beginning any setup actions.
3. Action Buffer: After performing any action, wait 1 second before executing the next action.