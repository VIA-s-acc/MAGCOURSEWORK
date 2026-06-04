#!/usr/bin/env python3
"""Калибровка ROI фотостенда по эталонному снимку (гл. 7, § 7.3).

По фотографии белого экрана (WW) автоматически определяет:
  - активную область дисплея (прямоугольник без синей рамки),
  - белый калибровочный квадрат (для яркостной нормировки),
сохраняет координаты в data/bench/roi_config.json и рисует
overlay-визуализацию (рамки ROI поверх снимка) для документации.

Камера и панель зафиксированы → калибровка выполняется один раз, после
чего вся измерительная кампания использует сохранённые координаты.

Запуск:
    python scripts/calibrate_roi.py docs/inbox/roi_ref.jpg
    python scripts/calibrate_roi.py docs/inbox/roi_ref.jpg --show   # + проверочный кроп
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage

from python.frames import PANEL_H, PANEL_W

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]


def load_gray(path: str) -> np.ndarray:
    im = ImageOps.exif_transpose(Image.open(path)).convert("L")
    return np.asarray(im, dtype=np.float64) / 255.0


def detect_display_bbox(gray: np.ndarray, thr: float = 0.55,
                        min_height: int = 250, x_min: int = 200) -> tuple[int, int, int, int]:
    """Найти активную область дисплея как вертикально-протяжённый яркий блок.

    Дисплей отличается от разъёма/проводов большой высотой яркого прогона.
    """
    mask = gray > thr
    cols = []
    for x in range(x_min, gray.shape[1]):
        ys = np.where(mask[:, x])[0]
        if len(ys):
            cols.append((x, len(ys), ys.min(), ys.max()))
    if not cols:
        raise RuntimeError("дисплей не найден (проверьте thr/освещение)")
    arr = np.array(cols)
    disp = arr[arr[:, 1] > min_height]
    if len(disp) == 0:
        raise RuntimeError("нет столбцов нужной высоты — панель не распознана")
    x0, x1 = int(disp[:, 0].min()), int(disp[:, 0].max())
    y0, y1 = int(np.median(disp[:, 2])), int(np.median(disp[:, 3]))
    return x0, y0, x1, y1


def detect_white_patch(gray: np.ndarray, thr: float = 0.85,
                       x_max: int = 200) -> tuple[int, int, int, int]:
    """Найти белый калибровочный квадрат (яркая область слева от панели)."""
    region = gray.copy()
    region[:, x_max:] = 0.0
    mask = region > thr
    lbl, n = ndimage.label(mask)
    if n == 0:
        raise RuntimeError("белый квадрат не найден")
    sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n + 1))
    cid = int(np.argmax(sizes)) + 1
    ys, xs = np.where(lbl == cid)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def inset(bbox: tuple[int, int, int, int], dx: int, dy: int) -> list[int]:
    x0, y0, x1, y1 = bbox
    return [x0 + dx, y0 + dy, x1 - dx, y1 - dy]


def draw_overlay(path: str, disp: list[int], white: list[int], out_path: Path) -> None:
    """Нарисовать рамки ROI поверх снимка (красная — дисплей, зелёная — квадрат)."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    d = ImageDraw.Draw(im)
    d.rectangle(disp, outline=(255, 40, 40), width=4)
    d.rectangle(white, outline=(40, 220, 40), width=4)
    d.text((disp[0], max(0, disp[1] - 22)), "EPD ROI", fill=(255, 40, 40))
    d.text((white[0], max(0, white[1] - 22)), "white", fill=(40, 220, 40))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # масштабируем до разумной ширины для документа
    w = 700
    im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
    im.save(out_path, quality=88)
    logger.info("overlay saved: %s", out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ref", help="эталонный снимок WW (например docs/inbox/roi_ref.jpg)")
    ap.add_argument("--inset-disp", type=int, nargs=2, default=(2, 2),
                    help="инсет рамки дисплея (dx dy), чтобы избежать синюю кромку")
    ap.add_argument("--inset-white", type=int, nargs=2, default=(8, 8),
                    help="инсет рамки белого квадрата")
    ap.add_argument("--show", action="store_true", help="сохранить проверочный кроп")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    gray = load_gray(args.ref)
    logger.info("снимок %dx%d, mean=%.3f", gray.shape[1], gray.shape[0], gray.mean())

    disp_raw = detect_display_bbox(gray)
    white_raw = detect_white_patch(gray)
    disp = inset(disp_raw, *args.inset_disp)
    white = inset(white_raw, *args.inset_white)

    aspect = (disp[3] - disp[1]) / (disp[2] - disp[0])
    logger.info("дисплей ROI=%s aspect=%.2f (панель %d/%d=%.2f)",
                disp, aspect, PANEL_H, PANEL_W, PANEL_H / PANEL_W)
    logger.info("белый квадрат ROI=%s", white)

    cfg = {
        "source": Path(args.ref).name,
        "panel_bbox": disp,
        "white_patch_bbox": white,
        "panel_w": PANEL_W,
        "panel_h": PANEL_H,
        "note": "камера фиксирована; bbox в пикселях EXIF-выпрямленного снимка; панель портрет 122x250",
    }
    cfg_path = REPO / "data" / "bench" / "roi_config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(cfg, open(cfg_path, "w"), indent=2, ensure_ascii=False)
    logger.info("saved %s", cfg_path)

    overlay_path = REPO / "tex" / "figures" / "raw_photos" / "roi_overlay.jpg"
    draw_overlay(args.ref, disp, white, overlay_path)

    if args.show:
        from python.photo_pipeline import build_capture
        cap = build_capture(gray, panel_bbox=tuple(disp), white_patch_bbox=tuple(white))
        chk = REPO / "data" / "bench" / "roi_check.png"
        Image.fromarray((np.clip(cap.reflectance, 0, 1) * 255).astype("uint8"), "L") \
            .resize((PANEL_W * 3, PANEL_H * 3)).save(chk)
        logger.info("проверочный кроп: %s (white_level=%.3f)", chk, cap.white_level)

    print(f"\nROI откалиброван. Конфиг: {cfg_path}\nOverlay: {overlay_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
