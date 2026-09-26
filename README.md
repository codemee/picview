# PicView

Image folder viewer built with Qt.

Run it with:

```powershell
uv run picview
```

Use **Open Folder** or drop a folder/image file onto the window. Images are never modified: rotation and mirror controls only affect the current view.

Images open at their original pixel size (100%) when they fit; larger images are scaled to fit the pane. Use the Fit to pane button to toggle between fitted and original size, the zoom slider or `+` / `-` to resize the view, and `0` to return to 100%.

Click the value to the left of either slider to enter an exact zoom percentage or thumbnail size. Press Enter to apply, or press Esc or click outside to cancel. The popup also has a button to restore 100% zoom or the 140px thumbnail size.

Keyboard shortcuts: Left / Right, Page Up / Page Down, and Backspace / Space select the previous / next image. Home / End select the first / last image. F11 opens full screen; Esc closes it. The system's Open shortcut opens a folder, and the system's Copy shortcut copies the selected image file to the clipboard (Ctrl+C on Windows and Linux, Command+C on macOS).

The theme button cycles through Follow system, Light, and Dark. Follow system is the default.
