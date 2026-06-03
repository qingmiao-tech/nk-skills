# nk-skills

`nk-skills` 当前发布两个技能：

- `nk-wechat-chat-archive`
- `nk-wechat-publish-archive`

| 技能 | 用途 | 典型输出 |
|------|------|----------|
| `nk-wechat-chat-archive` | 微信 4.x Windows 聊天记录归档 | Obsidian Markdown、图片附件、精华归档、每日简报 |
| `nk-wechat-publish-archive` | 公众号发布前物料归档 | 发布稿、封面图、列表摘要、公众号 HTML、动态相关文章 |

`nk-wechat-chat-archive` 用于把微信 4.x Windows 聊天记录归档到 Obsidian Markdown。它适合这些场景：

- 整理微信群或单聊记录，按月份生成 Markdown。
- 在已完成微信数据库解密和聊天 JSON 导出后，生成可长期保存的知识库归档。
- 从本地 `.dat` 附件解密图片，并写入归档目录的 `assets/`。
- 对完整归档做价值过滤，生成精华归档和每日简报。

## 一句话安装

最简单的方式是把下面这句话直接发给你的 Codex、Claude Code 或其他支持 Skills 的 Agent，让它代你安装：

```text
请帮我安装这个 Skills 仓库：git@github.com:qingmiao-tech/nk-skills.git
```

如果你的 Agent 不能使用 SSH，也可以发 HTTPS 地址：

```text
请帮我安装这个 Skills 仓库：https://github.com/qingmiao-tech/nk-skills.git
```

手动安装时，在 PowerShell 中执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$tmp=Join-Path $env:TEMP 'nk-skills-install'; Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue; git clone --depth 1 git@github.com:qingmiao-tech/nk-skills.git $tmp; New-Item -ItemType Directory -Force (Join-Path $env:USERPROFILE '.codex\skills') | Out-Null; Copy-Item (Join-Path $tmp 'skills\nk-wechat-chat-archive') (Join-Path $env:USERPROFILE '.codex\skills') -Recurse -Force; Copy-Item (Join-Path $tmp 'skills\nk-wechat-publish-archive') (Join-Path $env:USERPROFILE '.codex\skills') -Recurse -Force"
```

安装后，Codex CLI 会在下面路径读取技能：

```text
%USERPROFILE%\.codex\skills\nk-wechat-chat-archive
%USERPROFILE%\.codex\skills\nk-wechat-publish-archive
```

只安装公众号发布归档技能时，可以执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$tmp=Join-Path $env:TEMP 'nk-skills-install'; Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue; git clone --depth 1 git@github.com:qingmiao-tech/nk-skills.git $tmp; New-Item -ItemType Directory -Force (Join-Path $env:USERPROFILE '.codex\skills') | Out-Null; Copy-Item (Join-Path $tmp 'skills\nk-wechat-publish-archive') (Join-Path $env:USERPROFILE '.codex\skills') -Recurse -Force"
```

## nk-wechat-chat-archive 技能边界

这个技能不负责破解或上传数据。推荐工作方式是：

1. 用成熟工具 `wechat-decrypt` 解密微信 4.x 数据库。
2. 用 `wechat-decrypt/export_chat.py` 或等价脚本导出目标聊天 JSON。
3. 用本技能脚本把聊天 JSON、已解密数据库、本地附件目录转成 Obsidian Markdown。

不要把聊天内容、数据库、key 或图片上传到外部服务。不要把真实 key 写进长期文档或技能文件。

## 最小使用示例

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

## nk-wechat-publish-archive

这个技能用于公众号发布前物料归档：把 Obsidian 草稿复制到发布目录，生成封面、列表摘要、微信公众号 HTML 和动态 `相关文章`。

适合这些场景：

- 文章草稿已经写好，需要生成公众号发布前物料。
- 希望把草稿复制到对应年份的 `发布` 目录，保留原草稿不移动。
- 希望自动生成封面、列表摘要、蓝莹主题公众号 HTML 和预览 HTML。
- 希望发布稿文末自动带上动态 `相关文章`，但不插入二维码或私域引导。

## nk-wechat-publish-archive 目录约定

默认按 Obsidian 知识库中的年份目录组织文章：

| 路径 | 用途 |
|------|------|
| `07.发布文案/<year>年/草稿/` | 草稿来源 |
| `07.发布文案/<year>年/发布/` | 发布稿和生成物料 |
| `07.发布文案/<year>年/发布/发布索引.md` | 当年发布索引 |
| `08.数据反馈/公众号文章库/AI南柯-文章列表.json` | 已发布文章库，用于相关文章 |
| `00.系统配置/wechat-cover-summary-tool/` | 本地公众号封面、摘要、HTML 工具脚本 |

完整发布归档入口通常是本地知识库里的：

```text
00.系统配置/wechat-cover-summary-tool/archive_wechat_article_to_publish.py
```

本仓库同步了本次规则更新涉及的发布包生成脚本：

```text
00.系统配置/wechat-cover-summary-tool/build_wechat_publish_package.py
```

## nk-wechat-publish-archive 配置示例

如果知识库不在当前工作目录，可以在项目或用户配置中创建：

```text
.nk-skills/nk-wechat-publish-archive/EXTEND.md
```

示例：

```yaml
---
vault_root: D:/ObsidianVaults/MyVault
archive_script: 00.系统配置/wechat-cover-summary-tool/archive_wechat_article_to_publish.py
draft_root: 07.发布文案
article_library: 08.数据反馈/公众号文章库/AI南柯-文章列表.json
theme: blue
---
```

## nk-wechat-publish-archive 最小使用示例

在 Codex 中可以直接说：

```text
$nk-wechat-publish-archive 07.发布文案/2026年/草稿/某篇文章.md
```

也可以直接运行本地归档脚本：

```powershell
python "D:/ObsidianVaults/MyVault/00.系统配置/wechat-cover-summary-tool/archive_wechat_article_to_publish.py" `
  --article "D:/ObsidianVaults/MyVault/07.发布文案/2026年/草稿/某篇文章.md" `
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

用于登记正式链接和后台文章信息。

## nk-wechat-publish-archive 相关文章规则

本次同步的相关文章规则：

- 文末 `相关文章` 最多展示 5 条。
- 只展示已有正式公众号链接的文章，不展示发布链接仍为 `待补充` 的文章。
- 当前文章自身会被排除。
- 相关文章按主题关键词重合、近期程度、同系列工作流关联度综合排序。

重点主题词会额外加权，包括：

```text
obsidian、知识库、长期记忆、记忆系统、本地、归档、复盘、工作流、skill、脚本、agent、智能体、hermes、飞书、公众号、发布
```

近期文章会额外加权：

- 7 天内：+30
- 14 天内：+24
- 30 天内：+16
- 90 天内：+3

更多参数和验收命令见 [`skills/nk-wechat-publish-archive/SKILL.md`](./skills/nk-wechat-publish-archive/SKILL.md)。

