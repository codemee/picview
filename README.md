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

- The window title shows the current version (for example, **PicView v0.0.5**).
- Click **Open folder**, or drop a folder or image file onto the window.
- Drag a thumbnail or its filename to send the original image file to another application that accepts file drops.
- Rotation and mirror controls only affect the current view; image files are never modified.
- The language button cycles through **Follow system → Chinese (中) → English (En)**. The system icon shows smaller Chinese and English glyphs separated by a diagonal line. It follows the system by default, using Chinese for Chinese locales and English otherwise, and remembers the mode across restarts.
- The current folder is monitored automatically. New images appear in the thumbnail pane without resetting the current view. If the viewed image is deleted, a notification appears at the bottom and the next image is selected; deleting the last image wraps to the first, and an empty folder clears the image pane.
- Modified files automatically refresh their thumbnails and the current image, including full screen, while preserving zoom, rotation, mirroring, and scroll position. The last complete image remains visible while a file is still being written.

### Multiple folder tabs

- **Open folder** or **＋** opens a folder in a new tab. Dropping multiple folders opens each one. The same folder can be opened in multiple tabs with independent image selections, allowing comparison of images within one folder.
- Right-click a tab and choose **Duplicate tab** to create a copy beside it, preserving its selection and view settings. In comparison mode, duplicating a checked tab also adds the copy to comparison.
- Drag tabs to reorder them and use their close buttons to close them. Closing the last tab leaves an empty tab.
- Each tab keeps its own selection, zoom, rotation, mirroring, scroll positions, thumbnail size, and pane layout. Language and theme are shared.
- All tabs continue monitoring files; background animations pause. A **●** marks a background deletion notification, which appears when switching back.
- Restarting restores all tabs, their order, and the active tab. Missing folders keep their tabs and resume monitoring when they return.
- Use the platform's New Tab, Close, Next Tab, and Previous Tab shortcuts; common Windows bindings are `Ctrl+T`, `Ctrl+W`, `Ctrl+Tab`, and `Ctrl+Shift+Tab`.

### Compare images across folders

- Enable **Compare images** to replace tab folder icons with checkboxes. The current folder is checked initially.
- Check folders to divide the image area equally in tab order: side by side when thumbnails are above the images, and stacked when thumbnails are beside the images. Switch tabs to select each folder's own image from its thumbnails.
- Comparison panes share one toolbar above the images. Click an image pane to select it, indicated by a blue border. Each pane keeps independent zoom, rotation, mirroring, and scrolling. Visible background images continue updating when files change.
- Disable comparison to return to normal viewing, keeping each folder's selection and image adjustments.

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
