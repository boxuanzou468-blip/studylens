# StudyLens 第三批交接

状态：第二批审查中的 4 项遗漏已修复；SPEC 第六节第 5 步（HTML 报告）已完成并验收。到此停下等待 Claude 审查，没有开始第 6、7 步的 SKILL.md、AGENTS.md 与正式 README。

## 审查入口与交付路径

- 实现：`<repo>\scripts\build_report.py`、`templates\report.html`
- 示例报告：`<repo>\examples\studylens-report.html`
- 真实媒体报告：`<media>\.studylens\batch3-real\studylens-report.html`
- 全部验收日志：`<media>\.studylens\logs\batch3\`
- 第二批代码备份：`<media>\.studylens\batch3-before\`

真实媒体测试目录独立放在原测试目录的隐藏工作区内，保留原来的四支素材和转录；没有把测试视频放进 Git 仓库。无 Git 提交或推送，没有新增生产依赖，没有安装新浏览器。

## 新增与修改

新增：

- `scripts/build_report.py`
- `templates/report.html`
- `tests/test_batch3.py`（11 项新增 Python 回归）
- `tests/prepare_batch3.py`（准备独立媒体与手写测试分析、生成报告）
- `tests/browser_batch3.cjs`（Playwright 离线浏览器验收）
- `examples/no-speech/profile.json`
- `examples/no-speech/manifest.json`
- `examples/no-speech/analysis/8def9b053b34c9ea.json`
- `examples/no-speech/library.json`
- `examples/studylens-report.html`
- `examples/screenshots/` 下 6 张截图
- `BATCH3_REVIEW.md`

修改：

- `scripts/validate.py`：推荐路径语义规则、独立警告等级；保留 `validate_file()` 的旧 errors-only API，新增 `inspect_file()` 返回错误和警告。
- `scripts/chunk.py`：标头显示完整精度的 `duration_sec`。
- `schema/library.schema.json`：允许无可学习内容时 learning_path 为空。存在非 skip 段落时，语义校验仍拒绝空路径。

需求文档和前两批审查文件保持原样。

## 4 项遗漏的修正

1. **推荐路径**：引用 skip 段落报错；同一 `(video_id, segment_index)` 重复引用也报错，即使 reason 不同也不能绕过。topic_index 仍允许索引 skip 段落。
2. **警告等级**：单段超过 480 秒警告；中间非 skip 段短于 20 秒警告，首尾段与 skip 例外；影片超过 600 秒且只有 1 段时另加警告。警告不改变成功退出码；例如 `PASS（2 个警告）`。仍按 Claude 指定的阈值执行，240 秒的单段不会仅因整片单段而报警。
3. **精确时长**：每次读 chunk 的标头新增 `时长 1234.567891 秒（最后一段 end 请填此值）`，不只保留三位小数，也不让 AI 从最后一个语音时间戳猜总时长。
4. **无语音约定**：独立 examples/no-speech 示例只有一段 `0→60`、label=skip、relevance=0、reason=`無語音內容，無法判斷`；learning_path 为空，topic_index 仍记录该段，统计为 total=60、recommended=0、saved=60，全部校验通过。适用于没有可用语音/字幕文本的情况；有同名字幕的静音测试视频仍可根据字幕分析。

## 报告实现

**生成前校验**：内部检查 profile、目录中每份 analysis、library 及其引用/统计。汇总所有错误后拒绝写入输出；已有报告保留，不会被失败的构建截断。警告单独打印。支持 `--data-dir` 和 `--output`，默认读取素材目录的 `.studylens/` 并输出素材根目录的 `studylens-report.html`。

**单文件与数据安全**：原生 HTML/CSS/JS，数据内嵌在 `script[type="application/json"]`；Python 把 `<` 转成字面 `\u003c`，另处理 `>`、`&`、Unicode 行分隔符。前端采用 `createElement`、`textContent`、`replaceChildren`，没有 innerHTML 或 eval 拼接 AI 文本。模板不引用 CDN、外部字体或脚本。

真实测试数据的一笔标题是：

```text
</script><img src=x onerror=alert(1)>
```

它显示为普通文字；浏览器内没有生成 img，没有 alert，没有额外 script 节点。HTML 解析单元测试也确认 JSON 可以完整还原此字符串。

**媒体路径**：输入 manifest 的媒体路径必须在素材目录内；拒绝绝对路径、冒号、反斜线和上级跳转。计算相对报告位置的路径，再在浏览器中对每一层使用 encodeURIComponent。已实际播放 `路径 空格#100%/中文 #100%.mp4`，不是只检查字符串。

**导航与浏览**：顶部目标、总时长/建议时长/节省时长、可点击学习路径；目录有摘要、相关度、四色迷你时间轴、标签文字和各段摘要/理由/知识点。支持标题、摘要、理由、知识点搜索；只看重点；按 topic_index 精确筛选段落；主题索引按钮可快速筛选。

**播放器与智能模式**：

- 点击段落或学习路径跳转播放；也可用原生播放器或自定义进度条定位。
- 自然播放进入 skip 才自动跳过，显示 3 秒提示及「回去看」。
- 内部自动 seek 和用户主动 seek 分开记录；手动选中的 skip 段直到离开之前不会再被跳走。
- speed 使用段落指定倍速，离开恢复用户基础速度；包含原生 ratechange 与页面基础速度选择的处理。
- 末尾 skip 可以跳到影片精确结束，不留在最后一毫秒造成重复跳过。
- 智能开关与主题使用 localStorage，所有读写包在 try/catch；存储被拒时仍可正常使用。
- error 事件显示「浏览器无法播放此格式」、文件相对路径和系统播放器观看提示；目录保持可用。文件缺失时也给出明确说明。
- 支持 `#v=<video_id>&t=<秒>`；「复制此刻链接」包含影片与当前秒数。剪贴板不可用时选中链接供手动复制。深链接默认定位但不自动播放。

事件处理参考浏览器的 [seeking](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/seeking_event) 和 [ratechange](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/ratechange_event) 说明；本批效果由实际媒体事件验收，不把事件文档当作运行证据。

## 实际运行的命令

```powershell
$repo = '<repo>'
$py = "$repo\.venv\Scripts\python.exe"
$media = '<media>'

# 准备真实媒体副本、手写分析与两个报告
& $py "$repo\tests\prepare_batch3.py" $media

# 生产构建入口的等价用法
& $py "$repo\scripts\build_report.py" "$repo\examples" --data-dir "$repo\examples"
& $py "$repo\scripts\build_report.py" "$media\.studylens\batch3-real"

# Python 回归
& $py -m unittest discover -s "$repo\tests" -v

# 浏览器验收：使用本机已存在的运行时与浏览器
$env:NODE_PATH = '<user>\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:STUDYLENS_BROWSER_EXECUTABLE = '<user>\AppData\Local\ms-playwright\chromium_headless_shell-1243\chrome-headless-shell-win64\chrome-headless-shell.exe'
& '<user>\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' "$repo\tests\browser_batch3.cjs" $media
```

后两条生产构建入口与准备脚本内部调用的是同一个 create_report 实现。浏览器包默认期待的缓存版本在本机不存在，因此通过测试专用环境变量指定已安装的 Chromium；没有下载浏览器，也没有禁用浏览器安全机制。Playwright 仅供开发验收，不是报告或生产脚本运行依赖。

## 实际验收结果

```text
Ran 46 tests
OK

# 原有四个正例 + 无语音示例三个文件
共检查 7 个文件，0 个错误，0 个警告

# 原有反例：预期非零退出
共检查 4 个文件，29 个错误，0 个警告

No broken requirements found.
```

浏览器 16 项检查全部通过，完整结果见 `browser-evidence.json`，实际命令输出见 `browser.log`。所有页面在 context.offline=true 下直接打开 `file://` 报告，没有使用本地 HTTP 服务：

| 实际操作 | 观测结果 |
|---|---|
| 浅色、深色、390px 手机截图 | 全部生成，手机没有横向溢出 |
| 搜索「闭卷」、只看重点、主动回忆主题、不存在关键词 | 对应片段和空结果正确 |
| 恶意 title | 文字完整显示；0 个弹窗、0 个注入 img，script 数始终为 2 |
| 点击语音片第二段 | currentTime≈24.08、paused=false、videoWidth=640、readyState=4 |
| 进入 speed 段 | playbackRate=1.75 |
| 离开 speed 段 | 恢复用户设置的 1.5，而不是 1 |
| 自然跨过 79 秒进入片尾 skip | 跳到 85.2 秒，ended=true，提示可见 |
| 点击回去看 | 回到约 79.3 秒并继续播放，没有再次自动跳走 |
| 手动设置实际媒体 currentTime 到 skip 内 | 原生 seeking/seeked 后继续在 79 秒区间播放 |
| 跳过提示计时 | 3 秒后自动消失 |
| 复制 24.5 秒链接后新页面打开 | 正确影片、currentTime=24.5、paused=true |
| 新页面智能开关 | 记住已开启状态 |
| 中文/空格/#/% 路径 | 真实解码 MP4，src 各层正确编码 |
| FFV1 AVI | 显示格式错误与文件路径，目录仍保留 |
| 强制 Storage 读写抛异常 | 页面和开关仍正常使用 |
| 整轮离线浏览 | 0 个外部 HTTP 请求，0 个页面 JS 错误 |

测试使用真实解码的 85.2 秒中文 TTS MP4、三个字幕短片副本、特殊路径 MP4，以及由 ffmpeg 生成的 FFV1 AVI。语音分析为根据已检查逐字稿手写的短分析；其他短片和恶意标题仅为界面/安全测试数据，不代表正式课程结论。

## 截图与录像

以下均为浏览器实际截图，已打开检查，修正了跳过提示按钮对比度及主题切换截图时机：

- 浅色：`<repo>\examples\screenshots\report-light.png`
- 深色：`<repo>\examples\screenshots\report-dark.png`
- 手机：`<repo>\examples\screenshots\report-mobile.png`
- 真实视频播放：`<repo>\examples\screenshots\real-playback.png`
- 自动跳过提示：`<repo>\examples\screenshots\smart-skip.png`
- 不支持格式：`<repo>\examples\screenshots\unsupported-format.png`

Playwright 录像保存在 `<media>\.studylens\logs\batch3\browser-recording\`（每页一个 .webm；文件名由 Playwright 生成）。`browser-evidence.json` 的逐项时间/倍速/播放状态记录可直接对应操作，不用仅凭静态截图推断播放成功。

**示例报告中的播放器错误是预期情况**：第二批 examples 的 240/360 秒是虚构元数据，未附视频，故截图展示文件无法读取的兜底；真实视频播放证据在 real-playback.png 和浏览器状态日志中，不能把示例静态页等同于实际播放通过。

## 限制与后续边界

- 本批仅实测 Windows Chromium 的 file:// 场景及 390px 模拟视口；没有声称完成真实手机、Safari/Firefox 或跨系统验收。
- 浏览器支持与封装名不完全等价；本批用 FFV1 AVI 真实触发 error，并不宣称所有 AVI/MKV 都一定无法播放。当前不进行格式转码。
- 分享链接定位本地报告中的时刻，不上传/托管视频；接收者需要同一份报告和视频目录，机器上的绝对文件路径可能不同。
- 剪贴板、自动播放、localStorage 仍受浏览器策略影响，界面提供选中复制、手动播放、无持久化运行的退路。
- 没有自然课程视频或长课程的新转录验收；仍沿用已知 TTS/字幕素材，仅验证网页行为与安全边界。
- 报告生成根据已扫描的 manifest 与 AI JSON 校验，AI 总结内容本身的质量仍需审查。分段警告不会被脚本擅自改写。

下一步请 Claude 审查本批。收到下一批指令后再进入第 6、7 步，不自动继续。
