---
name: nk-wechat-publish-archive
description: 用于“公众号发布归档”的发布前物料生成：将草稿 Markdown 复制归档到对应年份发布目录，并自动生成公众号封面图、列表摘要、微信公众号 HTML 和动态相关文章。适用于用户说“生成公众号发布物料”“归档到发布目录”“把草稿转到发布并带上图片和封面”等场景；文章手动发布后的正式链接登记交给 nk-wechat-publish-register（公众号发布登记）技能。
---

# nk-wechat-publish-archive（公众号发布归档）

## 目标

把草稿目录里的文章发布到对应年份目录下的 `发布` 目录中，并保持原有子目录结构。

执行后会得到：

- 发布目录中的 Markdown 正文
- 被正文引用的本地图片副本
- `文章名-公众号封面.png`
- `文章名-公众号列表摘要.txt`
- `文章名.blue.wechat.html`
- `文章名.blue.preview.html`
- 草稿原文中的发布记录回写，发布链接先留空或待补充
- 发布稿自身的归档信息回写，发布链接先留空或待补充
- 对应年份目录下的 `发布索引.md`
- HTML 末尾的动态 `相关文章` 区域

## 内置脚本

`{baseDir}` 表示本技能目录。分享安装后，优先使用本技能自带脚本：

```text
{baseDir}/scripts/archive_wechat_article_to_publish.py
{baseDir}/scripts/build_wechat_publish_package.py
{baseDir}/scripts/build_wechat_cover_package.py
{baseDir}/scripts/sync_wechat_published_articles.py
{baseDir}/scripts/wechat_publish_config.py
{baseDir}/scripts/wechat-publish.example.json
```

如果用户原本已有 `00.系统配置/wechat-cover-summary-tool/` 工具目录，也可以继续使用原目录，不需要迁移本地文件。

运行内置脚本时，建议在 vault 根目录执行；如果当前工作目录不是 vault 根目录，先设置：

```powershell
$env:WECHAT_PUBLISH_ROOT = "D:/path/to/YourVault"
```

## 通用初始化

首次给别人使用时，不要假设对方也使用 `D:/ObsidianVaults/MyVault`、`AI南柯` 或相同目录结构。先完成初始化检查：

1. 定位用户的 vault / 项目根目录。
2. 检查根目录是否存在 `.wechat-publish.json`。
3. 如果不存在，参考 `00.系统配置/wechat-cover-summary-tool/wechat-publish.example.json` 创建一份配置文件。
4. 最少确认这些字段：
   - `publish_doc_root`：公众号草稿、发布目录所在根目录，默认 `07.发布文案`
   - `article_library_json` / `article_library_md`：公众号文章库输出路径
   - `header_template` / `footer_template`：品牌模板路径；可以留空，留空表示不插入品牌头尾
   - `related_articles_limit`：相关文章数量，默认 5
5. 如果用户没有配置文件，本技能继续使用当前本地默认值，兼容南柯现有工作流。

示例配置：

```json
{
  "publish_doc_root": "07.发布文案",
  "article_library_json": "08.数据反馈/公众号文章库/我的公众号-文章列表.json",
  "article_library_md": "08.数据反馈/公众号文章库/我的公众号-文章列表.md",
  "header_template": "",
  "footer_template": "",
  "publish_index_filename": "发布索引.md",
  "related_articles_limit": 5,
  "wechat_session_file": "skills/wechat-draft-publisher/scripts/session.json",
  "opencli_daemon_url": "http://127.0.0.1:19825"
}
```

## 目录规则

默认发布根目录按文章年份自动推导：

```text
07.发布文案/2026年/发布/
```

路径映射规则：

- 源文件在 `07.发布文案/2026年/草稿/xxx/文章.md`
- 目标文件变成 `07.发布文案/2026年/发布/xxx/文章.md`

也就是说：

- 发布目录跟着年份走，新的一年会自动落到新的年份目录
- `草稿` 之后的相对结构原样保留
- 草稿目录本身不移动、不删除
- 发布目录里是独立副本

## 执行步骤

1. 读取草稿文章全文。
2. 生成公众号列表摘要。
3. 将文章复制到对应年份的 `发布` 目录下。
4. 扫描正文中的本地图片引用并复制到目标目录对应相对路径。
5. 在发布目录中调用统一发布包脚本，生成封面、摘要、HTML，并从文章库/发布索引挑选最多 5 条相关文章。
6. 回写草稿原文的物料归档信息：
   - 有 YAML frontmatter 时，更新 `status`、`published_path`、`published_at`
   - 没有 YAML 时，在文末维护固定的 `## 发布记录` 区块
   - 这个阶段通常不写 `published_url`，因为文章还没手动发布
7. 回写发布稿自身的归档信息，记录草稿来源、封面文件、预览文件、发布时间和列表摘要。
8. 自动维护年份目录下的 `发布索引.md`，发布链接先为 `待补充`。
9. 用户手动在公众号后台发布后，使用 `nk-wechat-publish-register（公众号发布登记）` 技能补齐正式链接和后台文章信息。

## 前置检查

生成公众号 HTML 时会把正文中的本地图片上传到 GitHub 图床，底层可能读取 `gh` 的 Windows keyring token。

在 Codex 桌面沙箱里，普通命令可能读不到 keyring，导致误报 `gh auth status` token invalid，或脚本提示缺少 `GITHUB_TOKEN / GITHUB_REPO`。遇到这类结果时，不要直接判断为图床配置丢失。必须先用提权执行复验：

```powershell
gh auth status
```

如果提权后 `gh auth status` 显示已登录，后续调用 `archive_wechat_article_to_publish.py` 也要用提权方式执行，确保 GitHub 图床上传能读取 keyring token。

如果用户没有 GitHub 图床配置，不要伪装成已生成完整发布包。先提示用户配置 `GITHUB_TOKEN / GITHUB_REPO`，或只执行不依赖图床的归档/封面/摘要步骤。

## 统一命令

```powershell
python "{baseDir}/scripts/archive_wechat_article_to_publish.py" `
  --article "{vault_root}/07.发布文案/2026年/草稿/某专题/2026年5月14日-某篇文章.md" `
  --summary "这里放公众号列表摘要" `
  --cover-title "这里放封面主标题" `
  --cover-subtitle "这里放封面副标题" `
  --brand "这里放品牌角标" `
  --accent "这里放强调词"
```

发布后登记正式链接：

```text
$nk-wechat-publish-register 这篇
```

或：

```text
$nk-wechat-publish-register 07.发布文案/2026年/发布/文章.md
```

## 规则

- 图片使用复制，不做移动，避免影响其他草稿共用素材。
- 只复制正文中实际引用到的本地图片。
- 默认仍使用 `blue` 主题生成 HTML。
- 默认在蓝莹主题下把 Markdown 的 `##` 按一级标题样式渲染。
- 生成 HTML 时优先读取 `.wechat-publish.json` 中的 `header_template`；没有配置文件时兼容南柯当前默认头部卡片。
- 生成 HTML 时不再读取固定二维码尾部；脚本会根据配置中的文章库和各年 `发布索引.md` 动态生成 `相关文章`。
- `相关文章` 最多 5 条；没有可用正式链接时不输出尾部，避免放置二维码、私域引导或过长历史列表。
- 相关文章优先选择已有正式链接的文章，按主题关键词重合、近期程度、同系列工作流关联度综合排序；不会展示发布链接仍为“待补充”的文章。
- 生成 HTML 时自动忽略 YAML frontmatter 和草稿文末的发布记录，不把这些元信息带进公众号正文。
- 没有本地图片引用时，也要继续生成封面、摘要和 HTML。
- 重复发布同一草稿时，更新同一份发布记录，不重复堆叠。
- 同一篇文章重复发布时，会更新发布索引中的对应条目，而不是重复追加。
- 本技能只负责发布前物料生成；手动发布后的正式链接、后台摘要、封面和发布时间登记，交给 `nk-wechat-publish-register（公众号发布登记）`。
- 不要在没有用户确认或后台匹配证据时，猜测当前文章的公众号正式链接。

## 结果检查

执行后确认：

- 发布目录中已出现新的 Markdown 文件
- 引用图片已复制到发布目录对应位置
- 封面、摘要、HTML 都生成在发布目录
- 草稿原文已写入最新发布路径
- 发布稿自身已写入归档信息
- 当年 `发布索引.md` 已更新，发布链接为 `待补充` 或已确认链接
- 草稿目录中的原文件和原图片仍然保留
- 结束时提醒用户：网页后台发布完成后，执行 `$nk-wechat-publish-register 这篇`
