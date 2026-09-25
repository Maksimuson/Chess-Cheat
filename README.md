# Chess cheat

A small Windows overlay button that captures the screen, recognizes a chess
board locally (no internet, no neural network needed) from the screenshot,
and - if Stockfish is connected - shows the best move.

## Project structure

```
Chess cheat/
|-- src/
|   |-- main.cpp             # entry point
|   |-- screenshot.cpp       # overlay button, screenshot, launches Python
|   |-- screenshot.h
|   |-- board_reader.py      # board recognition + Stockfish query
|   |-- calibrate.py         # one-time calibration of the board's screen position
|   |-- board_config.json    # created by calibrate.py (coordinates, settings)
|   `-- templates.npz        # created by board_reader.py templates (piece templates)
|-- screenshots/
|   `-- shot.bmp             # created by the app when the button is clicked
|-- engine/
|   `-- stockfish.exe        # downloaded separately, see below
|-- Chess cheat.sln
`-- Chess cheat.vcxproj
```

## Why C++ for the overlay and screen capture

The overlay button, the always-on-top window, and the screenshot logic are
written in C++ using the native Win32 API rather than Python or a
higher-level framework. This wasn't an arbitrary choice:

- **Direct access to the Win32 API.** A borderless, click-through,
  always-on-top overlay window (`WS_EX_LAYERED | WS_EX_TOPMOST`) with a
  transparent color key is a Windows-specific concept. C++ talks to
  `user32.dll` and `gdi32.dll` directly, with no wrapper library standing
  between the code and the OS. Python could do this too through `ctypes` or
  `pywin32`, but at that point it's still calling the same Win32 functions,
  just through an extra translation layer.
- **Fast, low-level screen capture.** `BitBlt` with `CAPTUREBLT` copies the
  screen's device context directly into memory with no serialization step.
  Capturing a full 1080p (or higher) screen this way takes milliseconds;
  going through a scripting-language screenshot library adds overhead for
  no benefit here, since the button itself needs to hide, capture, and
  reappear fast enough that the user doesn't notice a flicker.
- **A tiny, self-contained executable.** A compiled C++ program with no
  runtime to install is a single `.exe` that starts instantly and uses very
  little memory sitting idle in the background - appropriate for something
  meant to sit on screen for an entire game.
- **Native, responsive UI thread.** The overlay repaints itself on hover and
  click through the standard Win32 message loop (`WM_PAINT`,
  `WM_MOUSEMOVE`, `WM_LBUTTONUP`), which is the most direct and lightest
  way to get a responsive custom-drawn widget on Windows.
- **Clean interop as a process boundary.** Board recognition and the chess
  engine call are comparatively slow, "batch" operations best expressed in
  Python (OpenCV, NumPy, and the Stockfish UCI text protocol are all much
  more convenient there). Rather than mixing that logic into the UI thread,
  the C++ side spawns Python as a short-lived child process and reads its
  output through a pipe. This keeps the always-on-top button responsive no
  matter how long recognition or engine analysis takes, and keeps each
  language doing what it's better at: C++ for the OS-level UI, Python for
  image processing and scripting the engine.

## What to install

1. **Visual Studio** (2019 or newer) with the "Desktop development with
   C++" workload.
2. **Python 3.10+**, added to `PATH` (check with `python --version`).
3. Python packages:
   ```
   pip install opencv-python numpy
   ```
4. **Stockfish** (optional, only needed for the best-move suggestion):
   download from https://stockfishchess.org/download/ (Windows, x86-64),
   take `stockfish.exe` from the archive and place it at
   `Chess cheat\engine\stockfish.exe`. The path can be changed in
   `board_config.json` via `"engine_path"`.

## Initial setup (once per piece theme)

Piece templates are tied to a specific board color scheme and piece style.
If you change the theme or the site, repeat steps 1-3.

1. Build and run the project (see below), open a game at the **starting
   position**, and click the overlay button - this creates
   `screenshots\shot.bmp`.
2. In the `src` folder, run:
   ```
   python calibrate.py
   ```
   Select the board with the mouse, right along the outer edges of the
   squares, and press ENTER. On the grid preview, press `Y` if it lines up
   correctly, or any other key to redo the selection. Then answer `y`/`n`
   to whether the white pieces are at the bottom in this screenshot.
3. Build the piece templates:
   ```
   python board_reader.py templates
   ```
   You should see a line listing all 12 pieces
   (`bB, bK, bN, bP, bQ, bR, wB, wK, wN, wP, wQ, wR`).

## Building the C++ part

1. Open `Chess cheat.sln` in Visual Studio.
2. Make sure the project only contains `main.cpp`, `screenshot.cpp`, and
   `screenshot.h` (no duplicate/old file defining `SaveScreenBmp` twice).
3. Configuration `Debug` or `Release`, platform `x64`.
4. `Ctrl+F5` to build and run without the debugger.

## Usage

1. Open a game on the site/app.
2. Click the small circular button in the top-left corner of the screen -
   it turns blue while recognition is running.
3. A **Board** window appears with the position matrix, the FEN string, and
   Stockfish's best move (if connected).
4. Right-click the button to close the program.

The 8x8 matrix: `0` is an empty square, positive numbers are your own
pieces, negative numbers are the opponent's (`1` pawn, `2` knight, `3`
bishop, `4` rook, `5` queen, `6` king). Your own color is detected
automatically from the king's position, unless set explicitly in
`board_config.json` (`"my_color": "white"` or `"black"`).

The best move is printed in UCI format, e.g. `e2e4` - meaning move the
piece from square `e2` to square `e4`. A trailing letter (`e7e8q`) marks a
pawn promotion: `q` queen, `r` rook, `b` bishop, `n` knight.

Whose turn it is has to be passed manually as `w`/`b` in the command the
C++ side uses to call Python (`python board_reader.py move w ...`) - it
can't be inferred from a single screenshot with no move history.

## Troubleshooting

If the **Board** window shows an error message instead of a matrix:

| Message | Cause |
|---|---|
| `cannot start python` | Python is not on `PATH` |
| `Cannot open image` | `shot.bmp` is missing |
| `FileNotFoundError ... templates.npz` | `board_reader.py templates` hasn't been run |
| `Board recognition looks wrong (...)` | templates don't match the current theme - rebuild them (see above) |
| `Engine not found` | `stockfish.exe` wasn't found - check `engine_path` |

## Disclaimer

Using tools like this in rated games on chess.com, lichess, and similar
platforms violates their terms of service and can get an account banned.
For reviewing finished games, working through puzzles offline, or practice,
this restriction doesn't apply.
