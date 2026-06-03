---
name: nk-wechat-publish-archive
description: Generates pre-publish WeChat Official Account materials from an Obsidian Markdown draft. It copies the draft into the yearly publish folder, preserves referenced local images, builds cover/list-summary/WeChat HTML/preview HTML, and adds a dynamic related-article footer without QR-code or private-traffic blocks. Use when the user asks for "公众号发布归档", "生成公众号发布物料", "归档到发布目录", or to prepare a draft before manual web publishing.
version: 2.5.0
metadata:
  openclaw:
    homepage: https://github.com/JimLiu/nk-skills#nk-wechat-publish-archive
---

# WeChat Publish Archive

发布前物料生成技能。它不直接发布公众号文章，也不猜测正式链接；用户在公众号后台手动发布后，再运行 `nk-wechat-publish-register` 登记正式链接和后台信息。

## Language

Respond in the user's language. For Chinese WeChat/Obsidian workflows, default to concise Simplified Chinese.

## Preferences (EXTEND.md)

Check these paths in order; first hit wins:

| Path | Scope |
|------|-------|
| `.nk-skills/nk-wechat-publish-archive/EXTEND.md` | Project |
| `${XDG_CONFIG_HOME:-$HOME/.config}/nk-skills/nk-wechat-publish-archive/EXTEND.md` | XDG |
| `$HOME/.nk-skills/nk-wechat-publish-archive/EXTEND.md` | User home |

Supported keys are optional:

| Key | Default | Purpose |
|-----|---------|---------|
| `vault_root` | current workspace | Obsidian vault root |
| `archive_script` | `00.系统配置/wechat-cover-summary-tool/archive_wechat_article_to_publish.py` | Local archive script path, relative to `vault_root` unless absolute |
| `draft_root` | `07.发布文案` | Root containing yearly draft/publish folders |
| `article_library` | `08.数据反馈/公众号文章库/AI南柯-文章列表.json` | Article library used for related links |
| `theme` | `blue` | HTML theme expected by the local script |

If no EXTEND.md exists, proceed with the defaults and the current workspace as `vault_root`.

## Workflow

1. Identify the source Markdown article. Prefer an explicit path from the user. If the user says "this article", resolve it from the current conversation or the most recent publish artifact path.
2. Read the draft and produce the required publishing metadata:
   - list summary for the Official Account article list;
   - cover title/subtitle/brand/accent values;
   - any user-provided title or summary should take precedence.
3. Run the local archive script from the vault:

```bash
python "{vault_root}/00.系统配置/wechat-cover-summary-tool/archive_wechat_article_to_publish.py" \
  --article "{draft_markdown}" \
  --summary "{list_summary}" \
  --cover-title "{cover_title}" \
  --cover-subtitle "{cover_subtitle}" \
  --brand "{brand}" \
  --accent "{accent}"
```

4. Treat the script output as the source of truth for generated paths.
5. Do not write or infer `published_url` during this step unless the user explicitly provides a verified URL for the same article.
6. End by telling the user to manually publish in the WeChat web backend, then run:

```text
/nk-wechat-publish-register 这篇
```

## Expected Project Conventions

The target vault normally uses this structure:

| Path | Purpose |
|------|---------|
| `07.发布文案/<year>年/草稿/` | Source drafts |
| `07.发布文案/<year>年/发布/` | Generated publish copies |
| `07.发布文案/<year>年/发布/发布索引.md` | Yearly publish index |
| `07.发布文案/模板/公众号/AI南柯-header-card.md` | Header card template |
| `08.数据反馈/公众号文章库/AI南柯-文章列表.json` | Published article library for related links |

The local script should generate:

- publish-directory Markdown copy;
- local image copies referenced by the article;
- `文章名-公众号封面.png`;
- `文章名-公众号列表摘要.txt`;
- `文章名.blue.wechat.html`;
- `文章名.blue.preview.html`;
- updated draft publish record;
- updated publish-copy archive metadata;
- updated yearly `发布索引.md`;
- a dynamic `相关文章` footer with at most 5 relevant articles.

## Rules

- This skill is only for pre-publish material generation.
- Keep the source draft and source images in place; copy only what the article references.
- The footer must use `相关文章`, not `往期文章`.
- Do not include QR codes, private-domain prompts, or fixed footer blocks in generated WeChat HTML.
- If no related article with an official URL exists, omit the footer.
- Related articles should only include entries with official URLs, exclude entries whose link is still `待补充`, and rank by keyword overlap, recency, and same-workflow relevance.
- When the article has YAML frontmatter or `## 发布记录`, ensure those metadata blocks are not included in the WeChat body.
- If GitHub image hosting fails because `gh` cannot read a token in a sandbox, re-check the actual user environment before concluding credentials are missing.

## Verification

Confirm these artifacts before reporting completion:

- the publish Markdown exists under `07.发布文案/<year>年/发布/`;
- referenced local images were copied beside the publish copy;
- cover, list summary, WeChat HTML, and preview HTML exist;
- the draft and publish copy both contain archive metadata;
- the yearly `发布索引.md` contains the article with link status `待补充` unless a verified URL was supplied;
- the WeChat HTML footer says `相关文章` and contains no QR-code/private-traffic block.

## Extension Support

Custom configurations are supported via EXTEND.md. See **Preferences (EXTEND.md)** for paths and supported keys.
