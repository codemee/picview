# PicView

使用 Qt 打造的圖片資料夾檢視器。

[English](README.md)

## 安裝與啟動

### 桌面版下載

- 已附加桌面版的版本可從 [GitHub Releases](https://github.com/codemee/picview/releases) 下載，不需要安裝 Python 或 uv。
- **Windows x64：**直接執行 `PicView-<版本>-windows-x64.exe`。
- **macOS Apple Silicon：**開啟 `PicView-<版本>-macos-arm64.dmg`，將 **PicView.app** 拖曳到 **Applications**。
- 桌面版目前沒有 Windows 發行者簽章或 Apple Developer ID 公證，首次開啟時可能會出現系統提示或遭到阻擋。

### 使用 uv

- 需要先安裝 [uv](https://docs.astral.sh/uv/getting-started/installation/)，並在圖形桌面環境執行。PicView 目前於 Windows 開發與測試。
- 不永久安裝工具，直接執行：

  ```powershell
  uvx picview
  ```

- 安裝為命令列工具，再啟動：

  ```powershell
  uv tool install picview
  picview
  ```

- 更新已安裝的版本：

  ```powershell
  uv tool upgrade picview
  ```

- 查詢版本：

  ```powershell
  picview --version
  # 或不安裝直接查詢：
  uvx picview --version
  ```

## 從原始碼啟動

在專案目錄中執行：

```powershell
uv run picview
```

## 使用方式

### 開啟圖片

- 視窗標題會顯示目前版本，例如 **PicView v0.0.2**。
- 點擊 **開啟資料夾**，或將資料夾、圖片檔案拖曳至視窗中。
- 旋轉與鏡射功能只影響目前的檢視畫面，不會修改圖片檔案。

### 縮放與縮圖大小

- 圖片大小未超出窗格時，以原始像素大小（100%）顯示；較大的圖片會縮放至符合窗格。
- 點擊 **符合窗格**，即可在符合窗格與原始大小之間切換。
- 使用縮放滑桿或 `+` / `-` 調整顯示比例；按 `0` 回到 100%。
- 點擊任一滑桿左側的數值，即可輸入精確的縮放百分比或縮圖大小。
- 在數值輸入視窗中：
  - 按 `Enter` 套用。
  - 按 `Esc` 或點擊視窗外部取消。
  - 使用重設按鈕，將顯示比例還原為 100%，或將縮圖大小還原為 140 像素。

### 鍵盤快捷鍵

| 操作 | 快捷鍵 |
| --- | --- |
| 上一張圖片 | `Left`（左方向鍵）、`Page Up` 或 `Backspace` |
| 下一張圖片 | `Right`（右方向鍵）、`Page Down` 或 `Space`（空白鍵） |
| 第一張／最後一張圖片 | `Home` / `End` |
| 開啟全螢幕 | `F11` |
| 關閉全螢幕 | `Esc` |
| 開啟資料夾 | 系統的「開啟」快捷鍵 |
| 將選取的圖片檔案複製到剪貼簿 | `Ctrl+C`（Windows / Linux）、`Command+C`（macOS） |

### 配色

- 點擊配色按鈕，依序切換 **跟隨系統**、**淺色** 與 **深色**。
- 預設為 **跟隨系統**。
