# Chess cheat

A small Windows overlay button that captures the screen, recognizes a chess
board locally (no internet, no neural network needed) from the screenshot,
and - if Stockfish is connected - shows the best move.

The project has two parts:

- **Overlay (C++)** - an always-on-top camera button. One click captures the
  screen, runs the recognizer and shows the result in a small window.
- **Setup window (`app.py`, Python/Tkinter)** - a chess-themed window for the
  one-time setup: screenshot, board calibration and piece templates. It can
  also launch the overlay.

## Project structure

```
Chess cheat/
|-- src/
|   |-- main.cpp             # entry point of the overlay
|   |-- screenshot.cpp       # overlay button, screenshot, launches Python
|   |-- screenshot.h
|   |-- app.py               # setup window (screenshot, calibration, templates, launcher)
|   |-- board_reader.py      # board recognition + Stockfish query
|   |-- board_config.json    # created by app.py (board position, settings)
|   `-- templates.npz        # created by app.py (piece templates)
|-- screenshots/
|   `-- shot.bmp             # created on every screenshot
|-- engine/
|   `-- stockfish.exe        # downloaded separately, see below
|-- Chess cheat.sln
`-- Chess cheat.vcxproj
```

The overlay looks for its files in `Desktop\Chess cheat\` (see `InitPaths` in
`screenshot.cpp`), so keep the project there or change that path.

## Why C++ for the overlay and screen capture

The overlay button, the always-on-top window, and the screenshot logic are
written in C++ using the native Win32 API rather than Python or a
higher-level framework. This wasn't an arbitrary choice:

- **Direct access to the Win32 API.** A borderless, always-on-top overlay
  window (`WS_EX_LAYERED | WS_EX_TOPMOST`) with a transparent color key is a
  Windows-specific concept. C++ talks to `user32.dll` and `gdi32.dll`
  directly, with no wrapper library between the code and the OS.
- **Fast, low-level screen capture.** `BitBlt` with `CAPTUREBLT` copies the
  screen's device context straight into memory. Capturing a full 1080p (or
  higher) screen takes milliseconds, so the button can hide, capture and
  reappear without a visible flicker.
- **A tiny, self-contained executable.** A compiled C++ program with no
  runtime to install is a single `.exe` that starts instantly and uses very
  little memory while idle - appropriate for something that sits on screen
  for an entire game.
- **Native, responsive UI thread.** The overlay repaints itself on hover and
  click through the standard Win32 message loop (`WM_PAINT`,
  `WM_MOUSEMOVE`, `WM_LBUTTONUP`).
- **Clean interop as a process boundary.** Board recognition and the engine
  call are slow "batch" operations that are much more convenient in Python
  (OpenCV, NumPy, the Stockfish UCI text protocol). The C++ side spawns
  Python as a short-lived child process and reads its output through a pipe,
  so the button stays responsive however long recognition or analysis takes.

## What to install

1. **Visual Studio** (2019 or newer) with the "Desktop development with
   C++" workload.
2. **Python 3.10+**, added to `PATH` (check with `python --version`).
3. Python packages:
   ```
   pip install pillow opencv-python numpy
   ```
4. **Stockfish** (optional, only needed for the best-move suggestion):
   download from https://stockfishchess.org/download/ (Windows, x86-64),
   take `stockfish.exe` from the archive and place it at
   `Chess cheat\engine\stockfish.exe`. The path can be changed in
   `board_config.json` via `"engine_path"`.

## Building the overlay

**Visual Studio:**

1. Open `Chess cheat.sln`.
2. Make sure the project contains only `main.cpp`, `screenshot.cpp` and
   `screenshot.h`.
3. Choose `Release` (or `Debug`) and platform `x64`.
4. Build -> Rebuild Solution. The `.exe` ends up in `x64\Release\` (the exact
   path is printed in the Output window).

**Command line** (from "Developer Command Prompt for VS", inside `src`):

```
cl /EHsc /O2 main.cpp screenshot.cpp /Fe:overlay.exe /link /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup
```

To get rid of the console window in a Visual Studio build, put these two
lines at the very top of `main.cpp`:

```cpp
#pragma comment(linker, "/SUBSYSTEM:WINDOWS")
#pragma comment(linker, "/ENTRY:mainCRTStartup")
```

Close the overlay before rebuilding, otherwise the linker cannot overwrite
the `.exe`.

## Initial setup (once per piece theme)

Piece templates are tied to a specific board color scheme and piece style.
If you change the theme or the site, repeat steps 1-3.

Run the setup window:

```
cd src
python app.py
```

1. Open a game at the **starting position** and press
   **1. Take screenshot**. The window hides itself while the screen is
   captured.
2. Press **2. Calibrate board** and drag a square over the board, exactly
   along the outer edges of the squares (no frame, no coordinates). The red
   8x8 grid shows how it lines up; arrow keys move the selection by 1 px and
   `+` / `-` resize it. Tick the checkbox if the white pieces are at the
   bottom, then press **Accept**.
3. Press **3. Build piece templates**. The log lists all 12 pieces
   (`bB, bK, bN, bP, bQ, bR, wB, wK, wN, wP, wQ, wR`).

A check mark next to a step means it is done.

## Usage

1. In the setup window choose who the move is for under **Move for**:
   - **my side (auto)** - your color is detected from the king's position
     (the board is always turned towards you), so no switching is needed;
   - **White** / **Black** - fixed color.
2. Press **Launch overlay button** and select the overlay `.exe` the first
   time (the path is remembered). The setup window minimizes so it does not
   appear in screenshots.
3. Open a game and click the camera button in the top-left corner of the
   screen - it changes color while recognition is running.
4. A **Board** window shows Stockfish's best move (or an error message).
5. Right-click the button to close the overlay; the setup window comes back.

There is also a **Test: screenshot + best move** button in the setup window
that does the same thing without the overlay.

The best move is printed in UCI format, e.g. `e2e4` - move the piece from
`e2` to `e4`. A trailing letter (`e7e8q`) marks a pawn promotion: `q` queen,
`r` rook, `b` bishop, `n` knight.

Castling rights and en passant cannot be known from a single screenshot, so
the FEN sent to Stockfish assumes full castling rights and no en passant.
That is fine for "best move right now" analysis, but in rare positions it can
suggest an illegal castling move.

## Configuration (`src/board_config.json`)

Created and updated by `app.py`; every key is optional.

| Key | Meaning |
|---|---|
| `box` | board position on the screen: `[left, top, right, bottom]` in pixels |
| `start_white_at_bottom` | whether white was at the bottom on the template screenshot |
| `turn` | `"me"` (auto, default in the setup window), `"w"` or `"b"` |
| `my_color` | `"auto"`, `"white"` or `"black"` (used for the 8x8 matrix) |
| `engine_path` | path to `stockfish.exe` (default `..\engine\stockfish.exe`) |
| `movetime_ms` | how long Stockfish thinks, in milliseconds (default 1000) |
| `overlay_exe` | path to the overlay `.exe` used by the Launch button |

## Command line

```
python board_reader.py templates [shot.bmp]     # build piece templates
python board_reader.py move [w|b] [shot.bmp]    # best move; turn defaults to config
python board_reader.py [shot.bmp]               # print the 8x8 matrix
```

## Troubleshooting

If the **Board** window (or the log in `app.py`) shows an error message:

| Message | Cause |
|---|---|
| `cannot start python` | Python is not on `PATH` |
| `Cannot open image` | `shot.bmp` is missing |
| `FileNotFoundError ... templates.npz` | templates were not built (step 3) |
| `Board recognition looks wrong (...)` | templates don't match the current theme - repeat steps 1-3 |
| `Engine not found` | `stockfish.exe` was not found - check `engine_path` |

The overlay button is still on the screen after closing `app.py`? It is a
separate process: right-click the button, or end `overlay.exe` in Task
Manager.

## Disclaimer

Using tools like this in rated games on chess.com, lichess, and similar
platforms violates their terms of service and can get an account banned.
For reviewing finished games, working through puzzles offline, or practice,
this restriction doesn't apply.
