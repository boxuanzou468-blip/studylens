# StudyLens 发布记录

仓库：https://github.com/boxuanzou468-blip/studylens

可见性：PUBLIC。许可证：MIT。提交作者仅设置在本仓库，使用 GitHub 用户名与 noreply 隐私邮箱，保留全局 Gitee 作者设置。

## 发布前检查

初始 74 个待提交文件完成路径、邮箱和疑似凭据扫描，无发现；.venv、.studylens、影片与 __pycache__ 均被忽略。源码、示例截图和脱敏的开发记录已公开，没有用户课程媒体、转录缓存或虚拟环境。

## 远端 CI 及修正

首个 commit：a7169dd。首轮 [CI](https://github.com/boxuanzou468-blip/studylens/actions/runs/39732130351) 中 Linux 成功，Windows/macOS 的同一根路径比较测试失败，扫描结果为零片。

修复 commit：c49837c。scan() 在函数入口将根目录统一 expanduser().resolve()，避免 /var 与 /private/var 等路径别名导致已解析的媒体路径不被认为属于根目录。新增不含平台依赖的「入口/..」路径回归，比较规范化前后影片、字幕与 id，保留原有外部链接边界检查。

修复后本机测试：61 项，60 通过，1 项本地模型测试按预期跳过。随后 [三平台 CI](https://github.com/boxuanzou468-blip/studylens/actions/runs/39732402291) 全部 success：

| 平台 | 结果 |
| --- | --- |
| ubuntu-latest | success |
| macos-latest | success |
| windows-latest | success |

CI 使用 Python 3.12、ffmpeg 与当前 requirements；没有下载 Whisper 模型。这里验证的是脚本/字幕流水线，不代表三平台浏览器、GPU 或真实长课程都已验证。

README 已替换为真实 CI 徽章，移除待运行占位 SVG，并按实测范围更新中英文边界。文档更新会再次触发相同工作流，实时状态见仓库 Actions。仓库简介与 ai-agent、claude-code、codex、skill、whisper、learning、video 主题已设置。
