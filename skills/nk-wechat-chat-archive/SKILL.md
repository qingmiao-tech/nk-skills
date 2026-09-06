---
name: nk-wechat-chat-archive
description: 在 Windows 本机把微信 4.x 群聊或单聊整理成按月 Obsidian Markdown，可包含图片、增量续档、价值过滤和每日简报。适用于“归档微信聊天”“从上次截止时间继续整理”“微信群进入本地知识库”“过滤闲聊”“生成学习简报”等请求；既支持从已导出的聊天 JSON 开始，也支持为当前登录账号准备本地工具和数据库。
---

# 微信聊天归档

## 能力边界

本技能支持 Windows 微信 4.x，处理用户本人已登录账号且保存在本机的数据。实时数据库读取依赖一个开源工具，技能内的脚本负责固定版本、串联流程、增量保护和验收：

- `wechatauto-replica`：从正在运行的 `Weixin.exe` 读取并验证各数据库密钥。
- 本技能：导出消息、解析本地 `.dat` 图片、日期截断、按月归档、增量合并、价值过滤、每日简报和一致性校验。

不承诺支持微信 3.x、macOS、移动端备份、企业微信或云端直接获取。微信升级后若内存结构改变，应先验证依赖工具兼容性，不能把“脚本启动”当作“数据已完整导出”。

聊天正文、数据库、账号标识、密钥和图片只在本机处理，不上传外部服务，不写入公开日志、长期文档或 Skill。只处理用户有权访问和归档的数据。

## 选择入口

按现有输入选择最短路径：

1. 只有聊天 JSON：运行归档脚本并加 `--skip-images`，先生成纯文本 Markdown。
2. 已有本技能生成的聊天 JSON、图片密钥配置和微信附件目录：直接运行完整归档。
3. 只有本机已登录的微信：按“首次准备”完成工具安装和聊天导出，再归档。
4. 已有正式归档：读取 `归档说明.json`，按增量流程构建候选目录，验收后再替换正式目录。
5. 只要精华和简报：对已有月度归档运行价值过滤脚本。

## 首次准备

先阅读 [工具链说明](references/toolchain.md)，确认微信版本、数据目录和依赖边界。默认在知识库的 `.tmp/` 下建立私有临时目录：

```powershell
$root = ".tmp/wechat-chat-archive"
python ".codex/skills/nk-wechat-chat-archive/scripts/bootstrap_wechat_archive_tools.py" `
  --tools-dir "$root/tools" `
  --install-deps
$py = "$root/tools/.venv/Scripts/python.exe"
```

保持目标账号已登录，然后直接导出目标聊天。`--db-root` 指向包含账号目录的 `xwechat_files`，不是某个具体账号的 `db_storage`：

```powershell
& $py ".codex/skills/nk-wechat-chat-archive/scripts/export_wechat_chat.py" `
  --wechatauto-repo "$root/tools/wechatauto-replica" `
  --db-root "E:/path/to/xwechat_files" `
  --workdir "$root/private-cache" `
  --chat "<群名或联系人>" `
  --output "$root/target-chat.json" `
  --image-config "$root/private-cache/image-config.json" `
  --through "2026-08-31"
```

如果有多个账号，显式增加 `--account "<账号目录名>"`。密钥缓存和 `image-config.json` 属于私有临时文件，禁止提交 Git。

## 导出与日期边界

首次按群名或备注导出；增量续档用 `--archive-summary` 代替 `--chat`，复用精确聊天 ID，并增加：

```powershell
  --archive-summary "<正式归档>/归档说明.json" `
  --previous-cutoff "<上次精确截止时间>" `
  --expected-previous-count <上次消息总数>
```

`--through YYYY-MM-DD` 包含该日 `23:59:59`，之后消息会明确排除。导出结果必须检查 `previous_count`、`incremental_count`、`latest_selected`、`excluded_after_cutoff` 和 `duplicates`。

## 生成月度归档

完整图片归档：

```powershell
& $py ".codex/skills/nk-wechat-chat-archive/scripts/archive_wechat_v4_chat.py" `
  --chat-json "$root/target-chat.json" `
  --wechat-base "E:/path/to/xwechat_files/<account>" `
  --wechatauto-repo "$root/tools/wechatauto-replica" `
  --image-config "$root/private-cache/image-config.json" `
  --output "$root/generated"
```

只有聊天 JSON 时：

```powershell
python ".codex/skills/nk-wechat-chat-archive/scripts/archive_wechat_v4_chat.py" `
  --chat-json "path/to/chat.json" `
  --skip-images `
  --output "path/to/archive"
```

输出包含 `YYYY-MM.md`、`assets/YYYY-MM/` 和 `归档说明.json`。正式归档建议保存到 `<知识库>/微信聊天归档/<聊天名>/`，但不要假定用户一定使用 Obsidian 或固定目录。

## 价值过滤与每日简报

根据群类型选择 `learning`、`project`、`customer`、`activity` 或 `general`：

```powershell
& $py ".codex/skills/nk-wechat-chat-archive/scripts/filter_wechat_archive.py" `
  --archive-dir "$root/generated" `
  --profile learning `
  --daily-digest
```

领域术语差异较大时增加 `--keywords-file path/to/keywords.json`。文件格式和调参方法见 [工具链说明](references/toolchain.md)。规则过滤是可解释的初筛，不应声称等同于人工判断或大模型语义理解。

## 增量续档

增量任务必须先阅读 [增量归档流程](references/incremental-workflow.md)。核心原则：

- 正式目录只读，先完整导出到临时候选目录。
- 用上次精确时间和消息数验证旧区间没有漂移。
- 未变化月份保持文件哈希不变；发生追加的旧月份保留原正文，只追加截止时间之后的消息。
- 先复制并复用历史图片，再补解新图片。
- 验收通过后备份并精确替换，禁止直接覆盖未验证的正式归档。

## 验收

先运行技能测试和结构校验：

```powershell
python -m unittest discover `
  -s ".codex/skills/nk-wechat-chat-archive/tests" `
  -p "test_*.py" -v
```

再验证实际归档：

```powershell
& $py ".codex/skills/nk-wechat-chat-archive/scripts/validate_wechat_archive.py" `
  --archive "<候选归档>" `
  --expected-messages <消息总数> `
  --expected-images <图片消息数> `
  --expected-latest "<归档最后时间>" `
  --expected-requested-through "<YYYY-MM-DD>"
```

增量任务还应提供历史基线、变化月份和禁入月份。只有校验输出 `"passed": true`，且人工抽查首条、末条、月份边界和若干图片可打开，才可报告完成。

## 常见失败

- 找不到数据目录：按 [工具链说明](references/toolchain.md) 检查微信配置和 `xwechat_files`。
- 无法提取密钥：确认 Windows 微信 4.x 正在运行且账号已登录；若微信刚升级，先核对依赖兼容性。
- 找不到群：先确认群聊已在当前本地数据库中出现；增量任务使用旧归档中的精确 ID。
- 图片缺失：在微信中打开对应图片使缓存落盘，再重跑候选归档。
- 同一 `local_id` 重复：必须以 `source_db + local_id` 识别消息，不能跨分片只按 `local_id` 去重。
- 正式归档与候选统计不一致：停止替换，保留现有归档并检查导出边界。
