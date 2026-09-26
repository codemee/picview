# PicView

Image folder viewer built with Qt.

[繁體中文](https://github.com/codemee/picview/blob/main/README.zh-TW.md)

## Install and run

### Desktop downloads

- Download desktop builds from [GitHub Releases](https://github.com/codemee/picview/releases) when attached to a release. Python and uv are not required.
- **Windows x64:** run `PicView-<version>-windows-x64.exe` directly.
- **macOS Apple Silicon:** open `PicView-<version>-macos-arm64.dmg`, then drag **PicView.app** into **Applications**.
- Desktop builds currently have no Windows publisher signature or Apple Developer ID notarization, so the operating system may prompt or block the first launch.

### With uv

- Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and a graphical desktop. PicView is developed and tested on Windows.
- Run without a permanent tool installation:

  ```powershell
  uvx picview
  ```

- Install as a command-line tool, then launch:

  ```powershell
  uv tool install picview
  picview
  ```

- Upgrade an installed copy:

  ```powershell
  uv tool upgrade picview
  ```

- Check the version:

  ```powershell
  picview --version
  # Or without installing:
  uvx picview --version
  ```

## Run from source

From the project directory, run:

```powershell
uv run picview
```

## Usage

### Open images

- The window title shows the current version (for example, **PicView v0.0.1**).
- Click **Open folder**, or drop a folder or image file onto the window.
- Rotation and mirror controls only affect the current view; image files are never modified.

### Zoom and thumbnail size

- Images open at their original pixel size (100%) when they fit; larger images are scaled to fit the pane.
- Click **Fit to pane** to toggle between fitted and original size.
- Use the zoom slider or `+` / `-` to resize the view; press `0` to return to 100%.
- Click the value to the left of either slider to enter an exact zoom percentage or thumbnail size.
- In the value popup:
  - Press `Enter` to apply.
  - Press `Esc` or click outside to cancel.
  - Use the reset button to restore 100% zoom or the 140 px thumbnail size.

### Keyboard shortcuts

| Action | Shortcut |
| --- | --- |
| Previous image | `Left`, `Page Up`, or `Backspace` |
| Next image | `Right`, `Page Down`, or `Space` |
| First / last image | `Home` / `End` |
| Open full screen | `F11` |
| Close full screen | `Esc` |
| Open a folder | System Open shortcut |
| Copy the selected image file to the clipboard | `Ctrl+C` (Windows / Linux), `Command+C` (macOS) |

### Theme

- Click the theme button to cycle through **Follow system**, **Light**, and **Dark**.
- **Follow system** is the default.
