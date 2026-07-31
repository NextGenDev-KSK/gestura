"""Record a custom gesture from the webcam and add it to your gesture library.

    python scripts/record_gesture.py --name my_gesture [--samples 40] [--camera 0]

Hold the hand shape steady while it captures examples, then bind the new gesture to an action in
the app's settings (or edit ``custom_gestures.json`` / ``settings.json`` directly). Fully offline.
"""

from __future__ import annotations

import argparse
import time

from gestura.engine.custom import CustomGestureClassifier
from gestura.util.logging import configure
from gestura.util.paths import data_dir
from gestura.vision import CameraSource, HandTracker, ModelNotFoundError


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a custom gesture for Gestura")
    parser.add_argument("--name", required=True, help="Name for the new gesture")
    parser.add_argument("--samples", type=int, default=40, help="Number of examples to capture")
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()

    configure(to_file=False)
    store_path = data_dir() / "custom_gestures.json"
    classifier = CustomGestureClassifier.load(store_path)

    try:
        tracker = HandTracker(num_hands=1, mirrored=True)
    except ModelNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    cam = CameraSource(args.camera, width=640, height=480, fps=60)
    cam.start()
    print(f"Recording gesture '{args.name}'. Hold the pose steady in view.")

    # Wait for the camera + a visible hand.
    deadline = time.perf_counter() + 12
    while time.perf_counter() < deadline:
        frame = cam.latest()
        if frame is not None:
            res = tracker.process(frame.image, frame_index=frame.index)
            if res.has_hand:
                break
        time.sleep(0.02)
    else:
        print("No hand detected — aborting.")
        cam.stop(); tracker.close()
        return 1

    for n in (3, 2, 1):
        print(f"  capturing in {n}…")
        time.sleep(0.8)

    collected = 0
    last_index = -1
    while collected < args.samples:
        frame = cam.latest()
        if frame is None or frame.index == last_index:
            time.sleep(0.005)
            continue
        last_index = frame.index
        res = tracker.process(frame.image, frame_index=frame.index)
        hand = res.primary
        if hand is not None and hand.score >= 0.6:
            classifier.add_sample(args.name, hand)
            collected += 1
            print(f"\r  captured {collected}/{args.samples}", end="")
    print()

    cam.stop()
    tracker.close()
    classifier.save(store_path)
    print(f"\nDone. '{args.name}' now has {classifier.sample_count(args.name)} samples.")
    print("Bind it to an action in Settings, or add a binding in settings.json:")
    print(f'   {{ "gesture": "{args.name}", "action": "screenshot" }}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
