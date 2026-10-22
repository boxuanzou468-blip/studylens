# 开发测试

从仓库根目录运行；使用已安装 requirements.txt 的 Python。Windows 可将 python 替换为 `.venv\Scripts\python.exe`，macOS/Linux 使用 `.venv/bin/python`。

```sh
python -m unittest discover -s tests -v
```

- 字幕解析、分块、缓存、GPU 回退模拟、schema/语义校验、统计、报告构建不需要模型或网络；依赖只需安装一次。
- `test_real_subtitle_pipeline_resume_and_stale_chunk` 需要 PATH 中的 ffmpeg 和 ffprobe，使用临时合成视频、字幕，不下载 Whisper；工具缺失时自动跳过。
- `test_optional_local_whisper` 仅当 `STUDYLENS_TEST_MODEL` 指定完整本地模型目录且 ffmpeg 可用时运行，否则自动跳过。强制 local_files_only，不下载模型。CI 不设置该变量。
- `acceptance.py <media> --model <local-model>` 是独立的真实 Whisper 验收，不在 unittest discovery 内；需要预先准备的模型和素材。`acceptance_batch2.py` 同样是手动集成验收。

## 浏览器与截图

开发机需 Node.js、Playwright 与 Chromium；这些不是生产依赖。可在仓库外安装 `npm install playwright`，把该处 node_modules 设置为 NODE_PATH。`STUDYLENS_BROWSER_EXECUTABLE` 可指定 Chromium 可执行文件，未设置时使用 Playwright 默认安装。可用 `npx playwright install chromium` 安装浏览器。

先准备专用测试素材：Windows 执行 `./tests/create_fixtures.ps1 -OutputFolder <repo外测试目录>`，需要 ffmpeg；其中 TTS 合成需要 Windows System.Speech。其他系统可自行准备等价四片素材。素材应含中文语音无字幕视频及三份同名字幕片。

```sh
python tests/prepare_batch3.py <media>
node tests/browser_batch3.cjs <media>
node tests/browser_batch4.cjs <media>
node tests/browser_batch5.cjs <media>
```

prepare 会写示例、测试媒体的 `.studylens/batch3-real` 和日志，浏览器脚本会刷新 examples/screenshots；仅用于开发验收，不要指向真实用户素材。批次 3/4 覆盖实际解码、智能跳过、倍速、深链接、注入防护、窄屏滚动，批次 5 覆盖排序、音量、静音、全屏与单控制列。浏览器测试必须能解码 H.264 MP4。报告通过 file:// 打开并断网测试，HTTP 预览服务须支持 Range 才能可靠定位。

## CI

`.github/workflows/ci.yml` 在 ubuntu-latest、windows-latest、macos-latest 安装 Python 3.12、ffmpeg 和依赖，只运行 unittest，不下载模型、不跑浏览器。工作流配置存在不等于三个平台已通过；远端实际结果以 GitHub Actions 为准。
