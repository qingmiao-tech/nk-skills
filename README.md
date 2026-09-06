# nk-skills

`nk-skills` 当前发布四个技能：

- `nk-session-distiller`
- `nk-wechat-chat-archive`
- `nk-wechat-publish-archive`
- `nk-wechat-publish-register`

| 技能 | 用途 | 典型输出 |
|------|------|----------|
| `nk-session-distiller` | 长会话沉淀与 handoff | Obsidian 复盘、项目 handoff、会话证据包 |
| `nk-wechat-chat-archive` | 微信 4.x Windows 聊天记录归档 | 本机工具准备、月度 Markdown、图片、增量续档、每日简报 |
| `nk-wechat-publish-archive` | 公众号发布前物料归档 | 发布稿、封面图、列表摘要、公众号 HTML、动态相关文章 |
| `nk-wechat-publish-register` | 公众号发布后正式链接登记 | 公众号文章库、发布索引、草稿和发布稿元数据回写 |

## 一句话安装

最简单的方式是把下面这句话直接发给你的 Codex、Claude Code 或其他支持 Skills 的 Agent，让它代你安装：

```text
请帮我安装这个 Skills 仓库：git@github.com:qingmiao-tech/nk-skills.git
```

如果你的 Agent 不能使用 SSH，也可以发 HTTPS 地址：

```text
请帮我安装这个 Skills 仓库：https://github.com/qingmiao-tech/nk-skills.git
```

如果只想安装单个技能，可以直接把对应话术发给 Agent：

```text
安装技能 nk-session-distiller：https://github.com/qingmiao-tech/nk-skills/tree/main/skills/nk-session-distiller
安装技能 nk-wechat-chat-archive：https://github.com/qingmiao-tech/nk-skills/tree/main/skills/nk-wechat-chat-archive
安装技能 nk-wechat-publish-archive：https://github.com/qingmiao-tech/nk-skills/tree/main/skills/nk-wechat-publish-archive
安装技能 nk-wechat-publish-register：https://github.com/qingmiao-tech/nk-skills/tree/main/skills/nk-wechat-publish-register
```

安装后，可以把下面这句话直接发给 Agent：

```text
请读取 nk-wechat-chat-archive，把我 Windows 微信 4.x 中指定聊天从上次截止点归档到指定日期，按月份保存为本地 Markdown，包含可用图片，并生成价值过滤和每日简报。所有聊天数据和密钥只在本机处理。
```

如果只需要公众号发布工作流，建议同时安装这两个技能：

```text
请帮我安装公众号发布工作流这两个技能：nk-wechat-publish-archive（https://github.com/qingmiao-tech/nk-skills/tree/main/skills/nk-wechat-publish-archive）和 nk-wechat-publish-register（https://github.com/qingmiao-tech/nk-skills/tree/main/skills/nk-wechat-publish-register）
```

手动安装全部技能时，在 PowerShell 中执行：

```powershell
$tmp = Join-Path $env:TEMP "nk-skills-install"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
git clone --depth 1 git@github.com:qingmiao-tech/nk-skills.git $tmp
$dest = Join-Path $env:USERPROFILE ".codex\skills"
New-Item -ItemType Directory -Force $dest | Out-Null
foreach ($skill in @("nk-session-distiller", "nk-wechat-chat-archive", "nk-wechat-publish-archive", "nk-wechat-publish-register")) {
  Copy-Item (Join-Path $tmp "skills\$skill") $dest -Recurse -Force
}
```

安装后，Codex CLI 会在下面路径读取技能：

```text
%USERPROFILE%\.codex\skills\nk-session-distiller
%USERPROFILE%\.codex\skills\nk-wechat-chat-archive
%USERPROFILE%\.codex\skills\nk-wechat-publish-archive
%USERPROFILE%\.codex\skills\nk-wechat-publish-register
```

如果目标 Agent 使用 `.agents\skills`，把上面命令里的 `.codex\skills` 改成 `.agents\skills` 即可。

只安装公众号发布工作流时，可以只复制这两个技能：

```powershell
$tmp = Join-Path $env:TEMP "nk-skills-install"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
git clone --depth 1 git@github.com:qingmiao-tech/nk-skills.git $tmp
$dest = Join-Path $env:USERPROFILE ".codex\skills"
New-Item -ItemType Directory -Force $dest | Out-Null
foreach ($skill in @("nk-wechat-publish-archive", "nk-wechat-publish-register")) {
  Copy-Item (Join-Path $tmp "skills\$skill") $dest -Recurse -Force
}
```

## nk-session-distiller（会话沉淀助手）

`nk-session-distiller` 用于判断 Codex、Claude Code、Hermes 或飞书里的长期会话是否值得沉淀，并整理成可复用文档。它适合这些场景：

- 会话太长，需要跨会话继续。
- 想把当前聊天整理成 Obsidian 复盘或项目 handoff。
- 需要从 Codex JSONL、Claude Code 记录、Hermes/飞书文本里提取关键事实、命令和风险线索。
- 想先判断一段会话值不值得沉淀，再决定写正式知识库文档、轻量 handoff 或跳过。

处理 Codex JSONL 时，可以先生成会话证据包：

```powershell
python ".codex/skills/nk-session-distiller/scripts/extract_codex_session.py" `
  --input "C:/Users/Administrator/.codex/sessions/YYYY/MM/DD/rollout-xxx.jsonl" `
  --output "10.Hermes协同/会话记录/_tmp/session-digest.md"
```

常见输出目录包括：

- `09.经验沉淀/AI工作流复盘/`
- `09.经验沉淀/项目案例库/`
- `10.Hermes协同/会话记录/YYYY/`
- 项目内的 `docs/ai-handoff/`

更多评分规则、拆分规则和模板见 [`skills/nk-session-distiller/SKILL.md`](./skills/nk-session-distiller/SKILL.md)。

## nk-wechat-chat-archive

`nk-wechat-chat-archive` 用于把微信 4.x Windows 聊天记录归档到 Obsidian Markdown。它适合这些场景：

- 整理微信群或单聊记录，按月份生成 Markdown。
- 从本机已登录微信开始，准备固定版本工具、私有数据库缓存和聊天 JSON。
- 从上次精确截止时间继续归档，并验证旧月份没有被意外改写。
- 从本地 `.dat` 附件解密图片，并写入归档目录的 `assets/`。
- 对完整归档做价值过滤，按群类型或自定义关键词生成精华归档和每日简报。

这个技能只处理用户有权访问的本机数据，不上传聊天正文、数据库、密钥或图片。当前完整工具链只支持 Windows 微信 4.x；微信 3.x、macOS、移动端备份、企业微信和云端直接获取不在已验证范围内。

首次使用可以让脚本准备固定版本的外部工具和隔离 Python 环境：

```powershell
python ".codex/skills/nk-wechat-chat-archive/scripts/bootstrap_wechat_archive_tools.py" `
  --tools-dir ".tmp/wechat-chat-archive/tools" `
  --install-deps
```

技能支持三种入口：

1. 只有聊天 JSON：使用 `--skip-images` 生成纯文本归档。
2. 已有本技能导出的聊天 JSON、图片密钥配置和附件：直接生成包含图片的月度归档。
3. 只有本机已登录微信：依次完成工具准备、聊天导出、归档和验收。

从当前登录账号导出聊天：

```powershell
& ".tmp/wechat-chat-archive/tools/.venv/Scripts/python.exe" `
  ".codex/skills/nk-wechat-chat-archive/scripts/export_wechat_chat.py" `
  --wechatauto-repo ".tmp/wechat-chat-archive/tools/wechatauto-replica" `
  --db-root "E:/path/to/xwechat_files" `
  --workdir ".tmp/wechat-chat-archive/private-cache" `
  --chat "<群名或联系人>" `
  --output ".tmp/wechat-chat-archive/target-chat.json" `
  --image-config ".tmp/wechat-chat-archive/private-cache/image-config.json" `
  --through "2026-08-31"
```

完整图片归档：

```powershell
python ".codex/skills/nk-wechat-chat-archive/scripts/archive_wechat_v4_chat.py" `
  --chat-json ".tmp/wechat-chat-archive/target-chat.json" `
  --wechat-base "E:/path/to/xwechat_files/<wxid>_<suffix>" `
  --wechatauto-repo ".tmp/wechat-chat-archive/tools/wechatauto-replica" `
  --image-config ".tmp/wechat-chat-archive/private-cache/image-config.json" `
  --output "path/to/local-knowledge-base/wechat/<聊天名>"
```

归档完成后，可以继续生成精华归档和每日简报：

```powershell
python ".codex/skills/nk-wechat-chat-archive/scripts/filter_wechat_archive.py" `
  --archive-dir "path/to/local-knowledge-base/wechat/<聊天名>" `
  --profile learning `
  --daily-digest
```

完整的本机导出、日期截断、增量合并、历史哈希保护和验收命令见 [`skills/nk-wechat-chat-archive/SKILL.md`](./skills/nk-wechat-chat-archive/SKILL.md)。首次配置和故障定位见 [`references/toolchain.md`](./skills/nk-wechat-chat-archive/references/toolchain.md)，增量续档见 [`references/incremental-workflow.md`](./skills/nk-wechat-chat-archive/references/incremental-workflow.md)。

## 公众号发布工作流

公众号发布工作流分两步：

1. `nk-wechat-publish-archive`：发布前生成物料，把 Obsidian 草稿复制到发布目录，生成封面、列表摘要、微信公众号 HTML 和动态 `相关文章`。
2. `nk-wechat-publish-register`：手动在公众号后台发布后，同步正式文章信息，回写正式链接、发布时间、摘要和封面等信息。

两个技能目录都已经内置所需脚本，方便单独分享安装：

```text
skills/nk-wechat-publish-archive/scripts/
skills/nk-wechat-publish-register/scripts/
```

内置脚本包括发布归档入口、发布包生成、封面生成、后台文章同步、配置加载和示例配置。已有本地 `00.系统配置/wechat-cover-summary-tool/` 的用户可以继续使用原目录；新安装分享版时不需要额外复制这套工具目录。

## 发布目录约定

默认按 Obsidian 知识库中的年份目录组织文章：

| 路径 | 用途 |
|------|------|
| `07.发布文案/<year>年/草稿/` | 草稿来源 |
| `07.发布文案/<year>年/发布/` | 发布稿和生成物料 |
| `07.发布文案/<year>年/发布/发布索引.md` | 当年发布索引 |
| `08.数据反馈/公众号文章库/AI南柯-文章列表.json` | 已发布文章库，用于相关文章 |

首次安装到新的知识库时，建议在 vault 根目录创建 `.wechat-publish.json`。可从任一发布技能目录复制示例：

```text
skills/nk-wechat-publish-archive/scripts/wechat-publish.example.json
```

如果当前命令不是在 vault 根目录执行，可以先设置：

```powershell
$env:WECHAT_PUBLISH_ROOT = "D:/path/to/YourVault"
```

## 发布前归档

在 Codex 中可以直接说：

```text
$nk-wechat-publish-archive 07.发布文案/2026年/草稿/某篇文章.md
```

也可以直接运行技能内置脚本：

```powershell
python ".codex/skills/nk-wechat-publish-archive/scripts/archive_wechat_article_to_publish.py" `
  --article "D:/path/to/YourVault/07.发布文案/2026年/草稿/某篇文章.md" `
  --summary "这里放公众号列表摘要" `
  --cover-title "这里放封面主标题" `
  --cover-subtitle "这里放封面副标题" `
  --brand "AI南柯" `
  --accent "强调词"
```

脚本执行后通常会生成：

- 发布目录中的 Markdown 正文
- 正文引用图片的发布目录副本
- `文章名-公众号封面.png`
- `文章名-公众号列表摘要.txt`
- `文章名.blue.wechat.html`
- `文章名.blue.preview.html`
- 年份目录下的 `发布索引.md`
- HTML 文末动态 `相关文章`

文章在公众号后台手动发布后，再运行：

```text
$nk-wechat-publish-register 这篇
```

## 发布后登记

`nk-wechat-publish-register` 会从公众号后台同步已发布文章，并把正式链接写回文章库、草稿、发布稿和发布索引。

也可以直接运行技能内置脚本：

```powershell
python ".codex/skills/nk-wechat-publish-register/scripts/sync_wechat_published_articles.py" `
  --output-json "08.数据反馈/公众号文章库/AI南柯-文章列表.json" `
  --output-md "08.数据反馈/公众号文章库/AI南柯-文章列表.md"
```

更多参数和验收命令见：

- [`skills/nk-wechat-publish-archive/SKILL.md`](./skills/nk-wechat-publish-archive/SKILL.md)
- [`skills/nk-wechat-publish-register/SKILL.md`](./skills/nk-wechat-publish-register/SKILL.md)
