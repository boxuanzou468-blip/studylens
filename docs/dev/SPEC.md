# StudyLens：學習影片 AI 目錄與重點標註工具（需求與框架文件）

> **給實作者（GPT）**：請依本文件實作 StudyLens。照「六、實作順序」一步一步做，每完成一步先自我驗收再繼續。需求有不清楚或互相矛盾的地方，先提問，不要自行猜測。

## 背景
使用者手邊常有大量內容雜亂的學習影片，不知道哪些段落是自己需要的。本工具讓使用者自己的 AI agent（Claude Code 或 GPT/Codex）讀取這些影片，並依照「使用者想學什麼」做兩件事：
1. 產生跨影片的**目錄**：每支影片講什麼、每一段講什麼。
2. 為每一段**個人化標註**：重點聽／正常看／可加速／可跳過。

最後輸出一份可點擊的 HTML 報告。

**核心設計：skill 模式**
- 本專案不呼叫任何 AI API，也不需要 API key。
- 使用者下載 repo 後，讓自己的 Claude Code 或 Codex 讀取 `SKILL.md`，由那個 AI 照著流程執行。
- 分工原則：**需要判斷的事交給 AI**（分段、摘要、標註），**機械性的事交給腳本**（轉錄、檢查、產生 HTML）。
- 唯一限制：AI 聽不到聲音，所以需要一支本機 Whisper 腳本先把語音轉成帶時間戳的文字。這一步免費、在本機完成；如果影片已有同名字幕檔，就直接使用、跳過轉錄。

**第一版範圍**：只處理本機影片檔，形態是命令列加上 HTML 報告。不做 B 站／YouTube 連結，也不做 GUI（架構上預留擴充空間）。

---

## 一、Repo 結構
```
studylens/
├── SKILL.md                 # 核心：交代 AI 的完整工作流程（Claude Code skill 格式，含 frontmatter）
├── AGENTS.md                # Codex/GPT 入口：簡短說明並指向 SKILL.md
├── scripts/
│   ├── check_env.py         # 檢查 Python ≥3.10、ffmpeg、faster-whisper；缺什麼就列出安裝指令
│   ├── scan.py              # 掃描影片資料夾 → .studylens/manifest.json
│   ├── transcribe.py        # faster-whisper 轉錄 → .studylens/transcripts/<id>.json（可續跑）
│   ├── chunk.py             # 把逐字稿切成帶時間戳的文字區塊，供 AI 分批讀取
│   ├── validate.py          # 依 schema 檢查 AI 寫的分析 JSON，錯誤要清楚指出
│   └── build_report.py      # 所有分析 JSON → report.html（單一檔案）
├── templates/report.html    # 報告模板（原生 HTML/CSS/JS，不依賴 CDN）
├── schema/
│   ├── profile.schema.json
│   ├── video_analysis.schema.json
│   └── library.schema.json
├── examples/                # 範例 analysis JSON 和報告截圖
├── requirements.txt         # faster-whisper、jsonschema（盡量精簡）
└── README.md                # 中英雙語：用途、截圖、安裝、怎麼叫 AI 使用
```
所有工作檔都寫在影片資料夾裡的 `.studylens/` 目錄，報告輸出到影片資料夾根目錄的 `studylens-report.html`，這樣影片就能用相對路徑播放。

## 二、AI 工作流程（`SKILL.md` 要寫清楚的內容）

**步驟 0：環境檢查**
執行 `check_env.py`，缺少套件就引導安裝。

**步驟 1：訪談使用者**（必做，分析開始前完成）
問以下問題，結果存成 `.studylens/profile.json`：
- 影片資料夾路徑
- **最想學的知識或目標**（必填，可以填多個）
- 目前程度：新手／有基礎／進階（用來判斷哪些內容「已經會了，可以加速」）
- 可選：時間預算、偏好的語言

**步驟 2：掃描影片**
執行 `scan.py`，列出影片 id、檔名、時長，以及有沒有同名字幕（.srt/.vtt/.ass）。

**步驟 3：轉錄**
執行 `transcribe.py`：
- 有字幕就轉換字幕格式，沒有字幕才用 Whisper 轉錄。
- 已完成的影片要跳過（可以續跑）。
- 長時間任務放到背景執行，並顯示進度。
- 預設模型 `small`，可以用參數改。偵測到 GPU 就用 GPU。

**步驟 4：逐支影片分析**（AI 的核心工作）
先用 `chunk.py` 取得區塊，每塊約 6000 字，附時間戳。讀完一支影片就寫出 `.studylens/analysis/<id>.json`，接著跑 `validate.py`，通過後才換下一支。一次只讀一支，避免塞爆 context。

**步驟 5：跨影片彙整**
讀取所有分析 JSON 的摘要層（不重讀逐字稿），寫出 `.studylens/library.json`，內容包括：
- 推薦學習路徑：依照目標排序的「影片＋段落」清單
- 主題索引：每個主題對應到哪些影片的哪些時間點
- 總時長、建議觀看時長、省下多少時間

**步驟 6：產生報告**
執行 `build_report.py`，然後幫使用者打開 `studylens-report.html`。

**標註規則**（寫進 SKILL.md）

| 標籤 | 顏色 | 判斷標準 |
|---|---|---|
| `must` 重點聽 | 紅 | 直接對應學習目標的核心概念、關鍵示範或結論 |
| `normal` 正常看 | 灰 | 相關的鋪陳或背景 |
| `speed` 可加速 | 黃 | 相關但節奏慢、重複講，或是以使用者程度來說已經會的基礎內容（建議 1.5～2 倍速） |
| `skip` 可跳過 | 淡色 | 離題閒聊、廣告、開場和片尾、重複的內容 |

另外三條規則：
- 每段都要附一句**理由**。
- 分段長度約 1～5 分鐘，對齊語句邊界；**段落要完整覆蓋整支影片，不能有空隙或重疊**。
- 每段都要有標題、2～3 句摘要和關鍵知識點（keypoints）。

## 三、資料格式（schema 重點欄位）
- `video_analysis`：
  - 影片層：`video_id`、`title`、`summary`、`topics[]`、`relevance`（0–100，跟學習目標的相關度）
  - 段落：`segments[]`，每段包含 `start`、`end`（秒）、`title`、`summary`、`keypoints[]`、`label`、`reason`、`speed`（只有 speed 標籤才填，例如 1.75）
- `library`：`learning_path[]`、`topic_index{}`、`stats{total_sec, recommended_sec, saved_sec}`
- `validate.py` 除了檢查 schema，還要檢查：時間不重疊、覆蓋完整、`end` 不超過影片時長。

## 四、HTML 報告功能
- **頂部**：學習目標、統計數字（總共 X 小時，建議看 Y 小時，省下 Z）、推薦學習路徑（可以點）
- **左欄目錄**：
  - 每支影片一列：標題、一句話摘要、相關度條，再加一條**彩色迷你時間軸**（紅黃灰區塊一眼看出哪裡是重點）
  - 點一下展開段落列表，每段顯示時間戳、標題、標籤徽章、摘要和理由
- **右欄播放器**：用 `<video>` 播放本機檔案；點段落就跳到對應時間
- **智慧播放模式**（開關）：播到 `speed` 段自動加速，播到 `skip` 段自動跳過，回到其他段恢復正常速度
- **篩選和搜尋**：只看重點、按主題篩選、關鍵字搜尋
- **技術要求**：單一 HTML 檔，資料內嵌，離線可用，支援深色模式，手機版面不跑版

## 五、限制
- 腳本**不呼叫任何 LLM**，所有判斷都由執行 skill 的 AI 完成。
- 支援 Windows／macOS／Linux：路徑用 `pathlib`，檔案一律 UTF-8，中文檔名和路徑要能正常處理。
- 腳本要能單獨執行，並附 `--help`。錯誤訊息要清楚，因為 AI 會讀這些訊息來自行修正。

## 六、實作順序（每步完成都要可以驗收）
1. 建立 repo 骨架、`requirements.txt`、`check_env.py`
2. `scan.py`、`transcribe.py`（含字幕轉換和續跑）、`chunk.py`
3. 三份 schema 和 `validate.py`
4. 手寫一份範例 `analysis.json` 和 `library.json` 放進 `examples/`
5. `templates/report.html` 和 `build_report.py`：先用範例資料把報告做好
6. 撰寫 `SKILL.md`（流程、訪談問題、標註規則、指令範例）和 `AGENTS.md`
7. README（附截圖）

## 七、驗收方式
- 準備 2～3 支短學習影片（其中一支附 .srt），放在含中文名稱的資料夾。
- 分別在 Claude Code 和 Codex 裡說「用 StudyLens 幫我整理這個資料夾，我想學 X」，確認 AI 會先訪談，再自動跑完整個流程。
- 確認每份分析都通過 `validate.py`，第二次執行時轉錄會被跳過。
- 打開報告檢查：
  - 點段落能跳到正確時間
  - 智慧播放模式會加速或跳過
  - 篩選和搜尋正常
  - 斷網也能用
