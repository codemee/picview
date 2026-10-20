# PicView

An image folder viewer built with Qt, focused on **fast loading** and **image comparison**.

[繁體中文](https://github.com/codemee/picview/blob/main/README.md)

## Highlights

### Fast loading

- Load the current image and prioritize visible thumbnails while the rest load progressively in the background, reducing the wait when opening a folder.
- Keep thumbnails in memory for reuse across tabs and layout changes, avoiding repeated decoding without saving thumbnail files to disk.

### Image comparison

- Check tabs to compare images side by side, across different folders or multiple tabs of the same folder.
- Select images, zoom, rotate, mirror, and scroll each comparison pane independently to inspect details and differences.

## Install and run

### Desktop downloads

- Download desktop builds from [GitHub Releases](https://github.com/codemee/picview/releases) when attached to a release. Python and uv are not required.
- **Windows x64**: run `PicView-<version>-windows-x64.exe` directly.
- **macOS Apple Silicon**: open `PicView-<version>-macos-arm64.dmg`, then drag **PicView.app** into **Applications**.
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

### Window and toolbars

- Resize the window down to **260 × 220 px**.
- Tools and folder tabs share one row: folder tabs on the left; open, layout, comparison, language, and theme tools grouped on the right.
- The selected tab meets the content pane directly, removing the gap between the former rows and leaving more room for images.
- Tools that no longer fit move into <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/more-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/more-light.png" width="34" height="34" alt="More tools" title="More tools"></picture> on the main, thumbnail, and image toolbars.
- Widen the window to restore the hidden tools automatically.
- Visible thumbnails load first; the rest are decoded progressively in the background.
- Thumbnails use a shared memory cache (up to 64 MiB), with no thumbnail files saved to disk.
- Resizing panes rearranges existing thumbnails without decoding every image again.
- When sliders are hidden, use the overflow menu to enter zoom or thumbnail-size values.
- The window title shows the current version, for example **PicView v0.0.12**.

### Open and drag images

- Click <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/folder-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/folder-light.png" width="34" height="34" alt="Open folder" title="Open folder"></picture> to choose a folder to view.
- Drop a folder or image file onto the window to open it.
- Drag a thumbnail or its filename to send the original file to another application that accepts file drops.
- Rotation and mirroring only affect the view; they do not modify image files.

### Image and pane tools

| Button | Action |
| --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/rotate-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/rotate-light.png" width="34" height="34" alt="Rotate" title="Rotate"></picture> | Rotate the current image |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/mirror-h-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/mirror-h-light.png" width="34" height="34" alt="Mirror horizontally" title="Mirror horizontally"></picture> | Mirror the current image horizontally |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/mirror-v-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/mirror-v-light.png" width="34" height="34" alt="Mirror vertically" title="Mirror vertically"></picture> | Mirror the current image vertically |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fit-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fit-light.png" width="34" height="34" alt="Fit to pane" title="Fit to pane"></picture> | Toggle fitted and original image size |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/expand-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/expand-light.png" width="34" height="34" alt="Maximize pane" title="Maximize pane"></picture> | Maximize the thumbnail or image pane |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/shrink-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/shrink-light.png" width="34" height="34" alt="Restore pane" title="Restore pane"></picture> | Restore the pane layout |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fullscreen-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fullscreen-light.png" width="34" height="34" alt="Full screen" title="Full screen"></picture> | Open the current image in full screen |

### Supported formats

- Raster images: JPEG, PNG, WebP, BMP, GIF, and TIFF.
- Vector images: static SVG.
- SVG preserves transparency and renders again at the display resolution when zooming.
- SVG supports comparison, rotation, mirroring, and full screen.
- SVG animations currently appear as static images.

### Folder monitoring and automatic updates

- All open folders are monitored for file changes automatically.
- New files appear in the thumbnail pane without changing the current image.
- Modified files refresh their thumbnails, image panes, and full-screen views.
- Updates preserve zoom, rotation, mirroring, and scroll positions.
- The last complete image remains visible while a file is still being written.
- Deleting the current image shows a notification at the bottom and selects the next image in order.
- Deleting the last image wraps to the first; an empty folder clears the image pane.
- A **●** marks a background tab's deletion notification; switch back to read it.
- Animations pause in background tabs.

### Multiple folder tabs

- Click <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/folder-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/folder-light.png" width="34" height="34" alt="Open folder" title="Open folder"></picture> or **＋** to open a folder in a new tab.
- Drop multiple folders to open a tab for each one.
- Open the same folder in multiple tabs to select and compare different images independently.
- Right-click a tab → **Duplicate tab** to create a copy beside it.
- The copy preserves the original tab's image selection and view settings.
- In comparison mode, duplicating a checked tab also adds the copy to comparison.
- Drag tabs to reorder them.
- Secondary tools collapse first when space is limited; excess tabs scroll horizontally and long names are shortened.
- The current tab stays visible when opening tabs, switching tabs, or resizing the window.
- Use a tab's close button to close it; closing the last tab leaves an empty tab.
- Each tab keeps its own selection, zoom, rotation, mirroring, scrolling, thumbnail size, and pane layout.
- Language and theme are shared across all tabs.
- Restarting restores all tabs, their order, and the active tab.
- Missing folders keep their tabs and resume automatically when they return.
- See “Keyboard shortcuts” below for tab shortcuts.

### Compare images

- Click <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/compare-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/compare-light.png" width="34" height="34" alt="Compare images" title="Compare images"></picture> to enable comparison mode.
- Tab folder icons become checkboxes; the current tab is checked initially.
- Check the tabs to compare; the image area divides equally in tab order.
- <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/split-h-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/split-h-light.png" width="34" height="34" alt="Stacked layout" title="Stacked layout"></picture> With thumbnails above the images, comparison panes appear side by side.
- <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/split-v-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/split-v-light.png" width="34" height="34" alt="Side-by-side layout" title="Side-by-side layout"></picture> With thumbnails beside the images, comparison panes are stacked.
- Switch to each tab and select its image from the thumbnails.
- Comparison panes share one toolbar above the images.
- Click an image pane to make it the toolbar's target; an accent-colored border marks it.
- Zoom, rotate, mirror, and scroll each pane independently.
- Visible background images continue updating when files change.
- Click <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/compare-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/compare-light.png" width="34" height="34" alt="Compare images" title="Compare images"></picture> again to return to normal viewing and keep each tab's selection and adjustments.

### Zoom and thumbnail size

- Images that fit the pane open at their original size, **100%**.
- Larger images are scaled to fit the pane automatically.
- Click <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fit-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fit-light.png" width="34" height="34" alt="Fit to pane" title="Fit to pane"></picture> to toggle between fitted and original size.
- Drag the zoom slider or press <kbd>+</kbd> / <kbd>-</kbd> to adjust the view.
- Press <kbd>0</kbd> to return to **100%**.
- Click the value to the left of a slider to enter an exact zoom percentage or thumbnail size.
- In the value popup, press <kbd>Enter</kbd> to apply.
- Press <kbd>Esc</kbd> or click outside to cancel.
- Click reset to restore **100%** zoom or **140 px** thumbnails.

### Background colors for transparent images

- Click <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/background-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/background-light.png" width="34" height="34" alt="Image background" title="Image background"></picture> in the image toolbar to open the background color panel.
- Choose **Default (follow theme)** to use the current theme's image background.
- Choose white, black, gray, light gray, cream, light blue, light green, or light pink to make transparent image details easier to see.
- Dark gray, slate, dark blue, dark green, dark purple, dark red, dark brown, and dark teal backgrounds help inspect light-colored images.
- The 16 background colors appear in four columns of swatches, with color names in tooltips. The default option keeps its text and previews the current theme's default background color.
- The background applies immediately to image and full-screen views, without changing image files or thumbnail backgrounds.
- Tabs and comparison panes keep independent choices, preserved when duplicating tabs or restarting.
- When the toolbar is narrow, open the background panel from **⋯ More tools**.

### Keyboard shortcuts

| Action | Shortcut |
| --- | --- |
| Previous image | <kbd>Left</kbd>, <kbd>Page Up</kbd>, or <kbd>Backspace</kbd> |
| Next image | <kbd>Right</kbd>, <kbd>Page Down</kbd>, or <kbd>Space</kbd> |
| Thumbnail in previous / next row | <kbd>Up</kbd> / <kbd>Down</kbd> |
| First / last image | <kbd>Home</kbd> / <kbd>End</kbd> |
| Open full screen | <kbd>F11</kbd> |
| Close full screen | <kbd>Esc</kbd> |
| Open a folder | System Open shortcut |
| Open a folder in a new tab | <kbd>Ctrl</kbd>+<kbd>T</kbd> |
| Close the current tab | <kbd>Ctrl</kbd>+<kbd>W</kbd> |
| Next / previous tab (wrap around) | <kbd>Ctrl</kbd>+<kbd>Tab</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Tab</kbd>, or <kbd>Ctrl</kbd>+<kbd>Page Down</kbd> / <kbd>Ctrl</kbd>+<kbd>Page Up</kbd> |
| Select tab 1–8 | <kbd>Ctrl</kbd>+<kbd>1</kbd>–<kbd>Ctrl</kbd>+<kbd>8</kbd> |
| Select the last tab | <kbd>Ctrl</kbd>+<kbd>9</kbd> |
| Reopen the last closed tab | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>T</kbd> (restores position and view; remembers up to 20 tabs during this session) |
| Copy the selected image file to the clipboard | <kbd>Ctrl</kbd>+<kbd>C</kbd> (Windows / Linux), <kbd>Command</kbd>+<kbd>C</kbd> (macOS) |

- On macOS, use <kbd>Command</kbd> instead of <kbd>Ctrl</kbd> for new, close, numbered, and reopen tab shortcuts.
- Tab cycling also supports the platform defaults.

### Language

- Click the language button to cycle through **Follow system → Chinese → English**.
- The icons are <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-system-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-system-light.png" width="34" height="34" alt="Follow system language" title="Follow system language"></picture> → <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-zh-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-zh-light.png" width="34" height="34" alt="Chinese" title="Chinese"></picture> → <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-en-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-en-light.png" width="34" height="34" alt="English" title="English"></picture>.
- The default is **Follow system**: Chinese for Chinese locales and English otherwise.
- Your language choice is remembered across restarts.

### Theme

- Click the theme button to cycle through **Follow system → Light → Dark**.
- The icons are <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-system-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-system-light.png" width="34" height="34" alt="Follow system theme" title="Follow system theme"></picture> → <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-light-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-light-light.png" width="34" height="34" alt="Light" title="Light"></picture> → <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-dark-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-dark-light.png" width="34" height="34" alt="Dark" title="Dark"></picture>.
- The default is **Follow system**.
- The dark theme uses a Unit-01-inspired palette: deep purple surfaces, neon green indicators and sliders, and orange tool accents.
- Image colors remain unchanged.
