# StudyLens

本仓库把本机学习影片整理成个性化目录、段落标签与离线 HTML。脚本不调用 LLM API；使用者当前的 AI agent 负责阅读逐字稿与分析。

执行影片整理任务时，请**完整依照本目录的 [SKILL.md](SKILL.md)**，先确认目标和程度，再逐片阅读、校验、汇总。脚本路径从该文件的实际位置解析，不能假定当前目录。

修改仓库代码时遵循用户给定批次范围；维护请求不是启动影片分析的指令。不要因为完成代码就自动提交 Git 或推送。

## Codex 安装位置

按当前 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)（核对日期 2026-10-21），用户技能目录为 `~/.agents/skills/`，仓库技能目录为 `.agents/skills/`，支持链接技能目录。把**整个** StudyLens 仓库放到其中的 `studylens/`，包括 scripts、schema、templates、requirements；不要只复制 SKILL.md，也不要搬运已创建的 .venv。

也可不安装，直接向 Codex 提供本仓库 SKILL.md 的绝对路径。正式文档使用当前 `.agents/skills` 位置，不以旧环境的 `.codex/skills` 缓存位置替代它。复制到新位置后由该位置首次建立自己的 .venv；未出现技能时重启 Codex。
