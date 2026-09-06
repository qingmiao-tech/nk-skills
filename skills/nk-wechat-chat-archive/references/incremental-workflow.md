# 增量归档流程

## 目标

从旧归档的精确截止时间继续整理到用户指定日期，同时保证：

- 旧区间消息数量不漂移。
- 未变化月份文件内容和哈希不变。
- 发生追加的旧月份保留历史正文，只追加新消息。
- 新图片补入，旧图片继续可用。
- 指定日期之后的消息不会混入。
- 正式目录在候选归档验收通过前保持不变。

## 1. 读取旧边界

读取 `<正式归档>/归档说明.json`，至少记录：

- `username`
- `messages`
- `archive_latest`
- `requested_through`
- `months`
- `image_messages`

若旧元数据没有 `archive_latest`，从最后一个月度文件的最后一条消息取得精确到秒的时间。将旧归档复制为只读基线，计算未变化月份哈希。

## 2. 从当前本机数据库导出

保持微信已登录，重新运行 `export_wechat_chat.py`。脚本会刷新消息分片并在私有工作目录中维护解密缓存。不要复用上次导出的静态 JSON 来声称“已到当前日期”。

## 3. 用旧身份完整导出

```powershell
& $py "$skill/scripts/export_wechat_chat.py" `
  --wechatauto-repo "$root/tools/wechatauto-replica" `
  --db-root "E:/path/to/xwechat_files" `
  --workdir "$root/private-cache" `
  --archive-summary "$formal/归档说明.json" `
  --output "$root/target-through.json" `
  --full-output "$root/target-current-full.json" `
  --image-config "$root/private-cache/image-config.json" `
  --through "2026-08-31" `
  --previous-cutoff "2026-06-30 23:59:59" `
  --expected-previous-count 12345
```

上例日期和数量只是占位，必须替换为旧归档的真实边界。检查：

- `previous_count` 等于旧归档消息总数。
- `duplicates` 为 `0`。
- `latest_selected` 不晚于指定日期。
- `excluded_after_cutoff` 与当前数据库中截止日后的消息相符。
- `incremental_count` 等于候选归档应新增的消息数。

任何一项不符都停止，不替换正式归档。

## 4. 生成独立候选归档

使用新的空目录运行 `archive_wechat_v4_chat.py`。为减少重复解密，可以先把旧 `assets/` 复制到候选目录；脚本发现同 md5 资产后会复用。

不要把新归档直接输出到正式目录。推荐结构：

```text
.tmp/wechat-chat-archive/run-YYYYMMDD/
  generated/
  candidate/
  baseline/
```

## 5. 保留历史正文

对于截止时间所在的旧月份，用生成文件更新标题统计，但正文以旧文件为前缀，只追加新消息：

```powershell
& $py "$skill/scripts/merge_incremental_month.py" `
  --existing "$baseline/2026-06.md" `
  --generated "$generated/2026-06.md" `
  --cutoff "2026-06-30 23:59:59" `
  --expected-new 25 `
  --output "$candidate/2026-06.md"
```

未变化月份从基线精确复制；全新月份从生成目录复制。若增量跨越多个旧月份，逐月判断：含旧正文的月份使用合并脚本，纯新月份直接采用生成文件。

## 6. 重建精华和简报

在候选目录上运行 `filter_wechat_archive.py`。过滤结果属于派生产物，可以完整重建；原始月度归档和图片才是历史保护基线。

若群聊主题特殊，使用专属 `--keywords-file`。不要把一套学习群关键词直接宣称适用于客户群、项目群或活动群。

## 7. 写入边界元数据

候选统计确认后运行：

```powershell
& $py "$skill/scripts/update_archive_metadata.py" `
  --archive "$candidate" `
  --previous-cutoff "<旧截止时间>" `
  --incremental-messages <新增数量> `
  --archive-latest "<候选最后时间>" `
  --requested-through "<YYYY-MM-DD>" `
  --session-latest-observed "<完整数据库最后时间>"
```

`archive_latest` 是进入归档的最后一条消息；`session_latest_observed` 可以晚于它，用来证明截止日之后的消息是有意排除，不是漏导。

## 8. 自动验收

```powershell
& $py "$skill/scripts/validate_wechat_archive.py" `
  --archive "$candidate" `
  --expected-messages <总消息数> `
  --expected-images <图片消息数> `
  --expected-latest "<候选最后时间>" `
  --expected-requested-through "<YYYY-MM-DD>" `
  --expected-incremental <新增数量> `
  --history-baseline "$baseline" `
  --prefix-baseline "$baseline" `
  --changed-month "<发生追加的旧月份>" `
  --forbid-month "<截止日之后的月份>"
```

还要人工抽查：第一条、旧截止点前后各两条、最后一条、跨月位置和若干新旧图片。校验必须返回 `"passed": true`。

## 9. 替换正式目录

先将正式目录复制或重命名为带时间戳的备份，再将候选目录放到正式位置。替换后从正式路径重新运行一次验证，确认元数据中的路径也已更新。

如果替换中断，恢复备份，不删除基线和临时数据。只有正式路径复验成功后，才能报告归档完成；临时私有数据是否清理由用户的数据保留策略决定。
