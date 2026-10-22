# StudyLens 第二批交接

状态：Claude 第一批审查的必修 1～3、建议 4～8 均已处理；SPEC 第六节第 3、4 步完成。本批自检通过，停下等待 Claude 审查，没有开始 HTML、SKILL.md、AGENTS.md 或正式 README。

项目：`<repo>`

素材：`<media>`

完整验收证据：`<media>\.studylens\logs\batch2\`

第一批实现备份：`<media>\.studylens\batch2-before\`

## 修改与新增文件

修改：

- `scripts/transcribe.py`：异常时间修正、VAD 默认开启、参数变更复用、自动字幕编码、下载提示、initial prompt、限流进度。
- `scripts/chunk.py`：紧凑时间戳、20～30 秒合并、6000 字符上限、目录时间范围。
- `scripts/check_env.py`：镜像/本地模型提示、GPU 官方说明链接；只提示，不改环境配置。
- `tests/test_pipeline.py`：缓存参数改变时的预期更新为复用，其余第一批回归保留。

新增：

- `schema/profile.schema.json`
- `schema/video_analysis.schema.json`
- `schema/library.schema.json`
- `scripts/validate.py`
- `tests/test_batch2.py`
- `tests/acceptance_batch2.py`
- `examples/profile.json`、`examples/manifest.json`、`examples/library.json`
- `examples/analysis/1826e5de3ff6b05b.json`
- `examples/analysis/df3a612a35031034.json`
- `examples/invalid/analysis-structure.json`
- `examples/invalid/analysis-timing.json`
- `examples/invalid/library-invalid.json`
- `examples/invalid/profile-invalid.json`
- `BATCH2_REVIEW.md`

`SPEC.md`、`BATCH1_CLAUDE_REVIEW.md`、`BATCH1_REVIEW.md` 均保留；未增加依赖、未创建 Git 提交或推送。第一批交接中的缓存与分块描述已由本文件更新。

## 8 项审查意见的处理

1. **零长与倒退时间**：`normalize_segments` 保留原始文本顺序，将倒退开始时间夹到前一段开始时间；零长/倒退结束补到最多 0.1 秒，在片尾无法补长时合入前一段；只有一段时利用片尾前的有效区间。每次只汇总一行修正段数。`check_segments` 继续严格验证；超出影片 0.25 秒以上仍报错。重叠的原始字幕可保留，AI 分析的重叠由新校验器检查。
2. **紧凑分块**：使用 `[MM:SS]`，一小时后 `[H:MM:SS]`，仅显示开始时间；尽量 20～30 秒一行，在至少 20 秒的句末或达到 30 秒时结束组。原文单段较长时不伪造细粒度时间。正文占比实测见下方，6000 字符硬上限保留，块目录显示起止范围。
3. **进度限流**：以已处理的媒体时间为准，阈值为 `max(影片时长 × 5%, 30 秒)`，即两种频率取更少输出的一种；另有开始、完成摘要。两小时 1500 段的模拟只输出 19 行进度。
4. **VAD**：默认开启 `vad_filter=True`，`--no-vad` 关闭；真实 TTS 影片已在开启 VAD 的情况下重新转录通过。已有缓存默认复用，要让旧结果采用 VAD 须显式 `--force`。
5. **缓存**：`device/compute_type` 不再进入参数 key；模型、语言、beam、VAD、prompt、字幕编码的变化会提示「参数与上次不同，若要重做请加 --force」，不自动重跑。文件指纹/字幕来源变化或结果缺失、损坏才自动重做。保留第一批 `version=1` 和全部原字段，旧缓存可以直接复用。
6. **编码**：默认依次尝试 UTF-8 BOM 兼容解码、带 BOM 的 UTF-16、GB18030；强制 `--subtitle-encoding` 时只使用指定编码，不偷偷回退。已检查 UTF-8、UTF-8 BOM、UTF-16 LE/BE BOM、GB18030、错误强制编码与不可解码数据。
7. **下载提示**：`check_env.py` 和转录失败信息提示手动设置 `HF_ENDPOINT=https://hf-mirror.com`，或 `--model <本地文件夹> --local-files-only`。说明这是第三方镜像，本批没有启用/测试镜像，也没有修改代理。GPU 提供 [faster-whisper 官方 GPU 说明](https://github.com/SYSTRAN/faster-whisper#gpu)，没有安装运行库。
8. **中文 prompt**：新增 `--initial-prompt`，默认 None，原样传入本地 Whisper。本批真实验收使用「以下是普通话的句子，使用简体中文和标点。」；它是提示，不保证字形、标点或识别完全正确，示例中「分步」仍可能识别为「分布」。

## Schema 与跨文件规则

三份 schema 使用 Draft 2020-12，限制未知字段、非空文本、合法标签、速度范围等。校验脚本通过 `iter_errors` 收集全部 schema 错误，再独立收集时间与引用错误；JSON 损坏时继续处理后续文件。实现依据 [jsonschema 官方验证接口](https://python-jsonschema.readthedocs.io/en/stable/validate/)。全部引用为本地 schema 内部引用，运行不访问网络。

**profile 字段**：必填 `video_folder`、`goals[]`、`level`；level 值为 `beginner/basic/advanced`，分别对应新手/有基础/进阶。可选 `time_budget_min`（正数）、`language`（例如 zh-CN）。profile 路径作为用户意图记录，不要求例子中的路径在机器上存在。

**analysis**：字段采用 SPEC。时长从扫描的 `manifest.json` 读取，没有给分析 JSON 增加一个可能冲突的 duration 字段。

- `start/end` 为有限数字秒数，不能用字符串或布尔值。
- 第一段 start 必须严格为 0；每段 end 必须大于 start。
- 相邻 end/start 误差最多 0.5 秒；超出时指出具体段号、空隙或重叠秒数、修复方向。
- 末段 end 与 duration_sec 误差最多 1 秒，同时任何 end 都不得超出实际时长。因此片尾容差允许少覆盖至多 1 秒，不允许超过时长。
- relevance 为 0～100 的 integer。
- label 仅 must/normal/speed/skip；speed 标签必须有 speed，范围 1.25～2.5；其他标签禁止 speed。
- 摘要、知识点与理由必填；「2～3 句摘要」和个人化判断属于语义要求，不用标点计数冒充质量验收。

**library 引用**：使用 `{video_id, segment_index}`，`segment_index` 从 **0** 开始。learning_path 每项另有必填 reason；topic_index 的值为引用数组。检查 manifest 与分析文件中的 video_id、段落索引、缺失/重复分析，以及被引用分析本身的合法性。

**stats 重算**：total_sec 为 manifest 所有影片时长之和；recommended_sec 为全部分析中 must/normal 原速时长，加 speed 时长除以倍速，skip 为零；saved_sec 为两者之差。与 learning_path 是否列出每个普通段落无关。统计容差为 0.01 秒，检查相减关系和重算结果，缺失或无效分析时明确报错，不假装完成完整统计验证。

## 正反例说明

`examples/` 是**虚构教学示例**，用来说明分析/汇总格式；不是对本机实际课程的识别结论。examples/manifest.json 中 240/360 秒时长和零大小指纹均为示例元数据，没有对应的真实视频，不能拿它直接跑转录。

两份分析都包含四种 label，摘要为两句，分别覆盖 240 秒和 360 秒。library 的统计为：总计 600 秒、建议 390 秒、省下 210 秒。

四份反例故意包含：错误结构和字段类型、开头未覆盖、5 秒空隙、10 秒重叠、超出片尾、越界速度、错误标签关联字段、错误 relevance、无效视频引用、越界段落索引、统计不一致、空目标及错误程度值。

## 实际执行命令与结果

完整复现：

```powershell
$py = '<repo>\.venv\Scripts\python.exe'
$repo = '<repo>'
$media = '<media>'
$model = '<user>\.cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots\536b0662742c02347bc0e980a01041f333bce120'
& $py "$repo\tests\acceptance_batch2.py" $media --model $model
```

该命令先验证旧缓存复用，再显式强制转录四支素材（VAD 开启、带中文 prompt），最后故意改动多个参数检查缓存仍原样复用。对生成的素材可安全重复运行；不针对个人课程目录。

主要子命令：

```powershell
& $py "$repo\scripts\check_env.py"
& $py -m unittest discover -s "$repo\tests" -v
& $py "$repo\scripts\transcribe.py" $media --model $model --language zh --local-files-only
& $py "$repo\scripts\transcribe.py" $media --model $model --language zh --local-files-only --initial-prompt '以下是普通话的句子，使用简体中文和标点。' --force
& $py "$repo\scripts\transcribe.py" $media --device cpu --compute-type int8 --no-vad --beam-size 1 --local-files-only
& $py "$repo\scripts\chunk.py" $media --video-id 7b331b1b7129b5e4
& $py "$repo\scripts\chunk.py" $media --video-id 7b331b1b7129b5e4 --chunk 1
& $py "$repo\scripts\validate.py" "$repo\examples\profile.json" "$repo\examples\analysis\1826e5de3ff6b05b.json" "$repo\examples\analysis\df3a612a35031034.json" "$repo\examples\library.json"
& $py "$repo\scripts\validate.py" "$repo\examples\invalid\analysis-structure.json" "$repo\examples\invalid\analysis-timing.json" "$repo\examples\invalid\library-invalid.json" "$repo\examples\invalid\profile-invalid.json"
& $py -m pip check
```

实际输出摘要：

```text
Ran 35 tests in 1.652s
OK

# VAD 真实转录
转录开始：85.2s，VAD=True
转录进度 42% (36.0/85.2s)
转录进度 79% (67.0/85.2s)
转录完成：8 段，影片 85.2s
完成 4，跳过 0，失败 0

# 改动参数后
SKIP 已完成；参数与上次不同，若要重做请加 --force
完成 0，跳过 4，失败 0

# 分块
块 1: 00:00–01:19 | 314 字符 | 内容 89%

# 正例
共检查 4 个文件，0 个错误

# 反例：预期退出码 1
共检查 4 个文件，29 个错误

No broken requirements found.
PASS 第二批：正例 4，反例 4；正文占比 83.59%；进度 19 行
```

四份转录在两次非强制复用检查中，`mtime_ns` 全部不变；改参检查没有加载模型。VAD 实跑仍遇到本机 cuBLAS 缺失，自动回退 CPU 完成。

错误消息节选：

```text
segments[0].end (60) ≠ segments[1].start (65)：中间有 5 秒空隙，请延长 segments[0] 或提前 segments[1]（容差 0.5 秒）
segments[1].end (120) ≠ segments[2].start (110)：重叠 10 秒，请缩短 segments[1] 或推迟 segments[2]（容差 0.5 秒）
learning_path[1].segment_index (99) 越界；影片 '1826e5de3ff6b05b' 只有 4 段，索引从 0 开始
```

完整命令参数、实际与预期退出码、指标保存在 `logs/batch2/acceptance-summary.json`。对应日志有 `environment.log`、`unittest.log`、`reuse-existing.log`、`transcribe-vad.log`、`reuse-changed-parameters.log`、`chunk-*.log`、`validate-positive.log`、`validate-negative.log`、`repair.log`、`progress-simulation.log`、`pip-check.log` 和各脚本 help 日志。反例退出码 1 是预期成功验收其拒绝行为，不是交付未通过。

## 使用校验器

正常运行时可直接：

```powershell
& $py "$repo\scripts\validate.py" "$media\.studylens\analysis\<id>.json"
& $py "$repo\scripts\validate.py" "$media\.studylens\library.json"
```

默认向上寻找最近的 manifest.json，library 使用 manifest 同级 analysis/。必要时传 `--manifest` 和 `--analysis-dir`，不确定类型可传 `--kind profile|video_analysis|library`；可一次提供多个文件。只读 JSON 和元数据，不触碰媒体、不修写 AI 分析。

## 保留限制与下一批边界

- 还没有自然课程/长课程的端到端实测；两小时的限流检查使用模拟段落，不是两小时真实 Whisper 推理。真实 Whisper 验收仍是第一批 85.2 秒 TTS 影片。
- 紧凑合并不表示无声间隙真的有讲话；精确时间和空隙需读原 transcript。正文 80% 目标已用典型短字幕达成；稀疏语音、很短片段、极小块上限不能保证相同比例。单条超过 30 秒的原字幕不会凭空按字数添加新时间。
- 自动解码是按顺序尝试可解码的编码，不保证识别所有混合/非标准编码；有歧义时使用强制参数。
- 原始文件仍采用大小/mtime 指纹；单影片中途失败仍从该影片开头续跑；同一素材目录不要多进程同时写入。
- Hugging Face 在线下载、第三方镜像、GPU 成功推理、macOS/Linux 没有新增实测；未更改网络或 GPU 配置。
- 按 Claude 意见延期：语言后缀字幕（影片.zh.srt 等）、MKV 内嵌字幕轨；正式 README 在后续批次记录。
- 语义摘要质量、标注是否适合用户、自然课程准确率仍需 AI 与实际素材验收，schema 通过不能代替。

本批范围到此结束。请 Claude 审查修复与数据约定；收到下一批指令后再进入 HTML 与后续 skill 工作。
