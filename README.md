# PicView

使用 Qt 打造的圖片資料夾檢視器。

[English](https://github.com/codemee/picview/blob/main/README.en.md)

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

### 視窗與工具列

- 視窗最小可縮至 **260 × 220 px**。
- 主工具列、縮圖與單圖工具列放不下的工具會收進 <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/more-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/more-light.png" width="34" height="34" alt="更多工具" title="更多工具"></picture>。
- 放寬視窗後，收起的工具會自動恢復。
- 縮圖會優先載入可見範圍，其餘在背景逐步製作。
- 縮圖使用共用的記憶體快取（上限 64 MiB），不另存縮圖檔案。
- 調整窗格大小只重新排列縮圖，不會重新解碼所有圖片。
- 滑桿收起時，可從更多工具選單輸入縮放比例或縮圖大小。
- 視窗標題會顯示目前版本，例如 **PicView v0.0.10**。

### 開啟與拖放圖片

- 點擊 <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/folder-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/folder-light.png" width="34" height="34" alt="開啟資料夾" title="開啟資料夾"></picture>，選擇要檢視的資料夾。
- 將資料夾或圖片檔案拖曳至視窗，也能開啟檢視。
- 按住縮圖或檔名拖曳，可將原始圖檔拖放至接受檔案的其他應用程式。
- 旋轉與鏡射只影響檢視畫面，不會修改圖檔。

### 圖片與窗格工具

| 按鈕 | 操作 |
| --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/rotate-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/rotate-light.png" width="34" height="34" alt="旋轉" title="旋轉"></picture> | 旋轉目前圖片 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/mirror-h-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/mirror-h-light.png" width="34" height="34" alt="水平鏡射" title="水平鏡射"></picture> | 水平鏡射目前圖片 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/mirror-v-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/mirror-v-light.png" width="34" height="34" alt="垂直鏡射" title="垂直鏡射"></picture> | 垂直鏡射目前圖片 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fit-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fit-light.png" width="34" height="34" alt="符合窗格" title="符合窗格"></picture> | 切換符合窗格與原始大小 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/expand-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/expand-light.png" width="34" height="34" alt="最大化窗格" title="最大化窗格"></picture> | 最大化縮圖或單圖窗格 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/shrink-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/shrink-light.png" width="34" height="34" alt="還原窗格" title="還原窗格"></picture> | 還原窗格布局 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fullscreen-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fullscreen-light.png" width="34" height="34" alt="全螢幕" title="全螢幕"></picture> | 開啟目前圖片的全螢幕檢視 |

### 支援格式

- 點陣圖片：JPEG、PNG、WebP、BMP、GIF、TIFF。
- 向量圖片：靜態 SVG。
- SVG 保留透明背景，縮放時會依顯示尺寸重新繪製。
- SVG 支援比圖、旋轉、鏡射及全螢幕。
- SVG 動畫目前以靜態畫面顯示。

### 資料夾監看與自動更新

- 所有已開啟的資料夾都會自動監看檔案變更。
- 新增圖檔：自動加入縮圖窗格，保留目前檢視的圖片。
- 修改圖檔：自動更新縮圖、單圖及全螢幕畫面。
- 更新時保留縮放、旋轉、鏡射與捲動位置。
- 檔案尚未寫完時，先保留上一版完整畫面。
- 目前圖片被刪除：底部顯示通知，並移到排序中的下一張。
- 最後一張被刪除：回到第一張；資料夾清空時，清除大圖。
- 背景標籤的圖片被刪除：標籤顯示 **●**，切回後顯示通知。
- 背景標籤的動畫會暫停。

### 多資料夾標籤

- 點擊 <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/folder-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/folder-light.png" width="34" height="34" alt="開啟資料夾" title="開啟資料夾"></picture> 或標籤列的 **＋**，在新標籤開啟資料夾。
- 一次拖入多個資料夾，會逐一開啟標籤。
- 同一資料夾可開啟多個標籤，各自選圖，方便比較不同圖片。
- 在標籤上按右鍵 → **複製標籤**，在原標籤旁建立副本。
- 副本會保留原標籤的選圖與檢視狀態。
- 比圖模式中，複製已勾選的標籤，副本也會加入比圖。
- 拖曳標籤可調整順序。
- 點擊標籤的關閉按鈕可關閉；關閉最後一頁後，會保留空白標籤。
- 各標籤獨立保留選圖、縮放、旋轉、鏡射、捲動、縮圖大小與窗格布局。
- 語言與配色由所有標籤共用。
- 重開程式會還原所有標籤、順序與目前標籤。
- 暫時不存在的資料夾會保留標籤，重新出現後自動恢復。
- 標籤快捷鍵請見下方「鍵盤快捷鍵」。

### 比較圖片

- 點擊工具列的 <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/compare-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/compare-light.png" width="34" height="34" alt="比圖" title="比圖"></picture>，啟用比較模式。
- 標籤的資料夾圖示會變成核取方塊，預設勾選目前標籤。
- 勾選要比較的標籤，單圖區域會依標籤順序等分。
- <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/split-h-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/split-h-light.png" width="34" height="34" alt="上下版面" title="上下版面"></picture> 上下版面：比較圖片左右並排。
- <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/split-v-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/split-v-light.png" width="34" height="34" alt="左右版面" title="左右版面"></picture> 左右版面：比較圖片上下排列。
- 切換到各標籤，從縮圖選擇該資料夾要比較的圖片。
- 比較窗格共用上方工具列。
- 點擊圖片窗格，指定工具列的操作目標；該窗格會顯示重點色外框。
- 各窗格可獨立縮放、旋轉、鏡射及捲動。
- 比較中的背景圖片也會即時更新。
- 再次點擊 <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/compare-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/compare-light.png" width="34" height="34" alt="比圖" title="比圖"></picture>，回到一般檢視並保留各標籤的選圖與操作狀態。

### 縮放與縮圖大小

- 圖片未超出窗格時，以原始大小 **100%** 顯示。
- 較大的圖片會自動縮放至符合窗格。
- 點擊 <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fit-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/fit-light.png" width="34" height="34" alt="符合窗格" title="符合窗格"></picture>，切換符合窗格與原始大小。
- 拖曳縮放滑桿，或按 <kbd>+</kbd> / <kbd>-</kbd>，調整顯示比例。
- 按 <kbd>0</kbd> 回到 **100%**。
- 點擊滑桿左側的數值，輸入精確的縮放百分比或縮圖大小。
- 在數值輸入視窗按 <kbd>Enter</kbd> 套用。
- 按 <kbd>Esc</kbd> 或點擊視窗外部取消。
- 點擊重設按鈕，還原 **100%** 縮放或 **140 px** 縮圖大小。

### 鍵盤快捷鍵

| 操作 | 快捷鍵 |
| --- | --- |
| 上一張圖片 | <kbd>Left</kbd>（左方向鍵）、<kbd>Page Up</kbd> 或 <kbd>Backspace</kbd> |
| 下一張圖片 | <kbd>Right</kbd>（右方向鍵）、<kbd>Page Down</kbd> 或 <kbd>Space</kbd>（空白鍵） |
| 上一列／下一列縮圖 | <kbd>Up</kbd>（上方向鍵）／<kbd>Down</kbd>（下方向鍵） |
| 第一張／最後一張圖片 | <kbd>Home</kbd> / <kbd>End</kbd> |
| 開啟全螢幕 | <kbd>F11</kbd> |
| 關閉全螢幕 | <kbd>Esc</kbd> |
| 開啟資料夾 | 系統的「開啟」快捷鍵 |
| 在新標籤開啟資料夾 | <kbd>Ctrl</kbd>+<kbd>T</kbd> |
| 關閉目前標籤 | <kbd>Ctrl</kbd>+<kbd>W</kbd> |
| 下一個／上一個標籤（循環切換） | <kbd>Ctrl</kbd>+<kbd>Tab</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Tab</kbd>，或 <kbd>Ctrl</kbd>+<kbd>Page Down</kbd> / <kbd>Ctrl</kbd>+<kbd>Page Up</kbd> |
| 切換到第 1～8 個標籤 | <kbd>Ctrl</kbd>+<kbd>1</kbd>～<kbd>Ctrl</kbd>+<kbd>8</kbd> |
| 切換到最後一個標籤 | <kbd>Ctrl</kbd>+<kbd>9</kbd> |
| 重新開啟剛關閉的標籤 | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>T</kbd>（還原位置與檢視狀態，保留最近 20 筆，限本次執行） |
| 將選取的圖片檔案複製到剪貼簿 | <kbd>Ctrl</kbd>+<kbd>C</kbd>（Windows / Linux）、<kbd>Command</kbd>+<kbd>C</kbd>（macOS） |

- macOS 的新增、關閉、數字切換與重新開啟標籤：使用 <kbd>Command</kbd> 取代 <kbd>Ctrl</kbd>。
- 前後切換標籤也支援系統預設快捷鍵。

### 語言

- 點擊語言按鈕，依序切換 **跟隨系統 → 中文 → 英文**。
- 圖示依序為 <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-system-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-system-light.png" width="34" height="34" alt="語言跟隨系統" title="語言跟隨系統"></picture> → <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-zh-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-zh-light.png" width="34" height="34" alt="中文" title="中文"></picture> → <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-en-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/lang-en-light.png" width="34" height="34" alt="英文" title="英文"></picture>。
- 預設跟隨系統：中文系統顯示中文，其餘顯示英文。
- 重開程式會保留語言選擇。

### 配色

- 點擊配色按鈕，依序切換 **跟隨系統 → 淺色 → 深色**。
- 圖示依序為 <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-system-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-system-light.png" width="34" height="34" alt="配色跟隨系統" title="配色跟隨系統"></picture> → <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-light-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-light-light.png" width="34" height="34" alt="淺色" title="淺色"></picture> → <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-dark-dark.png"><img src="https://raw.githubusercontent.com/codemee/picview/main/docs/icons/theme-dark-light.png" width="34" height="34" alt="深色" title="深色"></picture>。
- 預設為 **跟隨系統**。
- 深色介面採初號機風格：深紫色窗格、螢光綠選取提示與滑桿，以及少量橘色工具點綴。
- 圖片本身的顏色不會改變。
