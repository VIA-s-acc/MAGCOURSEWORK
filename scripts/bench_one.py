#!/usr/bin/env python3
"""Один прогон одного baseline на одном сценарии (проверка/отладка стенда).

Выполняет измерение энергии/латентности через INA-трассу и (опционально)
снимает фото панели для расчёта ghosting. Используется как для проверки
работоспособности перед полной кампанией, так и как строительный блок
scripts/run_bench_campaign.py.

Примеры:
    # только измерение E/τ (без фото) — проверка bench_factory на железе:
    python scripts/bench_one.py --port /dev/cu.SLAB_USBtoUART --baseline B0 --scenario 02_bb

    # с фото через телефон-вебкамеру (Iriun/DroidCam/Camo → индекс вебкамеры):
    python scripts/bench_one.py --port ... --baseline B0 --scenario 02_bb --camera 0

    # с фото через IP Webcam (HTTP MJPEG поток):
    python scripts/bench_one.py --port ... --baseline B0 --scenario 02_bb \
        --camera-url http://192.168.1.50:8080/shot.jpg
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
from PIL import Image

from python.bench_protocol import CUSTOM_BASELINES, run_baseline
from python.bridge import open_bridge
from python.frames import SCENARIOS
from python.lut import N_PHASES, N_SUB_FRAMES, N_SUB_LUTS, Lut, Source

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]


def default_balanced_lut() -> bytes:
    """Простая зарядо-сбалансированная LUT для baseline B2..B4 по умолчанию.

    4 активные фазы VSH1/VSL/VSH1/VSL по всем sub-frame, TP=20. Net-заряд
    нулевой при V(VSH1)=−V(VSL). Это рабочая заглушка; для финальной кампании
    LUT подменяется оптимальной (из M5) через --lut.
    """
    lut = Lut.zeros()
    seq = [Source.VSH1, Source.VSL, Source.VSH1, Source.VSL]
    for m in range(N_SUB_LUTS):
        for ph, src in enumerate(seq):
            for sf in range(N_SUB_FRAMES):
                lut.vs[m, ph, sf] = int(src)
    for ph in range(len(seq)):
        for sf in range(N_SUB_FRAMES):
            lut.tp[ph, sf] = 20
    return lut.encode()


def _looks_like_snapshot_url(url: str) -> bool:
    return url.lower().rstrip("/").endswith((".jpg", ".jpeg", ".png", "shot.jpg"))


def capture_photo(camera: int | None, camera_url: str | None, settle_s: float = 1.0):
    """Снять кадр с телефона-камеры. Возвращает PIL.Image.

    Три режима:
    - ``camera_url`` оканчивается на .jpg (IP Webcam snapshot, напр.
      http://IP:8080/shot.jpg) — забирается по HTTP без opencv;
    - ``camera_url`` — MJPEG-поток (http://IP:8080/video) — через cv2;
    - ``camera`` — индекс UVC-вебкамеры (DroidCam/Iriun/нативный режим) — через cv2.
    """
    # Снимок по HTTP — самый простой путь, не требует opencv.
    if camera_url and _looks_like_snapshot_url(camera_url):
        import urllib.request  # noqa: PLC0415
        from io import BytesIO  # noqa: PLC0415
        with urllib.request.urlopen(camera_url, timeout=10) as resp:
            data = resp.read()
        return Image.open(BytesIO(data)).convert("RGB")

    # Иначе — поток/вебкамера через opencv.
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        raise RuntimeError(
            "Для потока/вебкамеры нужен opencv-python: pip install opencv-python.\n"
            "Либо используйте IP Webcam и URL вида http://IP:8080/shot.jpg (без opencv)."
        )
    cap = cv2.VideoCapture(camera_url if camera_url else (camera if camera is not None else 0))
    if not cap.isOpened():
        raise RuntimeError(f"Не удалось открыть камеру (camera={camera}, url={camera_url})")
    time.sleep(settle_s)
    ok, frame = None, None
    for _ in range(5):
        ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("Камера не вернула кадр")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def compute_ghost(photo: Image.Image, scenario_img: np.ndarray) -> dict[str, float]:
    """Посчитать SSIM/residual по фото с использованием ROI-конфига."""
    from python.photo_pipeline import build_capture, compare_to_target

    cfg = json.loads((REPO / "data" / "bench" / "roi_config.json").read_text(encoding="utf-8"))
    gray = np.asarray(photo.convert("L"), dtype=np.float64) / 255.0
    cap = build_capture(
        gray,
        panel_bbox=tuple(cfg["panel_bbox"]),
        white_patch_bbox=tuple(cfg["white_patch_bbox"]),
    )
    return compare_to_target(cap, scenario_img)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default=None, help="serial-порт ESP32")
    ap.add_argument("--baseline", required=True, help="B0..B4")
    ap.add_argument("--scenario", required=True, help="имя сценария, напр. 02_bb")
    ap.add_argument("--camera", type=int, default=None, help="индекс вебкамеры (телефон-камера)")
    ap.add_argument("--camera-url", default=None, help="URL кадра IP Webcam")
    ap.add_argument("--no-sleep", action="store_true", help="не усыплять панель в конце")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.scenario not in SCENARIOS:
        raise SystemExit(f"Неизвестный сценарий {args.scenario!r}. Доступны: {list(SCENARIOS)}")
    scenario_img = SCENARIOS[args.scenario]()

    custom_lut = default_balanced_lut() if args.baseline in CUSTOM_BASELINES else None

    out_dir = REPO / "data" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)

    open_kwargs = {"port": args.port} if args.port else {}
    with open_bridge(**open_kwargs) as bridge:
        res = run_baseline(bridge, args.scenario, scenario_img, args.baseline, custom_lut=custom_lut)

        print("\n=== РЕЗУЛЬТАТ ===")
        print(f"  baseline = {res.baseline},  сценарий = {res.scenario}")
        print(f"  E      = {res.energy_mj:.3f} мДж")
        print(f"  τ      = {res.latency_s:.3f} с")
        print(f"  peak I = {res.peak_ma:.2f} мА")
        print(f"  samples= {res.n_samples}")

        result = {
            "baseline": res.baseline, "scenario": res.scenario,
            "energy_mj": res.energy_mj, "latency_s": res.latency_s,
            "peak_ma": res.peak_ma, "n_samples": res.n_samples,
        }

        if args.camera is not None or args.camera_url:
            print("\n  снимаю фото с камеры...")
            photo = capture_photo(args.camera, args.camera_url)
            photo_path = out_dir / f"oneshot_{args.baseline}_{args.scenario}.jpg"
            photo.save(photo_path, quality=88)
            ghost = compute_ghost(photo, scenario_img)
            result["ghost"] = ghost
            print(f"  фото: {photo_path}")
            print(f"  SSIM = {ghost['ssim']:.4f},  residual = {ghost['residual']:.4f}")

        (out_dir / f"oneshot_{args.baseline}_{args.scenario}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        if not args.no_sleep:
            bridge.sleep()

    print("\nГотово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
