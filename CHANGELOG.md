# Changelog

## 0.2.0

Gestura now behaves like a proper background utility.

### Added
- **System tray.** Closing the window keeps gesture control running in the background. The tray
  icon shows whether control is on or paused; its menu shows the window, pauses/resumes, or quits.
- **Global pause hotkey** (default **Ctrl+Alt+G**). Pause or resume from anywhere, even with the
  window hidden, because the keyboard is the one input a misbehaving gesture can't take away.
  Change it under Settings → Background & startup.
- **Start with Windows** and **start minimized to the tray**. Both settings existed before but did
  nothing; they now work. The installer's startup option writes the same entry, so the two never
  disagree or launch Gestura twice.
- **Single instance.** Launching Gestura while it's already running brings the existing window
  forward instead of starting a second engine that fights over the camera.
- **Reach calibration.** Settings → Cursor → Calibrate: sweep your hand over the area that feels
  comfortable and the cursor maps exactly that area onto the whole screen, even if it's off-centre.
  The preview shows the active area as a dashed frame.
- **Camera picker** (Settings → Camera) with live switching, and a **camera preview toggle**. With
  the preview off, gesture control keeps running and per-frame image conversion is skipped.
- First-use hint ("Raise your hand in front of the camera") and the resume hotkey on the
  paused badge.
- App icon for the window, taskbar, tray, .exe and installer.

### Fixed
- "Mirror camera" and other camera/tracking settings now apply immediately; previously they only
  took effect after restarting the app.
- The paused state now updates in the UI even when no camera frames are arriving.

## 0.1.0

First release: the full gesture pipeline, built-in gestures (clicks, drag, scroll, two-hand zoom,
volume, media, window switching, screenshot, keyboard shortcuts), the in-app gesture editor and
trainer, settings with automatic migration, and the Windows build.
