# 工具链与首次运行

## 已验证范围

- 操作系统：Windows。
- 微信：桌面版 4.x，进程名通常为 `Weixin.exe`。
- `wechatauto-replica`：默认固定到 `v1.2.0.3`。
- Python 依赖：`cryptography`、`zstandard`、`imageio-ffmpeg`。

外部项目地址：

- <https://github.com/fanyuantaier/wechatauto-replica>

固定版本是可复现实测基线，不代表永远兼容新版微信。若升级版本，先在临时目录验证消息数量、分片、图片和日期边界，再更新本技能的默认引用。

## 查找微信数据目录

常见结构：

```text
<数据盘>/xwechat_files/
  <账号目录>/
    db_storage/
      contact/contact.db
      session/session.db
      message/message_0.db
    msg/attach/
```

先检查微信配置文件：

```powershell
$config = Join-Path $env:APPDATA "Tencent/xwechat/config"
Get-ChildItem -LiteralPath $config -Filter "*.ini" -ErrorAction SilentlyContinue |
  ForEach-Object {
    [PSCustomObject]@{
      File = $_.FullName
      Value = (Get-Content -LiteralPath $_.FullName -Raw).Trim()
    }
  }
```

配置值通常指向微信数据根目录。只在明确的数据根目录内搜索账号目录：

```powershell
$root = "E:/path/from/wechat-config"
Get-ChildItem -LiteralPath $root -Directory -ErrorAction Stop |
  Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "db_storage") } |
  Select-Object Name, FullName, LastWriteTime
```

传给 `export_wechat_chat.py --db-root` 的是账号目录的父目录，通常为 `xwechat_files`。传给归档脚本 `--wechat-base` 的是选中的具体账号目录。

不要对整块磁盘做无边界递归扫描。找不到配置时，再让用户在微信的文件管理设置中确认存储位置。

## 准备外部工具

```powershell
$skill = ".codex/skills/nk-wechat-chat-archive"
$root = ".tmp/wechat-chat-archive"
python "$skill/scripts/bootstrap_wechat_archive_tools.py" `
  --tools-dir "$root/tools" `
  --install-deps
$py = "$root/tools/.venv/Scripts/python.exe"
```

脚本不会修改已有的脏工具仓库。需要重新拉取指定引用时，先处理仓库改动，再显式增加 `--update`。

## 私有文件

以下内容只保存在临时目录，不进入公开仓库：

```text
.tmp/wechat-chat-archive/private-cache/
.tmp/wechat-chat-archive/target-chat.json
```

推荐 `.gitignore`：

```gitignore
.tmp/wechat-chat-archive/
```

终端输出只展示数量、时间边界和路径。不要打印密钥内容、真实聊天 ID 或聊天正文。若需要共享故障信息，先脱敏账号、群名、路径和消息内容。

## 自定义过滤关键词

`--keywords-file` 接受 UTF-8 JSON，只允许这五类：`关键问答`、`工具资源`、`案例实操`、`方法总结`、`行动跟进`。

```json
{
  "工具资源": ["内部平台", "模板库"],
  "案例实操": ["行业术语", "验收样例"],
  "行动跟进": ["周会", "交付节点"]
}
```

自定义词会追加到通用规则和所选 profile，不会覆盖内置词。先抽查误保留和漏保留，再调整 `--min-score`：数值越高，过滤越严格。

## 故障定位

- `Weixin.exe` 不存在：微信未启动、未登录或版本并非 Windows 微信 4.x。
- `database key verification failed`：保持微信登录，确认工具版本；微信升级后不要盲目重试旧特征码。
- `chat was not found`：目标聊天未落入本地联系人/会话库，或名称不唯一。
- `missing_dat`：附件没有缓存到本机；先在微信里打开原图。
- `missing_module:cryptography`：使用 bootstrap 创建的虚拟环境，或安装 `cryptography`。
- 图片能找到但解密失败：重新生成私有 `image-config.json`，并确认它来自当前登录账号。
