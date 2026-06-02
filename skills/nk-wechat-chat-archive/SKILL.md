---
name: nk-wechat-chat-archive
description: 将微信 4.x Windows 聊天记录归档到 Obsidian Markdown。适用于用户要求“整理微信聊天记录”“微信群按月份归档”“微信聊天导出到本地知识库”“包含图片”“Weixin.exe / xwechat_files / 微信 4.x 数据库解密”“复用上次微信归档方案”等场景；支持在已完成数据库解密和聊天 JSON 导出后，把消息按月份生成 Markdown，并从本地 .dat 附件解密图片到 assets。
---

# 微信聊天归档

## 核心边界

使用成熟工具负责脆弱环节：

- 用 `wechat-decrypt` 扫描 Weixin.exe 内存、提取 per-DB key、解密 SQLCipher 4 数据库。
- 用 `wechat-decrypt/export_chat.py` 或等价脚本导出目标聊天 JSON。
- 用本技能的 `scripts/archive_wechat_v4_chat.py` 做最后一段确定性处理：聊天 JSON + 已解密 message DB + 本地附件目录 -> Obsidian 月度 Markdown + assets 图片。

不要把聊天内容、数据库、key 或图片上传到外部服务。不要把真实 key 写进长期文档或 skill。

## 推荐目录

在 vault 内使用临时工作区：

```text
.tmp/wechat-export/
  tools/wechat-decrypt/
  decrypted/
  target-chat.json
```

正式归档输出建议：

```text
10.Hermes协同/微信聊天归档/<群名或联系人名>/
  2026-02.md
  2026-03.md
  assets/
  归档说明.json
```

## 工作流

1. 确认微信版本和数据目录。微信 4.x Windows 常见目录是 `xwechat_files/<wxid>_<suffix>/db_storage`，附件在同级 `msg/attach`。
2. 克隆或复用 `wechat-decrypt`，配置 `config.json` 的 `db_dir`、`decrypted_dir`、`keys_file`。
3. 在微信正在运行且目标账号已登录时提取 key，并执行数据库解密。
4. 用聊天名、备注名、群名或 `@chatroom` 导出 JSON。
5. 用本技能脚本生成 Obsidian 归档。
6. 校验月份文件数、消息数、图片引用数和缺失图片数。
7. 如需日常复用，继续用价值过滤脚本生成“精华归档”和“每日简报”，把闲聊、系统消息和低信息密度短句过滤掉。

## Python 依赖

归档脚本自身只依赖标准库；但读取微信压缩正文和解密 V2 图片时需要与 `wechat-decrypt` 相同的依赖：

```powershell
python -m pip install -r ".tmp/wechat-export/tools/wechat-decrypt/requirements.txt"
```

最低检查：

```powershell
python -c "import Crypto, zstandard; print('deps ok')"
```

如果缺少 `Crypto`，V2 图片会无法解密；如果缺少 `zstandard`，部分压缩正文可能为空。

## 归档脚本

基本用法：

```powershell
python ".codex/skills/nk-wechat-chat-archive/scripts/archive_wechat_v4_chat.py" `
  --chat-json ".tmp/wechat-export/target-chat.json" `
  --decrypted-dir ".tmp/wechat-export/decrypted" `
  --wechat-base "E:/path/to/xwechat_files/<wxid>_<suffix>" `
  --wechat-decrypt-tool ".tmp/wechat-export/tools/wechat-decrypt" `
  --wechat-decrypt-config ".tmp/wechat-export/tools/wechat-decrypt/config.json" `
  --output "10.Hermes协同/微信聊天归档/<聊天名>"
```

常用参数：

- `--chat-json`：`export_chat.py` 生成的 JSON。
- `--decrypted-dir`：已解密数据库根目录，内部应有 `message/message_0.db`。
- `--wechat-base`：当前账号的 `xwechat_files/<wxid>_<suffix>` 目录。
- `--wechat-decrypt-tool`：包含 `decode_image.py` 的 `wechat-decrypt` 目录。
- `--wechat-decrypt-config`：读取 `image_aes_key` 和 `image_xor_key`。
- `--image-aes-key`、`--image-xor-key`：只在临时命令中覆盖，不要写入文档。
- `--output`：归档输出目录。

## 价值过滤与每日简报

当完整归档已经生成后，可以继续把月度聊天记录转成更适合复盘的“价值过滤”版本：

```powershell
python ".codex/skills/nk-wechat-chat-archive/scripts/filter_wechat_archive.py" `
  --archive-dir "10.Hermes协同/微信聊天归档/<聊天名>" `
  --profile learning `
  --daily-digest
```

输出结构：

```text
10.Hermes协同/微信聊天归档/<聊天名>/
  价值过滤/
    2026-02-价值.md
    2026-03-价值.md
    每日简报/
      2026-02-18.md
      2026-02-19.md
    价值过滤说明.json
```

过滤逻辑：

- 自动跳过系统消息、撤回提示、寒暄、纯表情、短确认、低信息密度闲聊。
- 优先保留关键问答、工具资源、案例实操、方法总结、行动跟进。
- 图片不会盲目全留；只有自身命中价值规则，或靠近高价值消息时，才会作为上下文保留。
- 输出文件会重写图片相对路径，继续引用原归档中的 `assets/` 图片，不复制图片。
- `--profile` 用于调整关注点：`learning` 适合学习群，`project` 适合项目群，`customer` 适合客户群，`activity` 适合行程/活动群，`general` 使用通用规则。

常用参数：

- `--min-score`：保留阈值，默认 `4`。数值越高，过滤越严格。
- `--context-window`：给高价值消息保留前后上下文，默认 `0`。
- `--image-context-window`：图片邻近高价值消息时保留，默认前后 `2` 条。
- `--daily-digest`：生成每日简报。
- `--daily-limit`：每日简报摘录条数，默认 `12`。

## 图片处理规则

脚本会：

- 用聊天 username 计算 `md5(username)`，定位 `msg/attach/<chat_hash>/<YYYY-MM>/Img/`。
- 从图片消息的 `packed_info_data` 或 XML 中提取 32 位 md5。
- 优先选择 `_h`、其次 `_W`、再 `_t` 的 `.dat` 文件。
- 调用 `decode_image.decrypt_dat_file()` 解密，写入 `assets/<YYYY-MM>/<md5>.<ext>`。
- Markdown 中使用相对路径引用图片。

如果图片缺失，先让用户在微信里打开对应图片，使本地缓存落盘，再重跑归档脚本。

## 验收命令

```powershell
$out = "10.Hermes协同/微信聊天归档/<聊天名>"
Get-Content "$out/归档说明.json" -Raw
rg -n "!\[\]\(" "$out"
rg -n "图片未能解密|缺失|failed" "$out"
Get-Content "$out/价值过滤/价值过滤说明.json" -Raw
```

合格标准：

- `归档说明.json` 中 `messages` 与导出 JSON 消息数一致。
- 月度文件覆盖目标时间范围。
- `image_messages` 与 Markdown 图片引用数一致，或能解释未解密原因。
- `image_diagnostics` 为空或只有可解释项；若出现 `missing_module:Crypto`，先安装 `pycryptodome`。
- Markdown 图片引用的本地文件全部存在。
- 价值过滤输出中 `kept_messages` 明显小于 `source_messages`，且 `每日简报/` 能按天生成可浏览文件。

## 常见失败判断

- `pywxdump` 无法读取：优先判断是否为微信 4.x / `Weixin.exe` / `xwechat_files`，不要继续套旧版方案。
- SQLite 直接打开失败：数据库仍是 SQLCipher/WCDB 加密状态，先解密。
- 找不到群：先用联系人库解析群名到 `@chatroom`，再用 `md5(username)` 找消息表。
- 解不出 V2 图片：检查 `config.json` 是否有 `image_aes_key` 和 `image_xor_key`，以及本地是否已有足够 `.dat` 缓存。
- 时间戳异常：确认导出 JSON 使用本机本地时间语义；月度分组以 `create_time` 为准。
