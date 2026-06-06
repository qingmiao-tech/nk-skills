# nk-skills

`nk-skills` 当前发布三个技能：

- `nk-wechat-chat-archive`
- `nk-wechat-publish-archive`
- `nk-wechat-publish-register`

| 技能 | 用途 | 典型输出 |
|------|------|----------|
| `nk-wechat-chat-archive` | 微信 4.x Windows 聊天记录归档 | Obsidian Markdown、图片附件、精华归档、每日简报 |
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

手动安装全部技能时，在 PowerShell 中执行：

```powershell
$tmp = Join-Path $env:TEMP "nk-skills-install"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
git clone --depth 1 git@github.com:qingmiao-tech/nk-skills.git $tmp
$dest = Join-Path $env:USERPROFILE ".codex\skills"
New-Item -ItemType Directory -Force $dest | Out-Null
foreach ($skill in @("nk-wechat-chat-archive", "nk-wechat-publish-archive", "nk-wechat-publish-register")) {
  Copy-Item (Join-Path $tmp "skills\$skill") $dest -Recurse -Force
}
```

安装后，Codex CLI 会在下面路径读取技能：

```text
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

## nk-wechat-chat-archive

`nk-wechat-chat-archive` 用于把微信 4.x Windows 聊天记录归档到 Obsidian Markdown。它适合这些场景：

- 整理微信群或单聊记录，按月份生成 Markdown。
- 在已完成微信数据库解密和聊天 JSON 导出后，生成可长期保存的知识库归档。
- 从本地 `.dat` 附件解密图片，并写入归档目录的 `assets/`。
- 对完整归档做价值过滤，生成精华归档和每日简报。

这个技能不负责破解或上传数据。推荐工作方式是：

1. 用成熟工具 `wechat-decrypt` 解密微信 4.x 数据库。
2. 用 `wechat-decrypt/export_chat.py` 或等价脚本导出目标聊天 JSON。
3. 用本技能脚本把聊天 JSON、已解密数据库、本地附件目录转成 Obsidian Markdown。

不要把聊天内容、数据库、key 或图片上传到外部服务。不要把真实 key 写进长期文档或技能文件。

最小使用示例：

```powershell
python ".codex/skills/nk-wechat-chat-archive/scripts/archive_wechat_v4_chat.py" `
  --chat-json ".tmp/wechat-export/target-chat.json" `
  --decrypted-dir ".tmp/wechat-export/decrypted" `
  --wechat-base "E:/path/to/xwechat_files/<wxid>_<suffix>" `
  --wechat-decrypt-tool ".tmp/wechat-export/tools/wechat-decrypt" `
  --wechat-decrypt-config ".tmp/wechat-export/tools/wechat-decrypt/config.json" `
  --output "10.Hermes协同/微信聊天归档/<聊天名>"
```

归档完成后，可以继续生成精华归档和每日简报：

```powershell
python ".codex/skills/nk-wechat-chat-archive/scripts/filter_wechat_archive.py" `
  --archive-dir "10.Hermes协同/微信聊天归档/<聊天名>" `
  --profile learning `
  --daily-digest
```

更多参数和验收命令见 [`skills/nk-wechat-chat-archive/SKILL.md`](./skills/nk-wechat-chat-archive/SKILL.md)。

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
