# Performance notes

Measured on the reference machine (Intel Core Ultra 9 275HX, 32 GB RAM, integrated 1080p webcam),
CPU-only MediaPipe (no GPU delegate).

## Latency budget (motion → cursor)

| Stage | Typical | Notes |
|-------|--------:|-------|
| Camera exposure + capture | 16–33 ms | one frame at 30–60 FPS; dominant in good light |
| MediaPipe HandLandmarker (CPU) | 30–35 ms | per frame, one hand, 640×480 |
| Feature + recognise + interpret | < 1 ms | pure Python/NumPy, no allocations on hot path |
| Action dispatch + `SendInput` | < 1 ms | single batched syscall |

End-to-end is therefore ~**50–70 ms** on CPU. The "< 20 ms" target is the *interpretation* cost
(which we beat by 20×); the pipeline-wide floor is set by MediaPipe inference. Two levers close the
gap when needed:

* **GPU delegate** (`tracking.use_gpu = true`) — offloads inference to the RTX GPU, cutting the
  35 ms stage to single digits. CPU remains the default per the project's CPU-first mandate.
* **One-Euro prediction** — cursor updates are smoothed and de-lagged so *perceived* pointer
  latency is well below the raw inference cadence.

## Frame rate and lighting (important)

Webcam frame rate is often **limited by the camera, not the CPU**:

* **Pixel format.** At 720p+, many webcams default to uncompressed YUY2 and throttle to a few FPS.
  Gestura requests **MJPG** and defaults to **640×480**, which restores full frame rate and is
  more than enough resolution for hand tracking. (Verified: 720p/YUY2 ≈ 9 FPS → 640×480/MJPG ≈
  25 FPS on the same camera.)
* **Auto-exposure in low light.** In a dark room the camera lengthens exposure to gather light,
  which drops FPS dramatically (measured ~2 FPS at night vs ~25 FPS in daylight on the same rig).
  This is physical, not a software bug. Mitigations: add light, or (future setting) cap exposure
  via `CAP_PROP_AUTO_EXPOSURE` at the cost of a darker image.

## Memory

The resident set target is **< 500 MB**. MediaPipe + OpenCV + the Qt UI sit comfortably under this
at 640×480 with a single tracked hand; the hot loop allocates no per-frame Python objects beyond
the typed result records.
