---
name: nk-wechat-publish-register
description: 用于“公众号发布登记”的发布后补链：手动在微信公众号后台发布文章后，从后台同步正式文章信息，并把正式链接、发布时间、摘要、封面等信息整理到公众号文章库，同时回写草稿、发布稿和发布索引。适用于用户说“登记这篇公众号”“补链”“同步刚发布的公众号链接”“把发布后的公众号信息整理到文章列表”等场景。
---

# nk-wechat-publish-register（公众号发布登记）

## 触发场景

用于 `nk-wechat-publish-archive（公众号发布归档）` 之后的第二步：用户已经手动在微信公众号网页后台发布完成，现在要登记正式发布信息。

推荐短指令：

```text
$nk-wechat-publish-register 这篇
```

如果上下文里没有明确文章，使用：

```text
$nk-wechat-publish-register 07.发布文案/2026年/发布/文章.md
```

如果用户直接贴了公众号链接，也可以一起使用：

```text
$nk-wechat-publish-register 07.发布文案/2026年/发布/文章.md https://mp.weixin.qq.com/s/xxxx
```

## 内置脚本

`{baseDir}` 表示本技能目录。分享安装后，优先使用本技能自带脚本：

```text
{baseDir}/scripts/sync_wechat_published_articles.py
{baseDir}/scripts/archive_wechat_article_to_publish.py
{baseDir}/scripts/wechat_publish_config.py
{baseDir}/scripts/wechat-publish.example.json
```

如果用户原本已有 `00.系统配置/wechat-cover-summary-tool/` 工具目录，也可以继续使用原目录，不需要迁移本地文件。

运行内置脚本时，建议在 vault 根目录执行；如果当前工作目录不是 vault 根目录，先设置：

```powershell
$env:WECHAT_PUBLISH_ROOT = "D:/path/to/YourVault"
```

## 通用初始化

首次给别人使用时，先读取或创建根目录下的 `.wechat-publish.json`，字段含义与 `nk-wechat-publish-archive` 一致。重点确认：

- `article_library_json` / `article_library_md`：写入用户自己的公众号文章库，不要写到 `AI南柯-文章列表`
- `publish_doc_root`：扫描用户自己的发布索引
- `opencli_daemon_url`：OpenCLI daemon 地址，默认 `http://127.0.0.1:19825`
- `wechat_session_file`：Playwright 降级方案使用的 session 文件

没有 `.wechat-publish.json` 时，继续兼容南柯当前本地默认配置。

## OpenCLI 检查

优先复用主 Chrome 登录态，但不要假设用户已经装好 OpenCLI。

执行前按顺序检查：

```powershell
opencli --help
opencli doctor
opencli daemon status
```

如果 `opencli` 不存在，提示用户安装：

```powershell
npm install -g @jackwener/opencli
```

如果 OpenCLI daemon 可用但 Chrome 扩展未连接，不能静默安装浏览器插件。应提示用户打开 OpenCLI 的安装说明或插件安装入口，完成后重新运行 `opencli doctor`。

如果 OpenCLI 暂时不可用，降级为用户直接粘贴公众号正式链接：

```text
$nk-wechat-publish-register 07.发布文案/2026年/发布/文章.md https://mp.weixin.qq.com/s/xxxx
```

这样仍然可以回写本地文章库、草稿、发布稿和发布索引，只是不能自动从后台批量同步摘要、封面和发布时间。

## 执行规则

- 优先使用 `opencli` 读取主 Chrome 的微信公众号后台登录态，不打开独立扫码浏览器。
- 先同步公众号后台文章库，再回写当前文章链接，保证配置中的文章库 JSON/Markdown 信息格式一致。
- 如果用户提供了链接，用用户提供的链接作为当前文章正式链接；仍可同步后台文章库补充摘要、封面、发布时间。
- 如果用户没有提供链接，用当前文章标题从后台文章库自动匹配。
- 只做发布后登记，不重新复制文章、不重新生成封面和 HTML，除非用户明确要求重建发布物料。
- 如果无法从后台匹配到当前文章，提示用户打开公众号后台发表记录列表页后重试，或直接粘贴当前文章正式链接。
- 对非南柯用户，文章库路径以 `.wechat-publish.json` 为准。

## 命令

先同步后台文章库：

```powershell
python "{baseDir}/scripts/sync_wechat_published_articles.py" `
  --backend opencli `
  --update-index
```

自动按标题补当前文章链接：

```powershell
python "{baseDir}/scripts/archive_wechat_article_to_publish.py" `
  --article "{vault_root}/07.发布文案/2026年/发布/文章.md" `
  --update-link-only `
  --auto-fetch-published-url `
  --wechat-sync-backend opencli
```

用户已提供正式链接时：

```powershell
python "{baseDir}/scripts/archive_wechat_article_to_publish.py" `
  --article "{vault_root}/07.发布文案/2026年/发布/文章.md" `
  --update-link-only `
  --published-url "https://mp.weixin.qq.com/s/xxxx"
```

## 检查

- `.wechat-publish.json` 配置中的文章库 JSON 已包含当前文章正式链接；没有配置文件时检查南柯当前默认文章库。
- 草稿 frontmatter 或 `## 发布记录` 已写入 `published_url`。
- 发布稿 frontmatter 和底部 `## 发布记录` 已写入同一个正式链接。
- `07.发布文案/<年份>/发布/发布索引.md` 当前文章条目的 `发布链接` 已更新。
- 不要把旧文章链接误登记为当前文章链接；如标题相近，优先以后台最新发布时间和用户确认的链接为准。
