# nk-skills

`nk-skills` 当前发布两个技能：

- `nk-wechat-chat-archive`
- `nk-wechat-publish-archive`

`nk-wechat-chat-archive` 用于把微信 4.x Windows 聊天记录归档到 Obsidian Markdown。它适合这些场景：

- 整理微信群或单聊记录，按月份生成 Markdown。
- 在已完成微信数据库解密和聊天 JSON 导出后，生成可长期保存的知识库归档。
- 从本地 `.dat` 附件解密图片，并写入归档目录的 `assets/`。
- 对完整归档做价值过滤，生成精华归档和每日简报。

## 一句话安装

在 PowerShell 中执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$tmp=Join-Path $env:TEMP 'nk-skills-install'; Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue; git clone --depth 1 git@github.com:qingmiao-tech/nk-skills.git $tmp; New-Item -ItemType Directory -Force (Join-Path $env:USERPROFILE '.codex\skills') | Out-Null; Copy-Item (Join-Path $tmp 'skills\nk-wechat-chat-archive') (Join-Path $env:USERPROFILE '.codex\skills') -Recurse -Force; Copy-Item (Join-Path $tmp 'skills\nk-wechat-publish-archive') (Join-Path $env:USERPROFILE '.codex\skills') -Recurse -Force"
```

安装后，Codex CLI 会在下面路径读取技能：

```text
%USERPROFILE%\.codex\skills\nk-wechat-chat-archive
%USERPROFILE%\.codex\skills\nk-wechat-publish-archive
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

本次同步的相关文章规则：

- 文末 `相关文章` 最多展示 5 条。
- 只展示已有正式公众号链接的文章，不展示发布链接仍为 `待补充` 的文章。
- 当前文章自身会被排除。
- 相关文章按主题关键词重合、近期程度、同系列工作流关联度综合排序。

工具脚本同步在：

```text
00.系统配置/wechat-cover-summary-tool/build_wechat_publish_package.py
```

更多参数和验收命令见 [`skills/nk-wechat-publish-archive/SKILL.md`](./skills/nk-wechat-publish-archive/SKILL.md)。

