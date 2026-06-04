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


def _bbox_of(lbl: np.ndarray, cid: int) -> tuple[int, int, int, int]:
    ys, xs = np.where(lbl == cid)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def detect_panel_and_patch(
    gray: np.ndarray, thr: float = 0.5,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Найти панель и белый квадрат как два крупнейших ярких блока.

    Ориентационно-независимо (работает и для портрета, и для ландшафта).
    Эталон — снимок белого поля (WW), где панель равномерно яркая.
    Возвращает (panel_bbox, white_bbox); панель — самый протяжённый
    (по диагонали) блок, квадрат — компактный близкий к квадратному.
    """
    mask = gray > thr
    mask = ndimage.binary_opening(mask, iterations=2)  # убрать мелкий шум
    lbl, n = ndimage.label(mask)
    if n < 2:
        raise RuntimeError(f"найдено {n} ярких блоков (<2): проверьте порог/освещение")
    sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n + 1))
    order = np.argsort(sizes)[::-1]
    # два крупнейших
    b1 = _bbox_of(lbl, int(order[0]) + 1)
    b2 = _bbox_of(lbl, int(order[1]) + 1)

    def diag(b):  # длина диагонали bbox
        return ((b[2] - b[0]) ** 2 + (b[3] - b[1]) ** 2) ** 0.5

    # панель — с большей диагональю (она вытянута); квадрат — меньший
    panel, patch = (b1, b2) if diag(b1) >= diag(b2) else (b2, b1)
    return panel, patch


def select_rois_interactive(path: str, disp_scale: float = 0.6
                            ) -> tuple[list[int], list[int]]:
    """Интерактивно выделить мышью 2 области на кадре (окно OpenCV).

    Шаг 1: выделить активную область ДИСПЛЕЯ (без синей рамки) → Enter/Space.
    Шаг 2: выделить БЕЛЫЙ калибровочный КВАДРАТ → Enter/Space.
    Возвращает (panel_bbox, white_bbox) в координатах полного снимка.
    """
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        raise RuntimeError("Нужен opencv-python: pip install -e \".[dev]\" (или \".[camera]\")")

    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    rgb = np.asarray(im)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    H, W = bgr.shape[:2]
    disp = cv2.resize(bgr, (int(W * disp_scale), int(H * disp_scale)))

    print("\n>>> Выдели рамкой АКТИВНУЮ ОБЛАСТЬ ДИСПЛЕЯ (без синей кромки), затем Enter/Space")
    r1 = cv2.selectROI("1/2: ДИСПЛЕЙ (Enter)", disp, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()
    print(">>> Теперь выдели БЕЛЫЙ КАЛИБРОВОЧНЫЙ КВАДРАТ, затем Enter/Space")
    r2 = cv2.selectROI("2/2: БЕЛЫЙ КВАДРАТ (Enter)", disp, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()

    if r1[2] == 0 or r2[2] == 0:
        raise RuntimeError("Область не выделена (нулевая ширина) — повтори калибровку")

    s = 1.0 / disp_scale
    def unscale(r):
        x, y, w, h = r
        return [int(round(x * s)), int(round(y * s)),
                int(round((x + w) * s)), int(round((y + h) * s))]
    return unscale(r1), unscale(r2)


def detect_rotation(panel_bbox: tuple[int, int, int, int]) -> int:
    """Определить поворот для приведения панели к портрету 122×250.

    Если bbox ландшафтный (ширина > высота) → нужен поворот 90°.
    Точное направление (90 vs 270) уточняется валидацией; по умолчанию 90.
    """
    x0, y0, x1, y1 = panel_bbox
    w, h = x1 - x0, y1 - y0
    return 90 if w > h else 0


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
    ap.add_argument("ref", help="эталонный снимок WW с камеры кампании (IP Webcam)")
    ap.add_argument("--inset-disp", type=int, nargs=2, default=(3, 3),
                    help="инсет рамки дисплея (dx dy), чтобы избежать синюю кромку")
    ap.add_argument("--inset-white", type=int, nargs=2, default=(8, 8),
                    help="инсет рамки белого квадрата")
    ap.add_argument("--rotate", type=int, default=None, choices=[0, 90, 180, 270],
                    help="принудительный поворот (иначе авто по ориентации bbox)")
    ap.add_argument("--interactive", "-i", action="store_true",
                    help="выделить области мышью в окне (надёжнее авто-детекта)")
    ap.add_argument("--show", action="store_true", help="сохранить проверочный кроп")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    gray = load_gray(args.ref)
    logger.info("снимок %dx%d, mean=%.3f", gray.shape[1], gray.shape[0], gray.mean())

    if args.interactive:
        disp, white = select_rois_interactive(args.ref)
        disp_raw = disp  # инсет не применяем — пользователь выделил точно
    else:
        disp_raw, white_raw = detect_panel_and_patch(gray)
        disp = inset(disp_raw, *args.inset_disp)
        white = inset(white_raw, *args.inset_white)
    rotate = args.rotate if args.rotate is not None else detect_rotation(disp_raw)

    logger.info("дисплей bbox=%s (%dx%d), поворот=%d°",
                disp, disp[2] - disp[0], disp[3] - disp[1], rotate)
    logger.info("белый квадрат bbox=%s", white)

    cfg = {
        "source": Path(args.ref).name,
        "panel_bbox": disp,
        "white_patch_bbox": white,
        "rotate_deg": rotate,
        "panel_w": PANEL_W,
        "panel_h": PANEL_H,
        "note": "камера фиксирована; bbox в пикселях EXIF-снимка; поворот приводит к портрету 122x250",
    }
    cfg_path = REPO / "data" / "bench" / "roi_config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(cfg, open(cfg_path, "w"), indent=2, ensure_ascii=False)
    logger.info("saved %s", cfg_path)

    overlay_path = REPO / "tex" / "figures" / "raw_photos" / "roi_overlay.jpg"
    draw_overlay(args.ref, disp, white, overlay_path)

    from python.photo_pipeline import build_capture
    # Сохраним проверочные кропы для ОБОИХ поворотов (90 и 270) — направление
    # уточняется по асимметричному кадру; основной = выбранный rotate.
    for rdeg in sorted({rotate, (rotate + 180) % 360}):
        cap = build_capture(gray, panel_bbox=tuple(disp), white_patch_bbox=tuple(white),
                            rotate_deg=rdeg)
        chk = REPO / "data" / "bench" / f"roi_check_rot{rdeg}.png"
        Image.fromarray((np.clip(cap.reflectance, 0, 1) * 255).astype("uint8"), "L") \
            .resize((PANEL_W * 3, PANEL_H * 3)).save(chk)
        logger.info("кроп rot=%d°: %s (white=%.3f, mean=%.3f)",
                    rdeg, chk.name, cap.white_level, cap.reflectance.mean())

    print(f"\nROI откалиброван. Конфиг: {cfg_path}\nOverlay: {overlay_path}")
    print("Проверочные кропы (rotXX.png) — в data/bench/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
