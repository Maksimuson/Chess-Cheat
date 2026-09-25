"""
Calibration: shows the full-screen screenshot, you select the chess board with the mouse.
The coordinates are saved to board_config.json (read by board_reader.py).

Select the board exactly along the outer edges of the squares (no frame, no coordinates)
and press ENTER. Then check the 8x8 grid on the preview: Y = accept, any other key = redo.
"""
import os
import sys
import json
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "board_config.json")
DEFAULT_SHOT = os.path.join(HERE, "..", "screenshots", "shot.bmp")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SHOT
    # fromfile + imdecode: cv2.imread does not understand non-ASCII characters in the path
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        sys.exit(f"Cannot open {path}")

    h, w = img.shape[:2]
    scale = min(1.0, 1500 / w, 850 / h)   # shrink so the screenshot fits in the window
    view = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img

    while True:
        print("Select the board with the mouse and press ENTER (C = cancel)...")
        x, y, rw, rh = cv2.selectROI("Select the board, press ENTER", view, showCrosshair=False)
        cv2.destroyAllWindows()
        if rw == 0 or rh == 0:
            sys.exit("Selection cancelled.")

        side = int(round(min(rw, rh) / scale))          # the board is square
        left, top = int(round(x / scale)), int(round(y / scale))
        box = [left, top, left + side, top + side]

        crop = img[box[1]:box[3], box[0]:box[2]].copy()
        step = side / 8
        for i in range(9):
            p = min(int(round(i * step)), side - 1)
            cv2.line(crop, (p, 0), (p, side - 1), (0, 0, 255), 1)
            cv2.line(crop, (0, p), (side - 1, p), (0, 0, 255), 1)
        preview_scale = min(1.0, 800 / side)
        crop = cv2.resize(crop, None, fx=preview_scale, fy=preview_scale)
        cv2.imshow("Grid preview: Y = accept, any other key = redo", crop)
        key = cv2.waitKey(0) & 0xFF
        cv2.destroyAllWindows()
        if key in (ord("y"), ord("Y")):
            break

    answer = input("Are the WHITE pieces at the bottom on this screenshot? (y/n): ").strip().lower()

    cfg = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    cfg.update({"box": box, "start_white_at_bottom": answer != "n"})
    cfg.setdefault("my_color", "auto")
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print(f"Saved to {CONFIG_FILE}: {cfg}")
    print("Next: python board_reader.py templates")


if __name__ == "__main__":
    main()