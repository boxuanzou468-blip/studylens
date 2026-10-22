# StudyLens 第四批交接

**状态：实现、文档与回归检查完成；Codex 全新对话已完成复用转录缓存、首片暂停后恢复的端到端验收。父对话追加离线播放定位复核通过；HTTP 预览服务的 Range 限制已实测并保留说明。等待 Claude 正式审查，Claude Code 侧仍由 Claude 独立验收。未建立 Git commit。**

## 已交付

- 修复模板可读性、窄屏回到播放器、profile 更新警告三项问题。
- 新增 `scripts/library_stats.py`，与最终校验器共享确定性的统计函数。
- 完成 `SKILL.md`、`AGENTS.md`、中文在前的双语 `README.md`、MIT `LICENSE`。
- 54 项 Python 测试通过；原有 16 项浏览器验收通过；新增 9 项窄屏滚动验收通过；SKILL 前置校验通过。
- 按要求创建了不继承本对话历史的新 Codex 对话，仅给出 SKILL.md 路径和一句影片整理请求；它先访谈，在用户授权合成答案后完成首片分析并暂停，再恢复完成其余三片与最终报告。

项目：`<repo>`

日志：`<media>\.studylens\logs\batch4\`

备份：`<media>\.studylens\batch4-before\`

## 文件变更

新增：

- `scripts/library_stats.py`
- `SKILL.md`
- `AGENTS.md`
- `README.md`
- `LICENSE`
- `tests/test_batch4.py`
- `tests/browser_batch4.cjs`
- `examples/screenshots/mobile-after-click.png`
- `BATCH4_REVIEW.md`

修改：

- `templates/report.html`：展开全部 HTML/CSS/JS；窄屏点击定位后滚回播放器，尊重 reduced motion。
- `scripts/common.py`：新增共享 `compute_library_stats()`。
- `scripts/validate.py`：新增 profile/analysis mtime 过期警告；统计校验复用共享函数。
- 重新生成 `examples/studylens-report.html` 与截图，以及专用测试目录中的报告。

`requirements.txt` 未增加生产依赖。Prettier 3.9.10 仅安装在工作区临时编辑副本的 `.format-tools/`，用于格式化模板，没有带入仓库或全局安装。原有批次文件和 SPEC 保留，没有提交/推送。

## 四项修正说明

1. **源码可读性**：模板 1536 行，最长行 126 字符，CSS 规则、声明及 JS 语句已展开。输出也保留可读格式，没有新增压缩器。格式化后重新跑了原有真实播放、跳过、倍速、深链接、路径编码与注入防护检查。
2. **移动/窄屏点击**：navigate 收到段落/学习路径等主动播放操作时，在宽度 ≤1050px 用 requestAnimationFrame 调用播放器 scrollIntoView；普通模式 smooth，prefers-reduced-motion 为 reduce 时 auto。初始加载和被动自动跳过不强制触发此滚动。1051px 不做额外强制滚动。
3. **目标可能更新警告**：inspect_file 对比 profile.json 和分析文件的 st_mtime_ns；profile 较新时报告「学习目标可能已更新，以下分析可能过期：…，若要依新目标重新标注请重跑分析」。单片验证、library 验证与报告构建都会提示；不改变成功退出码，不自动重写标签。mtime 只是保守启发式，不声称理解了目标内容。
4. **确定性统计**：library_stats 读取 manifest 和所有 analysis，逐份做结构/时长校验，缺失或非法时只报错，绝不输出部分统计。标准输出只有可嵌入 library.stats 的 JSON。must/normal 按原速，speed 除以倍速，skip 为零；总时长来自 manifest。校验器用同一个计算函数把关，避免两套公式漂移。

## SKILL 与文档

SKILL frontmatter 的 name 为 studylens，description 包含中英触发描述。主体覆盖：

- 从 SKILL.md 的实际位置解析绝对脚本路径，独立 .venv，Windows 与 macOS/Linux 指令；依赖缺失时执行安装，受到宿主限制时如实报告。
- 一次合并询问未提供的目录、具体目标、程度、可选预算/语言，以及既有结果复用选择；模糊目标最多再澄清一次。
- 字幕优先、后台转录、简短进度、本地模型优先与第三方镜像边界；按输出语言传 initial prompt。
- 逐支逐块读完、立即写分析并验证；已完成且目标未变的有效分析跳过；新目标重新标注不等于重新 ASR。
- 具体标题、内容摘要、纠正明显同音错字但不编造内容、reason 对应目标、按程度校准标签，不能整片无差别标红。
- 无可用文本时全片 skip 的约定；分段长度和旧目标警告尽量消除。
- 先修顺序、以 must 为主的路径、通过 Python 计算预算、stats 直接使用 library_stats 输出。
- 构建、打开报告，交付报告路径、三项时长和最该先看的三个片段。

README 含流程图、两个工具的安装说明、可复制请求、输出布局、恢复行为、隐私边界、已知限制和 MIT 授权。明确说明：文件保存在本机，但当前 AI agent 读取的文本可能进入其模型服务，不能误称所有 AI 分析都离线。截图为 report-light.png 和 smart-skip.png，没有额外制作非必需 GIF。

Codex 安装目录根据当前 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)核对为用户 `~/.agents/skills/` 和仓库 `.agents/skills/`，不是照旧环境缓存路径写 `.codex/skills`。Claude 安装路径和 `/studylens` 调用参考 [Claude Code 官方技能说明](https://code.claude.com/docs/en/skills)。LICENSE 作者为 StudyLens contributors。

## 实际命令与结果

```powershell
$repo = '<repo>'
$py = "$repo\.venv\Scripts\python.exe"
$media = '<media>'

& $py -m unittest discover -s "$repo\tests" -v
& $py '<user>\.codex\skills\.system\skill-creator\scripts\quick_validate.py' $repo
& $py "$repo\scripts\library_stats.py" "$repo\examples" --data-dir "$repo\examples"
& $py -m pip check

# 重新生成独立测试报告，然后实跑原有与新增浏览器检查
& $py "$repo\tests\prepare_batch3.py" $media
$env:NODE_PATH = '<user>\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:STUDYLENS_BROWSER_EXECUTABLE = '<user>\AppData\Local\ms-playwright\chromium_headless_shell-1243\chrome-headless-shell-win64\chrome-headless-shell.exe'
& node "$repo\tests\browser_batch3.cjs" $media
& node "$repo\tests\browser_batch4.cjs" $media
```

```text
Ran 54 tests in 2.431s
OK
Skill is valid!
{
  "total_sec": 600.0,
  "recommended_sec": 390.0,
  "saved_sec": 210.0
}
No broken requirements found.
PASS responsive scroll: 9 checks, including 1050/1051 boundary and reduced motion
```

新增单元测试验证：较新 profile 单片/library 警告、较旧 profile 无警告、构建与 CLI 的警告不阻断成功、统计完整性、从无关工作目录执行的纯 JSON 输出、坏/缺分析拒绝部分输出、无语音统计、小数和倍速计算。

浏览器新增检查覆盖 390/720/1050 像素的段落与路径点击，1051 像素不强制滚动，以及 390 像素普通 motion 与 reduced motion。测试包装原生 scrollIntoView 只记录参数，仍调用真实方法并检查播放器实际位置；不是用模拟返回值伪造滚动。手机截图在媒体 seek 完成并能解码后获取。

证据：

- `logs/batch4/unittest.log`
- `logs/batch4/skill-validation.log`
- `logs/batch4/example-stats.log`
- `logs/batch4/pip-check.log`
- `logs/batch4/browser-scroll.log`
- `logs/batch4/browser-scroll-evidence.json`（9 项、实际浏览器版本、滚动参数与位置）
- `logs/batch3/browser-evidence.json`（本次重跑的原有 16 项，0 JS 错误、0 弹窗、0 外部请求）
- `examples/screenshots/mobile-after-click.png`（390px 点击后播放器位于视口顶部）

## 独立 Codex 对话：端到端与暂停恢复实测

对话：**StudyLens 全新对话端到端验收**

threadId：`01a15fa3-9192-7060-8f75-baa039083c92`

该对话初始只收到以下请求，没有本对话历史、已有答案或预期分析：

```text
请完整读取 <repo>\SKILL.md。用 StudyLens 帮我整理 <media> 这个文件夹，我想学制定学习计划和复习方法。
```

它读取 SKILL、检查目录，识别四支视频与已有转录缓存，在个人化分析前先询问程度和可选时间预算。初始检查中，其 PATH 没找到 ffmpeg/ffprobe；本轮复用缓存，没有修复或重新验证该环境的转录工具发现能力。

### 授权与两轮执行

此前发送测试代答曾因缺少明确授权被自动审批拒绝；本次用户通过截图明确授权该测试对话使用合成答案及执行暂停/恢复，随后消息已成功发送。授权限于该测试对话、测试素材和补充本交接文档。以下内容是测试人设，不代表用户的真实程度。

第一条实际发送的答案：

```text
有基础：已经做过学习计划，但执行和复习效果不稳定。预算 2 分钟，输出简体中文。沿用已有逐字稿缓存，按这次的目标生成分析。先完成并校验第一支影片的分析就暂停，保留文件；我稍后再让你继续。
```

暂停轮次 `01a1617d-9ffa-75b3-a0b8-903490dde220` 建立 profile，目标为制定稳定执行的学习计划、改善复习方法与效果；程度 basic、预算 2 分钟、语言 zh-CN。它只完成并验证第一支「中文字幕.mp4」的分析，然后停下。该片目录式内容标为 speed 1.5，其余三片当时没有分析文件。

暂停后记录首片分析、全部四份转录、profile 和 manifest 的快照，再发送：

```text
继续，沿用刚才的学习目标、程度、预算和输出语言，完成剩余影片及最终报告。
```

恢复轮次 `01a1617f-1f78-73f2-81ac-ee64271117e7` 读取 profile 并校验已完成的首片，未重读首片转录或分块；逐片读取剩余内容，生成三份分析、library 和报告。它使用 library_stats.py 计算统计，通过 Python 计算路径预算，并校验各片及最终 library。

### 最终产物与独立核验

最终报告：`<media>\studylens-report.html`

| 检查项 | 实测结果 |
| --- | --- |
| 分析数量 | 四片齐全 |
| 首片分析恢复前后 | SHA-256、大小和修改时间均未改变 |
| 四份转录缓存 | 恢复前后均未改变 |
| profile | 恢复时未改写 |
| 媒体和字幕 | 大小、mtime 与 manifest 中的输入指纹一致 |
| 总时长 | 109.2 秒 |
| 按标签推荐时长 | 71.66666666666667 秒 |
| 节省时长 | 37.53333333333333 秒 |
| 学习路径 | 61 秒，符合 120 秒预算 |
| 标签分布 | must 3、normal 0、speed 2、skip 3 |
| 最终校验 | 六个文件，0 错误，退出码 0 |
| 报告内嵌数据 | 与通过校验的 profile、library、四份 analysis 完全一致 |

首片分析 SHA-256：`52d985ab27b7bfa4308c51a7a833b929e86fb1b806f40898bef66576e917c619`，大小 1240 字节，mtime_ns `1792637033713612900`。

最终报告 SHA-256：`2a60d0784c5625de3e08537f80b5e57ccb6fff4c380674eb2b971c598115ba61`。

最先推荐三个片段均来自「中文语音无字幕.mp4」：00:06–00:24 目标分解、00:24–00:47 持续排期与问题记录、00:47–01:07 复述练习与每周复习。开场与重复结尾为 skip，两个目录式字幕片段为 speed，英文片因重复概述为 skip；没有全部标成重点。

保留一个不同的分段警告：语音片目标分解段长 18 秒，短于建议 20 秒。它保留完整语义边界，没有伪造为无警告；合并校验日志显示两次，是同一问题分别在单片和 library 校验中报告。

### 播放定位：离线通过，HTTP 预览有限制

独立对话在 `http://127.0.0.1:8766/studylens-report.html` 的预览中可切换影片，但定位后从零开始，因此它没有把精确跳转声称为通过。

父对话随后对同一份最终报告进行真实 Chromium 复核：

- 直接以 file:// 打开，并设置浏览器离线：深链接定位到 47 秒；点击该片段后 currentTime 为 47.768611 且处于播放状态，seekable 为 `[0,85.2]`。
- 使用同一 HTTP 预览：深链接停在 0 秒，片段点击后为 0.767818，seekable 为 `[0,0]`。
- 对 HTTP 服务显式发送 `Range: bytes=100-199`，返回 200 和完整 679501 字节，没有 Content-Range 或 Accept-Ranges；服务标识为 SimpleHTTP/0.6 Python/3.12.14。
- 两种打开方式均无页面 JS 错误。

上述对照支持该预览服务不支持所需的 Range 定位。离线文件模式的定位已经实测通过，不能将 HTTP 预览结果推广为全部播放失败，也不能把离线复核说成是独立对话自行完成。此次未新增 HTTP 服务功能，预览服务限制仍需交接；使用本地浏览器直接打开报告，或使用支持 Range 的服务。

### 测试范围与证据

本轮验证的是**全新对话读取说明书、复用已有转录、受控暂停后恢复分析、生成报告**。没有重新安装依赖、重新扫描/ASR，也没有强杀进程；输入指纹经独立检查一致，不代表冷启动转录流程重跑通过。素材总长本就小于两分钟，因此预算计算通过，但不构成大素材严格预算取舍的压力测试。真实课程、跨系统、GPU 和非 Chromium 限制仍按 README 保留。

所有以下相对路径均位于 `<media>\.studylens\`：

- `logs/batch4/e2e-first-turn.json`：初始访谈；长 SKILL 输出按工具限制截断。
- `logs/batch4/e2e-paused-turn.json`：合成答案、首片分析与暂停记录。
- `logs/batch4/resume-before.json`：恢复前文件快照。
- `logs/batch4/e2e-completed-turn.json`：恢复、其余分析、统计、构建与交付记录。
- `logs/batch4/e2e-final-validation.log`：六文件最终校验。
- `logs/batch4/e2e-verification.json`：文件保持性、统计、预算及内嵌数据独立核验。
- `logs/batch4/e2e-playback-comparison.json`：离线/HTTP 播放对照与 Range 探测。
- `logs/batch4/e2e-file.png`、`logs/batch4/e2e-http-preview.png`：对应浏览器截图。

## 交接边界

Codex 侧本轮缓存复用及受控暂停/恢复验收已完成，可以交 Claude 正式审查；Claude Code 侧仍由 Claude 独立实测，本交接不替它声明成功。此次授权后仅执行测试对话、写入测试素材与补充本交接文档，没有新增产品代码变更，没有建立 commit 或推送。
