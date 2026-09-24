"""
Local chess board recognition from a full-screen screenshot (no Gemini, no internet).

NOTE: this file is ASCII-only on purpose, so it works no matter which encoding
your editor saves it in.

One-time setup:
  1) Open a game at the STARTING position and press the overlay button (creates shot.bmp).
  2) python calibrate.py               - select the board with the mouse
  3) python board_reader.py templates  - build piece templates from shot.bmp

After that:  python board_reader.py   (reads shot.bmp)  or from code:
  from board_reader import read_board
  matrix = read_board(path)

Templates depend on the piece theme; if you change site/theme, repeat steps 1-3.
"""
import os
import sys
import json
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "board_config.json")   # created by calibrate.py
TEMPLATE_FILE = os.path.join(HERE, "templates.npz")
# default screenshot: ..\screenshots\shot.bmp (folder "src" next to folder "screenshots")
DEFAULT_SHOT = os.path.join(HERE, "..", "screenshots", "shot.bmp")


def load_config():
    cfg = {"box": None, "my_color": "auto", "start_white_at_bottom": True}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


_cfg = load_config()
BOARD_BOX = tuple(_cfg["box"]) if _cfg["box"] else None  # (left, top, right, bottom) in pixels
MY_COLOR = _cfg["my_color"]                               # "white" / "black" / "auto"
START_WHITE_AT_BOTTOM = _cfg["start_white_at_bottom"]     # white at the bottom on the template screenshot?

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


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "templates":
        make_templates(sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_SHOT)
    else:
        shot = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SHOT
        for line in read_board(shot):
            print(line)