# StudyLens 第五批交接

**状态：A～D 的实现、整理和本机回归完成，等待 Claude 最终审查。没有创建 Git commit、GitHub 仓库或推送。三平台 CI 已配置，远端尚未运行；徽章明确显示待首次运行。**

本文件与历史审查统一保存在 `docs/dev/`。`<repo>` 表示工具根目录，`<media>` 表示专用测试素材目录。源码按完整目录使用，不能只复制 SKILL.md。

## 13 项处理结果

| 项目 | 修改及验证 |
| --- | --- |
| 1 摘要不混入流程 | SKILL 明确 summary/reason 只写内容及其与目标、程度的关系，不提转录、缓存、字幕处理、预算计算等执行过程；执行限制另在交付说明写。本批按要求修说明书，没有追溯改写第四批的历史分析证据。 |
| 2 同音错字 | 加入「分布练习→分步练习」示例，并要求以按步骤练习的上下文为证；实际讲分布学习时不得机械替换。只纠正分析表述，不更改原 transcript。 |
| 3 短片警告 | 仅 duration ≥180 秒才检查中间非 skip 段小于 20 秒的警告；179.999/180 边界覆盖，过长段落及单段长片警告保持。 |
| 4 警告去重和短路径 | inspect_file 给出一致的 `analysis/<id>.json：…`；CLI 在同一轮分析+library 中按素材根目录及警告去重，builder 同样去重。不同行为独立命令仍会各自报告，不使用跨运行缓存隐藏问题。测试正反文件顺序、构建输出及不同素材同名文件，避免误吞独立警告。 |
| 5 相关度排序 | 默认 relevance 降序，同分保留输入顺序；提供原始顺序切换，筛选保持选定排序。无深链接时也默认选择最高相关度影片；深链接仍优先。 |
| 6 单套控制列 | 移除 video 原生 controls，保留自订进度/播放/速度，补音量、静音与全屏。全屏包含整个播放器面板，仍用同一控制列；音量状态双向同步。全屏拒绝时显示退路提示，有 webkitEnterFullscreen 兼容分支，但未声称 Safari 已测。 |
| 7 中文界面 | LOCAL LEARNING NOTES 改为「本地学习笔记」。 |
| 8 根目录和脱敏 | SPEC 及历史 BATCH 审查/交接统一移到 docs/dev/，README 底部链接开发记录；本机工具、素材、用户、工作区路径改为占位符，保留外部 URL。第五批交接也放在这里。截图中的分享输入暂时显示通用本地路径，仅用于截图脱敏，截图后恢复其真实值。 |
| 9 素材脚本 | create_fixtures.ps1 的 OutputFolder 改为必填参数，取消个人 D 盘默认值。 |
| 10 测试说明 | 新增 tests/README.md，分别说明纯本地单元测试、ffmpeg 集成、Playwright/Chromium 浏览器验收和可选本地 Whisper 模型测试。 |
| 11 三平台 CI | 新增 .github/workflows/ci.yml：ubuntu-latest、windows-latest、macos-latest，Python 3.12，安装 ffmpeg 和 requirements，离线模型模式，unittest discovery。无本地模型时对应测试自动跳过，CI 不下载模型。没有远端运行结果，README 保留 macOS/Linux 未实测边界。 |
| 12 README | 中英说明 HTTP 预览需 Range；否则直接在本地浏览器打开 HTML。加上可点击 CI 待运行徽章，指向实际工作流；仓库身份未定，未编造 OWNER/REPO，也不显示伪造 passing。发布时将 docs/ci-status.svg 替换为该仓库 GitHub Actions 实时徽章。 |
| 13 外链 | README、AGENTS 外部链接全部 HTTP GET 200；OpenAI 锚点存在。Claude 旧锚点 choose-where-skills-load 不存在，改为 where-skills-live 后复验存在。请求使用普通 User-Agent、正常证书校验。 |

## 文件变化

产品修改：`SKILL.md`、`scripts/validate.py`、`scripts/build_report.py`、`templates/report.html`。

开发/文档：`README.md`、`tests/README.md`、`tests/create_fixtures.ps1`、`tests/test_batch3.py`、`tests/test_batch4.py`、`tests/test_pipeline.py`、新增 `tests/test_batch5.py`、新增 `tests/browser_batch5.cjs`、已有 browser_batch3/4 的截图路径脱敏与格式化、`.github/workflows/ci.yml`、`docs/ci-status.svg`、`docs/dev/` 历史记录与证据。

重新生成 `examples/studylens-report.html`、无语音示例数据，以及浅色/深色/手机、真实播放/跳过/不支持格式、窄屏滚动和新增控制列截图。README 使用的浅色与跳过截图已更新。无生产依赖变化；Prettier 沿用仓库外临时工具，不带入生产目录。

## 实际验证

- **Python：60 项，59 通过，1 自动跳过**。跳过的是明确需 STUDYLENS_TEST_MODEL 的可选本地模型烟雾测试。本次没有设置该变量，没有下载/重复跑 Whisper。
- ffmpeg/ffprobe 真实字幕扫描→转录→恢复→失效检查测试已运行成功。Windows WinGet 链接需解析到实际 bin，测试进程临时加 PATH；没有修改系统 PATH。
- **浏览器：16 项原有回归 +9 项窄屏滚动 +11 项新增检查，全部通过**。真实 Chromium、本地 file://、离线执行，真实 MP4 解码与定位。新增检查包括相关度排序/原序/筛选、唯一控制列、音量静音与原生状态同步、实际进入和退出全屏、拒绝时提示、中文标题、390/720/1050 宽度无横向溢出，以及无 JS 错误/外部 HTTP 请求。
- 同步回正式目录后，第四批四片产物共六份 JSON 重新校验：0 错误、0 警告；使用新模板重建素材根目录的最终报告成功，原 18 秒警告不再出现。
- SKILL quick_validate 与 pip check：通过。
- CI YAML 解析、三个 runner matrix、公开文档相对文件链接检查：通过。**这不是远端 CI 执行证据。**
- 开发记录重新检查：未发现个人 Windows 绝对路径或 Administrator 字段；保留了原有外部资料链接。
- 目视检查已更新的浅色与 390px 控制列截图，布局可用。示例 HTML 只有演示元数据，不附真实课程媒体，缺文件提示是预期示例行为；实际媒体解码证据来自专用测试素材。

复现命令（先准备 tests/README.md 指定的开发环境和专用素材）：

```sh
python -m unittest discover -s tests -v
python tests/prepare_batch3.py <media>
node tests/browser_batch3.cjs <media>
node tests/browser_batch4.cjs <media>
node tests/browser_batch5.cjs <media>
```

### 外链检查

| URL | HTTP | 章节锚点 |
| --- | --- | --- |
| https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills | 200 | 存在 |
| https://code.claude.com/docs/en/skills | 200 | 不适用 |
| https://code.claude.com/docs/en/skills#where-skills-live | 200 | 存在；已修复旧锚点 |
| https://hf-mirror.com | 200 | 不适用；这里只检查可访问，不代表镜像下载或服务可信度验收 |

检查时间为本批执行时；外部页面后续可能变化。

### 证据位置

公开、已脱敏证据：

- [单元测试日志](batch5-evidence/unittest.log)
- [浏览器验收摘要与新增检查](batch5-evidence/browser-results.json)
- [外部 HTTP 与锚点结果](batch5-evidence/external-links.json)
- [390px 控制列截图](../../examples/screenshots/release-controls-mobile.png)
- [桌面控制列截图](../../examples/screenshots/release-controls.png)

完整运行日志留在 `<media>/.studylens/logs/batch3/`、`batch4/`、`batch5/`；第五批覆盖前的源文件备份在 `<media>/.studylens/logs/batch5/source-before/`。这些含本机运行路径的原始日志不收入公开仓库。

## 发布前仍需用户决定

GitHub 仓库名称、公开范围和首个 commit 作者仍由用户决定；本批不创建仓库、不 commit、不推送。确定仓库身份并获准发布后，才能安装该身份对应的实时 CI 徽章并获得远端三平台运行结果。Claude 最终审查通过前，不宣称已发布或三平台运行成功。真实长课程、GPU 成功推理、Safari/Firefox、真实手机等边界保持 README 说明。
