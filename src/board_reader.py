"""

One-time setup:
  1) Open a game at the STARTING position and press the overlay button (creates shot.bmp).
  2) python calibrate.py               - select the board with the mouse
  3) python board_reader.py templates  - build piece templates from shot.bmp

After that:  python board_reader.py   (reads shot.bmp)  or from code:
  from board_reader import read_board
  matrix = read_board(path)
"""
import os
import sys
import json
import subprocess
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "board_config.json")   # created by calibrate.py
TEMPLATE_FILE = os.path.join(HERE, "templates.npz")
# default screenshot: ..\screenshots\shot.bmp (folder "src" next to folder "screenshots")
DEFAULT_SHOT = os.path.join(HERE, "..", "screenshots", "shot.bmp")
# default engine location: ..\engine\stockfish.exe (put the downloaded exe there)
DEFAULT_ENGINE = os.path.join(HERE, "..", "engine", "stockfish.exe")


def load_config():
    cfg = {
        "box": None,
        "my_color": "auto",
        "start_white_at_bottom": True,
        "engine_path": DEFAULT_ENGINE,
        "turn": "w",          # whose move it is; override per call, see CLI below
        "movetime_ms": 1000,  # how long Stockfish thinks, in milliseconds
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


_cfg = load_config()
BOARD_BOX = tuple(_cfg["box"]) if _cfg["box"] else None  # (left, top, right, bottom) in pixels
MY_COLOR = _cfg["my_color"]                               # "white" / "black" / "auto"
START_WHITE_AT_BOTTOM = _cfg["start_white_at_bottom"]     # white at the bottom on the template screenshot?
ENGINE_PATH = _cfg["engine_path"]
DEFAULT_TURN = _cfg["turn"]
MOVETIME_MS = _cfg["movetime_ms"]

SQ = 48                 # square size after normalization
PIECE_NUM = {"P": 1, "N": 2, "B": 3, "R": 4, "Q": 5, "K": 6}
BACK_RANK = "RNBQKBNR"
KEYS = [c + p for c in "wb" for p in "PNBRQK"]


def load_board(path):
    # np.fromfile + imdecode, because cv2.imread breaks on non-ASCII paths (Windows)
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {path}")
    if BOARD_BOX:
        left, top, right, bottom = BOARD_BOX
        img = img[top:bottom, left:right]
    return img


def split_squares(img):
    h, w = img.shape[:2]
    ys = np.linspace(0, h, 9).astype(int)
    xs = np.linspace(0, w, 9).astype(int)
    return [[img[ys[r]:ys[r + 1], xs[c]:xs[c + 1]] for c in range(8)] for r in range(8)]


def analyze(square):
    """Returns (piece silhouette mask, gray image of the piece on a neutral background)."""
    sq = cv2.resize(square, (SQ, SQ), interpolation=cv2.INTER_AREA)

    # square background color = median of the four corners (also works for highlighted squares)
    k = 5
    corners = np.concatenate([
        sq[:k, :k].reshape(-1, 3), sq[:k, -k:].reshape(-1, 3),
        sq[-k:, :k].reshape(-1, 3), sq[-k:, -k:].reshape(-1, 3),
    ])
    bg = np.median(corners, axis=0)
    diff = np.abs(sq.astype(int) - bg.astype(int)).sum(axis=2)

    raw = (diff > 45).astype(np.uint8)
    raw[:3, :] = 0
    raw[-3:, :] = 0
    raw[:, :3] = 0
    raw[:, -3:] = 0
    raw = cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    # fill the silhouette and drop small junk (coordinate letters etc.)
    mask = np.zeros_like(raw)
    contours, _ = cv2.findContours(raw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        if cv2.contourArea(cnt) >= 60:
            cv2.drawContours(mask, [cnt], -1, 1, thickness=cv2.FILLED)

    gray = cv2.cvtColor(sq, cv2.COLOR_BGR2GRAY)
    gray = np.where(mask > 0, gray, 128).astype(np.uint8)
    return mask, gray


def make_templates(path):
    img = load_board(path)
    squares = split_squares(img)

    def standard(r, c):
        if r == 0:
            return "b" + BACK_RANK[c]
        if r == 1:
            return "bP"
        if r == 6:
            return "wP"
        if r == 7:
            return "w" + BACK_RANK[c]
        return None

    found = {}
    for r in range(8):
        for c in range(8):
            rr, cc = (r, c) if START_WHITE_AT_BOTTOM else (7 - r, 7 - c)
            key = standard(rr, cc)
            if key is None or key in found:
                continue
            found[key] = analyze(squares[r][c])

    out = {}
    for key, (mask, gray) in found.items():
        out[key + "_mask"] = mask
        out[key + "_gray"] = gray
    np.savez(TEMPLATE_FILE, **out)
    print(f"Templates saved to {TEMPLATE_FILE}: {', '.join(sorted(found))}")


def score(mask, gray, tmask, tgray):
    m, tm = mask.astype(bool), tmask.astype(bool)
    union = m | tm
    if union.sum() == 0:
        return 1.0
    iou = (m & tm).sum() / union.sum()
    d = np.abs(gray.astype(int) - tgray.astype(int))[union].mean() / 255
    return (1 - iou) + 0.5 * d


def read_grid(path):
    """8x8 grid: None for an empty square, or a key like 'wP', 'bK'."""
    data = np.load(TEMPLATE_FILE)
    templates = {k: (data[k + "_mask"], data[k + "_gray"]) for k in KEYS}

    squares = split_squares(load_board(path))
    grid = []
    for r in range(8):
        row = []
        for c in range(8):
            mask, gray = analyze(squares[r][c])
            if mask.mean() < 0.04:
                row.append(None)
                continue
            best_key, best = min(
                ((k, score(mask, gray, tm, tg)) for k, (tm, tg) in templates.items()),
                key=lambda x: x[1],
            )
            if best > 0.6:
                print(f"Warning: square ({r},{c}) recognized with low confidence "
                      f"({best_key}, score={best:.2f})", file=sys.stderr)
            row.append(best_key)
        grid.append(row)
    return grid


def detect_my_color(grid):
    """The board is always turned towards the player, so my color = the color whose king is at the bottom."""
    king_row = {}
    for r in range(8):
        for c in range(8):
            if grid[r][c] and grid[r][c][1] == "K":
                king_row[grid[r][c][0]] = r
    if "w" in king_row and "b" in king_row and (king_row["w"] >= 4) != (king_row["b"] >= 4):
        return "w" if king_row["w"] >= 4 else "b"
    # fallback: whose material is greater in the bottom half
    weight = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}
    balance = 0
    for r in range(8):
        for c in range(8):
            if grid[r][c]:
                v = weight[grid[r][c][1]] * (1 if grid[r][c][0] == "w" else -1)
                balance += v if r >= 4 else -v
    return "w" if balance >= 0 else "b"


def read_board(path):
    """8x8 matrix: 0 empty, positive = my pieces, negative = opponent's pieces."""
    grid = read_grid(path)
    me = detect_my_color(grid) if MY_COLOR == "auto" else MY_COLOR[0]
    board = []
    for row in grid:
        board.append([
            0 if key is None else (PIECE_NUM[key[1]] if key[0] == me else -PIECE_NUM[key[1]])
            for key in row
        ])
    return board


class RecognitionError(Exception):
    """Raised when the recognized grid is not a physically possible chess position."""


def validate_grid(grid):
    """Basic sanity check: catches a mismatched piece theme before it reaches the engine.

    A real position has exactly one king per side and a handful of other limits.
    If templates come from the wrong theme, recognition tends to collapse onto one
    or two piece types (often the king), which this catches early with a clear
    message instead of sending garbage to the engine.
    """
    counts = {}
    for row in grid:
        for key in row:
            if key:
                counts[key] = counts.get(key, 0) + 1

    problems = []
    for color in ("w", "b"):
        kings = counts.get(color + "K", 0)
        if kings != 1:
            problems.append(f"{'white' if color == 'w' else 'black'} kings: {kings} (must be 1)")
        if counts.get(color + "P", 0) > 8:
            problems.append(f"{'white' if color == 'w' else 'black'} pawns: {counts.get(color + 'P')} (max 8)")

    if problems:
        raise RecognitionError(
            "Board recognition looks wrong (" + "; ".join(problems) + "). "
            "This usually means the piece templates do not match the current theme - "
            "recalibrate: open a normal game at the starting position with this theme, "
            "then run 'python board_reader.py templates' again."
        )


def board_to_fen(grid, turn, start_white_at_bottom):
    """Piece-placement FEN from an absolute w/b grid (as returned by read_grid).

    Castling rights, en passant, and move counters cannot be known from a single
    screenshot, so they are filled with permissive defaults (full castling rights
    assumed, no en passant). This is fine for "what is the best move right now"
    analysis; it can misjudge a rare position where castling is no longer legal.
    """
    pos = {}
    for r in range(8):
        for c in range(8):
            key = grid[r][c]
            if key is None:
                continue
            color, piece = key[0], key[1]
            if start_white_at_bottom:
                rank, file_idx = 8 - r, c
            else:
                rank, file_idx = r + 1, 7 - c
            pos[(rank, file_idx)] = piece if color == "w" else piece.lower()

    rows = []
    for rank in range(8, 0, -1):
        row, empty = "", 0
        for file_idx in range(8):
            letter = pos.get((rank, file_idx))
            if letter is None:
                empty += 1
                continue
            if empty:
                row += str(empty)
                empty = 0
            row += letter
        if empty:
            row += str(empty)
        rows.append(row)

    return f"{'/'.join(rows)} {turn} KQkq - 0 1"


class Engine:
    """Thin UCI wrapper around a Stockfish (or any UCI engine) process."""

    def __init__(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Engine not found: {path}\n"
                "Download Stockfish from https://stockfishchess.org/download/ "
                "and set its path in board_config.json (\"engine_path\") or place "
                "it at ..\\engine\\stockfish.exe"
            )
        self.proc = subprocess.Popen(
            [path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._send("uci")
        self._wait_for("uciok")
        self._send("isready")
        self._wait_for("readyok")

    def _send(self, cmd):
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _wait_for(self, token, timeout_lines=10000):
        for _ in range(timeout_lines):
            line = self.proc.stdout.readline()
            if not line:
                break
            if token in line:
                return line
        code = self.proc.poll()
        raise RuntimeError(
            f"Engine did not respond with '{token}' (process exit code: {code}). "
            "This usually means the FEN sent to it was not a legal position."
        )

    def best_move(self, fen, movetime_ms=1000):
        self._send(f"position fen {fen}")
        self._send(f"go movetime {movetime_ms}")
        line = self._wait_for("bestmove")
        move = line.split()[1]
        if move == "(none)":
            return None  # checkmate or stalemate in this position
        return move

    def close(self):
        try:
            self._send("quit")
        except Exception:
            pass
        self.proc.terminate()


def suggest_move(shot_path, turn, engine_path=None, movetime_ms=None):
    """Reads the board and asks the engine for the best move. Returns (board, fen, move)."""
    grid = read_grid(shot_path)
    validate_grid(grid)  # fail fast with a clear message instead of a bad FEN reaching the engine
    fen = board_to_fen(grid, turn, START_WHITE_AT_BOTTOM)
    engine = Engine(engine_path or ENGINE_PATH)
    try:
        move = engine.best_move(fen, movetime_ms or MOVETIME_MS)
    finally:
        engine.close()

    me = detect_my_color(grid) if MY_COLOR == "auto" else MY_COLOR[0]
    board = [
        [0 if key is None else (PIECE_NUM[key[1]] if key[0] == me else -PIECE_NUM[key[1]])
         for key in row]
        for row in grid
    ]
    return board, fen, move


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "templates":
        make_templates(sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_SHOT)

    elif len(sys.argv) >= 2 and sys.argv[1] == "move":
        # python board_reader.py move [w|b] [shot_path]
        turn = DEFAULT_TURN
        shot = DEFAULT_SHOT
        rest = sys.argv[2:]
        if rest and rest[0] in ("w", "b"):
            turn, rest = rest[0], rest[1:]
        if rest:
            shot = rest[0]

        try:
            board, fen, move = suggest_move(shot, turn)
        except (RecognitionError, FileNotFoundError, RuntimeError) as e:
            # a clean one-line message instead of a full traceback in the C++ message box
            print(f"ERROR: {e}")
            sys.exit(1)

        for line in board:
            print(line)
        print(f"FEN: {fen}")
        print(f"Best move: {move}" if move else "Best move: none (checkmate/stalemate)")

    else:
        shot = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SHOT
        for line in read_board(shot):
            print(line)