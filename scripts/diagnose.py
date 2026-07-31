"""Hardware + pipeline diagnostics.

Exercises the real camera and hand tracker for a few seconds and prints a health/perf report:
available cameras, capture FPS, tracker inference latency, and detection rate. Useful both as a
first-run sanity check and as a lightweight benchmark.

    python scripts/diagnose.py [--seconds 5] [--camera 0]
"""

from __future__ import annotations

import argparse
import statistics
import time

import numpy as np

from gestura.util.logging import configure, get_logger
from gestura.vision import CameraSource, HandTracker, ModelNotFoundError, list_cameras

_log = get_logger("gestura.diagnose")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gestura pipeline diagnostics")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    configure(to_file=False)

    print("== Cameras ==")
    cams = list_cameras()
    print(f"  detected indices: {cams or 'none'}")

    print("\n== Tracker init ==")
    try:
        tracker = HandTracker(num_hands=1, mirrored=True)
    except ModelNotFoundError as exc:
        print(f"  ERROR: {exc}")
        return 1
    print("  HandTracker initialised OK")

    # Synthetic frame smoke test (no hand -> zero detections, must not crash).
    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = tracker.process(blank, frame_index=0)
    print(f"  blank-frame detections: {len(result.hands)} (expected 0)")

    print(f"\n== Live capture for {args.seconds:.0f}s on camera {args.camera} ==")
    cam = CameraSource(args.camera, width=args.width, height=args.height, fps=60)
    cam.start()

    # Wait for the stream to warm up (device open + first frames) before timing, so the
    # benchmark measures steady-state throughput rather than camera start-up latency.
    warmup_deadline = time.perf_counter() + 8.0
    while cam.latest() is None and time.perf_counter() < warmup_deadline:
        time.sleep(0.02)
    if cam.latest() is None:
        print("  ERROR: no frames within 8s — camera busy or unavailable")
        cam.stop()
        tracker.close()
        return 1
    print(f"  streaming after {8.0 - (warmup_deadline - time.perf_counter()):.1f}s warmup")

    infer_ms: list[float] = []
    frames = 0
    detections = 0
    last_index = -1
    start = time.perf_counter()
    try:
        while time.perf_counter() - start < args.seconds:
            frame = cam.latest()
            if frame is None or frame.index == last_index:
                time.sleep(0.001)
                continue
            last_index = frame.index
            t0 = time.perf_counter()
            res = tracker.process(frame.image, frame_index=frame.index)
            infer_ms.append((time.perf_counter() - t0) * 1000)
            frames += 1
            if res.has_hand:
                detections += 1
    finally:
        cam.stop()
        tracker.close()

    elapsed = time.perf_counter() - start
    print("\n== Report ==")
    print(f"  camera status at end : {cam.status.value}")
    print(f"  frames processed     : {frames}")
    print(f"  effective FPS        : {frames / elapsed:.1f}")
    if infer_ms:
        print(f"  inference latency    : mean {statistics.mean(infer_ms):.1f} ms | "
              f"p50 {statistics.median(infer_ms):.1f} ms | max {max(infer_ms):.1f} ms")
    print(f"  frames with a hand   : {detections}/{frames} "
          f"({(detections / frames * 100) if frames else 0:.0f}%)")
    if frames == 0:
        print("  NOTE: no frames captured — is a camera connected and free?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
