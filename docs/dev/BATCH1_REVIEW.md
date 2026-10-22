# StudyLens 第一批交接：仅 SPEC 第六节第 1、2 步

状态：实现及本机验收完成，停在第一批，等待 Claude 审查。没有开始 schema、分析 JSON、HTML 报告、SKILL.md、AGENTS.md 或正式 README。

项目：`<repo>`

测试素材（仓库外）：`<media>`

## 新增文件

| 文件 | 内容 |
|---|---|
| `.gitignore` | 排除 `.studylens/`、常见影片、`.venv/`、`venv/`、`__pycache__/` 等 |
| `requirements.txt` | faster-whisper、jsonschema，以及实测必需的 PyAV 兼容约束 |
| `scripts/common.py` | UTF-8 控制台/JSON、原子写入、路径边界、ffprobe、输入指纹 |
| `scripts/check_env.py` | Python ≥3.10、ffmpeg/ffprobe、依赖及 PyAV 兼容检查、CUDA 可见设备诊断 |
| `scripts/scan.py` | 递归扫描、稳定 id、时长、音轨、同名字幕、manifest |
| `scripts/transcribe.py` | SRT/VTT/ASS 解析、Whisper 本地转录、进度、GPU 自动选择和 CPU 回退、按影片续跑 |
| `scripts/chunk.py` | 一次读一支影片，默认 6000 字符上限，目录及指定块输出 |
| `templates/.gitkeep`、`schema/.gitkeep`、`examples/.gitkeep` | 仅目录骨架 |
| `tests/test_pipeline.py` | 16 项回归检查，包含真实 ffmpeg/ffprobe 和 CLI 字幕流程 |
| `tests/create_fixtures.ps1` | 生成三种字幕影片及 Windows 中文 TTS 无字幕影片 |
| `tests/acceptance.py` | 可复现的第一批完整验收；日志写到素材目录的 `.studylens/logs/` |
| `BATCH1_REVIEW.md` | 本交接说明 |

保留原来的 `SPEC.md`，没有修改需求文档。已执行 `git init`，没有创建提交，也没有推送。

## 实际执行命令

由于本机 Python 不在 PATH，使用已有运行时创建项目专用虚拟环境：

```powershell
& '<user>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv '<repo>\.venv'
& '<repo>\.venv\Scripts\python.exe' -m pip install -r '<repo>\requirements.txt'
& '<repo>\tests\create_fixtures.ps1'
```

最终完整验收命令：

```powershell
$py = '<repo>\.venv\Scripts\python.exe'
$repo = '<repo>'
$media = '<media>'
$model = '<user>\.cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots\536b0662742c02347bc0e980a01041f333bce120'
& $py "$repo\tests\acceptance.py" $media --model $model --force-first
```

`acceptance.py` 实际启动的每一条 Python 命令及退出码都保存在：

`<media>\.studylens\logs\acceptance-summary.json`

展开后的主要命令：

```powershell
& $py "$repo\scripts\check_env.py"
& $py -m unittest discover -s "$repo\tests" -v
& $py "$repo\scripts\scan.py" $media
& $py "$repo\scripts\transcribe.py" $media --model $model --language zh --local-files-only --force
& $py "$repo\scripts\transcribe.py" $media --model $model --language zh --local-files-only
& $py "$repo\scripts\chunk.py" $media --video-id 7b331b1b7129b5e4
& $py "$repo\scripts\chunk.py" $media --video-id 7b331b1b7129b5e4 --chunk 1
& $py "$repo\scripts\chunk.py" $media --video-id 7b331b1b7129b5e4 --max-chars 128
& $py -m pip check
```

## 实际结果与输出

环境：Windows，Python 3.12.14，faster-whisper 1.2.1，CTranslate2 4.8.3，PyAV 16.1.0，jsonschema 4.26.0。ffmpeg 与 ffprobe 均在 PATH。

```text
Ran 16 tests in 1.247s
OK
```

| 影片 | 时长 | 来源 | 转录段数 |
|---|---:|---|---:|
| 中文字幕.mp4 | 8.000 秒 | 同名 SRT | 2 |
| 样式字幕.mp4 | 8.000 秒 | 同名 ASS | 2 |
| 英文字幕.mp4 | 8.000 秒 | 同名 VTT | 2 |
| 中文语音无字幕.mp4 | 85.200 秒 | 实际 Whisper small 推理 | 8 |

中文语音由 Windows System.Speech 的中文声音生成，经 ffmpeg 合成 H.264/AAC MP4；该影片旁没有同名字幕。原始 TTS 文本保留在 `中文语音-原文.txt`，没有作为 Whisper 输入。

首轮：

```text
GPU 无法运行，重试 CPU: Library cublas64_12.dll is not found or cannot be loaded
DONE whisper: 8 段
完成 4，跳过 0，失败 0
```

第二轮：

```text
[1/4] 中文字幕.mp4
  SKIP 已完成且输入、参数未变化
[2/4] 中文语音无字幕.mp4
  SKIP 已完成且输入、参数未变化
[3/4] 样式字幕.mp4
  SKIP 已完成且输入、参数未变化
[4/4] 英文字幕.mp4
  SKIP 已完成且输入、参数未变化
完成 0，跳过 4，失败 0
```

额外核验四份转录文件的 `mtime_ns` 均未变化，第二轮没有改写结果，也没有加载模型。

真实转录节选：

```text
[00:00:00.000 --> 00:00:06.000] 大家好,今天我们学习如何制定有效的学习计划。
[00:00:06.000 --> 00:00:15.000] 首先,要明确自己最想掌握的知识,把一个大目标拆成几个小目标。
[00:01:07.000 --> 00:01:19.000] 今天的重点是明确目标,分布练习,及时复习。希望大家都能找到适合自己的学习方法。
```

注意最后一段把原文「分步练习」识别为「分布练习」。TTS 规范化字符相似度为 98.78%，只用于粗略核对这段合成语音，不是自然课程识别准确率。

默认 6000 字符得到 1 块（538 字符）；用 128 字符上限得到 7 块。另用超过两万字符的合成逐字稿检查多块上限和无丢字。

```text
No broken requirements found.
PASS 四支素材、真实语音转录、续跑、分块；TTS 字符相似度 98.78%
```

完整日志均在 `<media>\.studylens\logs\`：

- `environment.log`、`unittest.log`、`scan.log`
- `transcribe-first-final.log`、`transcribe-resume.log`
- `chunk-index.log`、`chunk-text.log`、`chunk-small.log`
- `pip-check.log`、`acceptance-summary.json`

早期失败的 tiny 下载和兼容性排查日志也留在该目录；最终结论以以上 final/resume/summary 文件为准。

## 本批实现取舍与数据约定

1. 默认递归；`--no-recursive` 只扫描顶层。支持 MP4、MKV、MOV、AVI、WebM、M4V、WMV、FLV、MPEG、MPG，扩展名不区分大小写；实际能否解码取决于文件编码和后端支持。跳过隐藏目录、`.studylens/`、外部文件链接；探测失败会清楚报错并使扫描非零退出。
2. id 为相对路径 UTF-8 的 SHA-256 前 16 位。同路径在重复扫描中稳定，移动整个素材目录不改变 id；改名或调整相对目录会改变 id。
3. 字幕以完整同名 stem 匹配，不猜测语言后缀；同时存在时优先 SRT → VTT → ASS。坏字幕明确报错，不静默改走 Whisper。默认 UTF-8/UTF-8 BOM；旧编码可显式指定 `--subtitle-encoding gb18030`。
4. `.studylens/manifest.json` 含 `version=1`、`videos[]`、`errors[]`。每片记录 `id/path/filename/duration_sec/has_audio/fingerprint/subtitle/subtitle_fingerprint`；全部路径相对素材根目录，以 `/` 分隔。
5. `.studylens/transcripts/<id>.json` 含 `version/status/video_id/duration_sec/source/subtitle_path/language/device/model/cache_key/input_identity/segments[]`。`source` 为 `subtitle/whisper/no_audio`；每条原始转录为 `start/end/text`，秒数可以有小数。后续 schema 的对象是 AI 分析，原始转录没有冒充分析格式。
6. 续跑粒度是整支影片；输入指纹采用文件大小和纳秒修改时间，另纳入字幕路径、时长及转录相关参数。输入过期要求重扫，重扫后旧转录会被拒用。损坏 JSON、段落越界、来源/状态错误会重做。指纹不是内容哈希；不覆盖「人为同时伪造大小和修改时间」的情况。多个进程不要同时写同一素材目录。
7. 完整 JSON 原子替换；中断时保留已完成影片。本片尚未完成则下次从该影片开头重做。逐字稿不要求填满静音间隙；后续 AI 分析的完整覆盖是第 3 步校验器的工作。没有字幕且没有音轨时写出空逐字稿和 `no_audio`，不能凭空推测画面内容。
8. GPU 自动检测以 CTranslate2 可见 CUDA 设备为准；实际推理遇到 CUDA/cuBLAS/cuDNN 等错误，auto 模式明确报错并回退 CPU。显式 `--device cuda` 不隐藏失败；网络/普通模型错误不伪报为 GPU 错误。支持 `--device cpu`，默认 CUDA float16 / CPU int8。
9. `chunk.py` 默认只打印块目录，AI 用 `--chunk N` 一块一块读取。每块最多约 6000 字符，实际实现为严格上限（含时间戳和换行，不含 CLI 元信息标题）。单条字幕太长时优先标点断开，但沿用该条原始时间范围，不用字数捏造语音对齐。
10. 转录进度即时 flush；执行 agent 可将命令放后台并查看输出。本批用执行工具的后台会话完成长任务，未增加平台专属的后台进程管理依赖。

## 已知限制与环境问题

- 首次尝试下载 tiny 时 Hugging Face 出现 SSL/连接中止；未关闭证书校验、未修改代理配置。随后找到本机已有完整 small 缓存，用本地路径与 `--local-files-only` 完成验收。首次在线模型下载在此机器仍未通过，完整离线转录已通过。
- 本机能检测到 1 个 CUDA 设备，但缺少可加载的 `cublas64_12.dll`。本批证明 CPU 转录和 GPU 故障自动回退，未证明 GPU 成功推理，也未安装/修改 GPU 驱动或 CUDA。上游 GPU 运行库要求见 [faster-whisper 官方说明](https://github.com/SYSTRAN/faster-whisper#gpu)。
- 初装 PyAV 19.0.2 时实跑出现 `open() got an unexpected keyword argument 'metadata_errors'`。增加 `av>=11,<17` 约束，实测 PyAV 16.1.0 可运行；没有为此引入额外的业务依赖。
- 用的是合成语音和测试字幕，尚无自然课程视频；口音、噪音、多人、多语种、超长课程和各容器编码的识别表现未验收。
- 仅在本机 Windows/Python 3.12 验收。路径采用 pathlib、文本采用 UTF-8，但 macOS/Linux 与其他 Python 版本尚未实机验证。中文 TTS 素材生成脚本仅供 Windows 验收，生产脚本不依赖 System.Speech。
- 本批没有 LLM API 调用、分析标注、全影片分析覆盖校验、HTML 播放器或 agent skill 端到端验收。

## Claude 审查入口

请先读本文件，再读 `scripts/` 的实现及 `tests/test_pipeline.py`。如需复现，用上面的完整验收命令；会重做四支生成素材的转录，随后检查第二轮全跳过。

第 3 步开始前建议确认上述 manifest/transcript 字段约定；后续 `validate.py` 可直接用 `duration_sec` 检查 AI 分析的段落完整覆盖。等待审查结果，不自动继续下一批。
