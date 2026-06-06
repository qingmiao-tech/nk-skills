#!/usr/bin/env python3
"""
将 Markdown 转换为适合微信公众号粘贴的 HTML 片段。

特点：
1. 零第三方依赖
2. 内置 mdnice 风格主题：蓝莹 / 全栈蓝 / 科技蓝
3. 默认输出 HTML 片段，可选完整预览页
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib import error, parse, request


INLINE_CODE_TOKEN = "INLINECODETOKEN"


def build_blue_theme() -> Dict[str, str]:
    return {
        "display_name": "蓝莹",
        "container": (
            "font-family: PingFang SC, Microsoft YaHei, sans-serif;"
            "word-break: break-word;"
            "color: #3d3d3d;"
            "font-size: 16px;"
            "line-height: 1.75;"
        ),
        "p": "margin: 1em 0; color: #666666; line-height: 1.75;",
        "h1": (
            "margin: 1.4em 0 0.9em; padding-bottom: 6px;"
            "border-bottom: 2px solid hsl(216, 100%, 68%);"
            "font-size: 1.7em; font-weight: 400; color: #333333; line-height: 1.4;"
        ),
        "h1_inner": (
            "display: inline-block; background: hsl(216, 100%, 68%); color: #ffffff;"
            "padding: 3px 10px; border-radius: 3px 3px 0 0; margin-right: 3px;"
        ),
        "h2": (
            "margin: 1.3em 0 0.8em; padding-bottom: 4px;"
            "border-bottom: 1px solid hsl(216, 100%, 68%);"
            "font-size: 1.4em; font-weight: 400; color: #333333; line-height: 1.4;"
        ),
        "h3": "margin: 1.2em 0 0.7em; font-size: 1.2em; font-weight: 400; color: #333333; line-height: 1.4;",
        "h4": (
            "width: 80%; margin: 1.6em auto; padding: 10px;"
            "border: 1px solid hsl(216, 100%, 68%); border-top: 4px solid hsl(216, 100%, 68%);"
            "font-size: 1em; font-weight: 400; color: #333333; line-height: 1.7;"
        ),
        "h5": (
            "width: 80%; margin: 1.6em auto; padding: 10px;"
            "background: hsl(216, 100%, 68%); border: 3px double #ffffff;"
            "font-size: 1.3em; font-weight: 400; color: #ffffff; text-align: center; line-height: 1.5;"
        ),
        "h6": (
            "margin: 1.2em 0 0.8em; padding-bottom: 4px;"
            "border-bottom: 1px solid hsl(216, 100%, 68%);"
            "font-size: 1.5em; font-weight: 400; color: hsl(216, 100%, 68%); line-height: 1.4;"
        ),
        "ul": "margin: 1em 0; padding-left: 2em; color: #666666;",
        "ol": "margin: 1em 0; padding-left: 2em; color: #666666;",
        "li": "margin: 0.35em 0; color: #666666; line-height: 1.75;",
        "blockquote": (
            "margin: 1.3em 0; padding: 0.8em 1em;"
            "background: #f9f9f9; border-left: 4px solid hsl(216, 100%, 68%);"
        ),
        "blockquote_p": "margin: 0.35em 0; color: #999999; line-height: 1.7;",
        "hr": "margin: 1.5em auto; width: 90%; border: 0; border-top: 2px dashed hsl(216, 100%, 68%);",
        "pre": (
            "margin: 1.2em 0; padding: 14px 16px; overflow-x: auto;"
            "background: #0f172a; border-radius: 8px; color: #e2e8f0; line-height: 1.6;"
        ),
        "code_block": "font-family: Consolas, Monaco, monospace; font-size: 13px; white-space: pre;",
        "code_lang": "margin-bottom: 8px; color: #93c5fd; font-size: 12px; font-family: Consolas, Monaco, monospace;",
        "code_inline": (
            "padding: 2px 6px; margin: 0 2px; border-radius: 4px;"
            "background: rgba(99, 179, 237, 0.14); color: hsl(216, 100%, 68%);"
            "font-family: Consolas, Monaco, monospace; font-size: 0.92em;"
        ),
        "table": (
            "margin: 1.5em auto; width: 100%; border-collapse: collapse;"
            "font-size: 0.95em; color: #666666;"
        ),
        "th": (
            "padding: 8px 12px; border: 1px solid #d8e8ff;"
            "background: #eef6ff; color: #333333; font-weight: 400; text-align: left;"
        ),
        "td": "padding: 8px 12px; border: 1px solid #d8e8ff; color: #666666; text-align: left;",
        "img": "display: block; width: 90%; margin: 1.3em auto; box-shadow: #cccccc 0 10px 15px;",
        "a": "color: hsl(187, 100%, 45%); text-decoration: none; border-bottom: 1px solid hsl(187, 100%, 45%);",
        "strong": "color: hsl(216, 80%, 44%); font-weight: 600;",
        "em": "font-style: normal; color: #ffffff; background: hsl(244, 100%, 75%); padding: 2px 4px; margin: 0 2px;",
        "del": "color: #999999;",
        "preview_background": "#f3f6fb",
    }


def build_science_blue_theme() -> Dict[str, str]:
    return {
        "display_name": "科技蓝",
        "container": (
            "font-family: PingFang SC, Microsoft YaHei, sans-serif;"
            "word-break: break-word;"
            "color: #2c3e50;"
            "font-size: 15px;"
            "line-height: 1.8;"
        ),
        "p": "margin: 0.9em 10px; color: #3f4c5a; line-height: 1.8; letter-spacing: 0.1em; font-size: 15px;",
        "h1": "margin: 1.6em 0 1em; border-bottom: 2px solid #0e88eb; text-align: center; font-size: 1.4em; line-height: 1.5;",
        "h1_inner": "display: inline-block; color: #0e88eb; font-weight: 700; padding: 3px 10px 1px;",
        "h2": "margin: 1.4em 0 0.8em; text-align: left; font-size: 1em;",
        "h2_inner": "display: inline-block; padding-left: 10px; border-left: 5px solid #0e88eb; color: #0e88eb; font-weight: 700; font-size: 22px;",
        "h3": "margin: 1.3em 0 0.7em; color: #0e88eb; font-size: 18px; font-weight: 700;",
        "h4": "margin: 1.1em 0 0.6em; color: #0e88eb; font-size: 16px; font-weight: 700;",
        "h5": "margin: 1.1em 0 0.6em; color: #0e88eb; font-size: 15px; font-weight: 700;",
        "h6": "margin: 1.1em 0 0.6em; color: #0e88eb; font-size: 14px; font-weight: 700;",
        "ul": "margin: 1em 0; padding-left: 2em; color: #3f4c5a;",
        "ol": "margin: 1em 0; padding-left: 2em; color: #3f4c5a;",
        "li": "margin: 0.35em 0; color: #3f4c5a; line-height: 1.75;",
        "blockquote": (
            "margin: 1.3em 0; padding: 12px 14px;"
            "background: #ffffff; color: #0e88eb;"
            "box-shadow: #84A1A8 0 10px 15px; border-radius: 0 0 10px 10px;"
        ),
        "blockquote_p": "margin: 0.35em 0; color: #0e88eb; line-height: 1.8;",
        "blockquote_prefix": "★",
        "blockquote_suffix": "”",
        "blockquote_symbol_style": "color: #0e88eb; font-size: 2.2em; line-height: 1; font-weight: 700;",
        "blockquote_suffix_style": "color: #0e88eb; font-size: 2.2em; line-height: 1; font-weight: 500; float: right;",
        "hr": "margin: 1.5em auto; border: 0; height: 1px; background-image: linear-gradient(to right, rgba(248,57,41,0), #0e88eb, rgba(248,57,41,0));",
        "pre": (
            "margin: 1.2em 0; padding: 14px 16px; overflow-x: auto;"
            "background: #0b1f35; border-radius: 8px; color: #eaf3ff; line-height: 1.65;"
        ),
        "code_block": "font-family: Consolas, Monaco, monospace; font-size: 13px; white-space: pre;",
        "code_lang": "margin-bottom: 8px; color: #8ed0ff; font-size: 12px; font-family: Consolas, Monaco, monospace;",
        "code_inline": (
            "display: inline-block; padding: 0 4px; border-radius: 2px;"
            "background: rgba(14, 136, 235, 0.1); color: #0e88eb;"
            "font-family: Consolas, Monaco, monospace; font-size: 0.92em;"
        ),
        "table": "margin: 1.5em auto; width: 100%; border-collapse: collapse; font-size: 15px; color: #3f4c5a;",
        "th": "padding: 8px 12px; border: 1px solid #cfe4fb; background: #edf6ff; color: #0e88eb; font-weight: 700; text-align: left;",
        "td": "padding: 8px 12px; border: 1px solid #d7e8f8; color: #3f4c5a; text-align: left;",
        "img": "display: block; width: 85%; height: auto; object-fit: contain; margin: 20px auto; border-radius: 0 0 5px 5px; box-shadow: #84A1A8 0 10px 15px;",
        "a": "color: #0e88eb; text-decoration: none; border-bottom: 0 solid transparent;",
        "strong": "color: #0e88eb; font-weight: 700;",
        "em": "font-style: normal; color: #0e88eb; letter-spacing: 0.3em;",
        "del": "color: #6a88c5;",
        "preview_background": "#eff6ff",
    }


def build_full_stack_blue_theme() -> Dict[str, str]:
    return {
        "display_name": "全栈蓝",
        "container": (
            "font-family: Optima, PingFang SC, Microsoft YaHei, sans-serif;"
            "word-break: break-word;"
            "color: #595959;"
            "font-size: 14px;"
            "line-height: 1.75;"
            "letter-spacing: 1px;"
            "background-image: linear-gradient(90deg, rgba(50, 0, 0, 0.05) 3%, rgba(0, 0, 0, 0) 3%),"
            " linear-gradient(360deg, rgba(50, 0, 0, 0.05) 3%, rgba(0, 0, 0, 0) 3%);"
            "background-size: 20px 20px;"
            "background-position: center center;"
            "padding: 2px 6px;"
        ),
        "p": "margin: 10px 0; color: #595959; line-height: 1.8; letter-spacing: 2px; font-size: 14px; word-spacing: 2px;",
        "h1": "margin: 1.6em 0 1em; font-size: 25px; text-align: left; line-height: 1.4;",
        "h1_inner": "display: inline-block; font-weight: 700; color: #40B8FA;",
        "h2": "display: block; margin: 1.4em 0 1em; border-bottom: 4px solid #40B8FA; line-height: 1.4;",
        "h2_inner": "display: inline-block; color: #40B8FA; font-size: 20px; margin-left: 25px;",
        "h3": "position: relative; margin: 50px 0 20px; text-align: center; font-size: 16px; font-weight: 700; color: #595959; line-height: 1.5;",
        "h3_inner": "display: inline-block; border-bottom: 2px solid rgba(79, 177, 249, 0.65); padding-bottom: 2px;",
        "h4": "margin: 1.2em 0 0.6em; color: #595959; font-size: 14px; font-weight: 700;",
        "h4_inner": "display: inline-block;",
        "h5": "margin: 1.1em 0 0.6em; color: #3594F7; font-size: 14px; font-weight: 700;",
        "h6": "margin: 1.1em 0 0.6em; color: #3594F7; font-size: 14px; font-weight: 700;",
        "ul": "margin: 1em 0; padding-left: 2em; color: #595959; list-style-type: circle;",
        "ol": "margin: 1em 0; padding-left: 2em; color: #595959;",
        "li": "margin: 0.35em 0; color: #595959; line-height: 1.75;",
        "blockquote": (
            "margin: 1.3em 0; padding: 12px 14px;"
            "border: 1px solid rgba(64, 184, 250, 0.4); background: rgba(64, 184, 250, 0.1);"
            "border-radius: 6px; color: #595959;"
        ),
        "blockquote_p": "margin: 0.35em 0; color: #595959; line-height: 1.8;",
        "blockquote_prefix": "❝",
        "blockquote_suffix": "❞",
        "blockquote_symbol_style": "color: rgba(64, 184, 250, 0.5); font-size: 2em; line-height: 1; font-weight: 700;",
        "blockquote_suffix_style": "color: rgba(64, 184, 250, 0.5); font-size: 2em; line-height: 1; font-weight: 700; float: right;",
        "hr": "margin: 1.5em auto; border: 0; height: 2px; background: #3BAAFA;",
        "pre": (
            "margin: 1.2em 0; padding: 14px 16px; overflow-x: auto;"
            "background: #10243a; border-radius: 8px; color: #edf6ff; line-height: 1.65;"
        ),
        "code_block": "font-family: Consolas, Monaco, monospace; font-size: 13px; white-space: pre;",
        "code_lang": "margin-bottom: 8px; color: #86d3ff; font-size: 12px; font-family: Consolas, Monaco, monospace;",
        "code_inline": (
            "display: inline-block; padding: 0 4px; border-radius: 2px;"
            "background: rgba(59, 170, 250, 0.1); color: #3594F7;"
            "font-family: Consolas, Monaco, monospace; font-size: 0.92em;"
        ),
        "table": "margin: 1.5em auto; width: 100%; border-collapse: collapse; font-size: 14px; color: #595959;",
        "th": "padding: 8px 12px; border: 1px solid #cfe4fb; background: #edf7ff; color: #3594F7; font-weight: 700; text-align: left;",
        "td": "padding: 8px 12px; border: 1px solid #d7e8f8; color: #595959; text-align: left;",
        "img": "display: block; width: 90%; object-fit: contain; margin: 20px auto; border-radius: 6px; box-shadow: 2px 4px 7px #999999;",
        "a": "color: #40B8FA; text-decoration: none; border-bottom: 1px solid #3BAAFA;",
        "strong": "color: #3594F7; font-weight: 700;",
        "em": "font-style: normal; color: #3594F7; font-weight: 700;",
        "del": "color: #3594F7;",
        "preview_background": "#f4f9ff",
    }


THEMES = {
    "blue": build_blue_theme(),
    "scienceBlue": build_science_blue_theme(),
    "fullStackBlue": build_full_stack_blue_theme(),
}


@dataclass
class Block:
    kind: str
    lines: List[str]


class MarkdownToWechatHtml:
    def __init__(self, theme_name: str = "blue", promote_h2_to_h1: bool = False) -> None:
        if theme_name not in THEMES:
            raise ValueError(f"不支持的主题: {theme_name}")
        self.theme_name = theme_name
        self.theme = THEMES[theme_name]
        self.promote_h2_to_h1 = promote_h2_to_h1

    def convert(self, markdown_text: str) -> str:
        blocks = self._parse_blocks(markdown_text.replace("\r\n", "\n"))
        rendered = [self._render_block(block) for block in blocks]
        body = "\n".join(chunk for chunk in rendered if chunk)
        return f'<section id="nice" data-theme="{self.theme_name}" style="{self.theme["container"]}">\n{body}\n</section>'

    def wrap_full_html(self, fragment: str, title: str) -> str:
        safe_title = html.escape(title)
        background = self.theme.get("preview_background", "#f3f6fb")
        return (
            "<!DOCTYPE html>\n"
            '<html lang="zh-CN">\n<head>\n'
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"  <title>{safe_title}</title>\n"
            "</head>\n"
            f'<body style="margin: 0; background: {background};">\n'
            '  <div style="max-width: 860px; margin: 0 auto; padding: 24px 16px;">\n'
            '    <div style="background: #ffffff; border-radius: 12px; padding: 28px 24px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);">\n'
            f"{fragment}\n"
            "    </div>\n"
            "  </div>\n"
            "</body>\n</html>\n"
        )

    def _parse_blocks(self, text: str) -> List[Block]:
        lines = text.split("\n")
        blocks: List[Block] = []
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            if stripped.startswith("```"):
                block_lines = [line]
                i += 1
                while i < len(lines):
                    block_lines.append(lines[i])
                    if lines[i].strip().startswith("```"):
                        i += 1
                        break
                    i += 1
                blocks.append(Block("code", block_lines))
                continue

            if re.match(r"^\|?.+\|.+$", stripped) and i + 1 < len(lines) and self._is_table_separator(lines[i + 1].strip()):
                table_lines = [line, lines[i + 1]]
                i += 2
                while i < len(lines):
                    next_line = lines[i].strip()
                    if not next_line or "|" not in next_line:
                        break
                    table_lines.append(lines[i])
                    i += 1
                blocks.append(Block("table", table_lines))
                continue

            if re.match(r"^(#{1,6})\s+.+$", stripped):
                blocks.append(Block("heading", [line]))
                i += 1
                continue

            if re.match(r"^([-*_]\s?){3,}$", stripped):
                blocks.append(Block("hr", [line]))
                i += 1
                continue

            if stripped.startswith(">"):
                quote_lines = [line]
                i += 1
                while i < len(lines) and lines[i].strip().startswith(">"):
                    quote_lines.append(lines[i])
                    i += 1
                blocks.append(Block("blockquote", quote_lines))
                continue

            if re.match(r"^(\-|\*|\+)\s+.+$", stripped):
                list_lines = [line]
                i += 1
                while i < len(lines) and re.match(r"^(\-|\*|\+)\s+.+$", lines[i].strip()):
                    list_lines.append(lines[i])
                    i += 1
                blocks.append(Block("ul", list_lines))
                continue

            if re.match(r"^\d+\.\s+.+$", stripped):
                list_lines = [line]
                i += 1
                while i < len(lines) and re.match(r"^\d+\.\s+.+$", lines[i].strip()):
                    list_lines.append(lines[i])
                    i += 1
                blocks.append(Block("ol", list_lines))
                continue

            paragraph_lines = [line]
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if not next_stripped or self._starts_new_block(next_stripped):
                    break
                paragraph_lines.append(lines[i])
                i += 1
            blocks.append(Block("paragraph", paragraph_lines))

        return blocks

    def _starts_new_block(self, stripped: str) -> bool:
        return any(
            (
                stripped.startswith("```"),
                bool(re.match(r"^(#{1,6})\s+.+$", stripped)),
                bool(re.match(r"^([-*_]\s?){3,}$", stripped)),
                stripped.startswith(">"),
                bool(re.match(r"^(\-|\*|\+)\s+.+$", stripped)),
                bool(re.match(r"^\d+\.\s+.+$", stripped)),
            )
        )

    def _is_table_separator(self, line: str) -> bool:
        if "|" not in line:
            return False
        clean = line.replace("|", "").replace(":", "").replace("-", "").strip()
        return clean == ""

    def _render_block(self, block: Block) -> str:
        if block.kind == "heading":
            return self._render_heading(block.lines[0])
        if block.kind == "paragraph":
            text = " ".join(item.strip() for item in block.lines)
            return f'<p style="{self.theme["p"]}">{self._render_inline(text)}</p>'
        if block.kind == "ul":
            items = [re.sub(r"^(\-|\*|\+)\s+", "", item.strip()) for item in block.lines]
            inner = "".join(f'<li style="{self.theme["li"]}">{self._render_inline(item)}</li>' for item in items)
            return f'<ul style="{self.theme["ul"]}">{inner}</ul>'
        if block.kind == "ol":
            items = [re.sub(r"^\d+\.\s+", "", item.strip()) for item in block.lines]
            inner = "".join(f'<li style="{self.theme["li"]}">{self._render_inline(item)}</li>' for item in items)
            return f'<ol style="{self.theme["ol"]}">{inner}</ol>'
        if block.kind == "blockquote":
            return self._render_blockquote(block.lines)
        if block.kind == "code":
            return self._render_code_block(block.lines)
        if block.kind == "table":
            return self._render_table(block.lines)
        if block.kind == "hr":
            return f'<hr style="{self.theme["hr"]}">'
        return ""

    def _render_heading(self, line: str) -> str:
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if not match:
            return ""
        level = len(match.group(1))
        content = self._render_inline(match.group(2).strip())

        if level == 1:
            return f'<h1 style="{self.theme["h1"]}"><span style="{self.theme["h1_inner"]}">{content}</span></h1>'

        if level == 2 and self.promote_h2_to_h1:
            return f'<h1 style="{self.theme["h1"]}"><span style="{self.theme["h1_inner"]}">{content}</span></h1>'

        if level == 2 and "h2_inner" in self.theme:
            return f'<h2 style="{self.theme["h2"]}"><span style="{self.theme["h2_inner"]}">{content}</span></h2>'

        if level == 3 and "h3_inner" in self.theme:
            return f'<h3 style="{self.theme["h3"]}"><span style="{self.theme["h3_inner"]}">{content}</span></h3>'

        if level == 4 and "h4_inner" in self.theme:
            return f'<h4 style="{self.theme["h4"]}"><span style="{self.theme["h4_inner"]}">{content}</span></h4>'

        tag = f"h{level}"
        style = self.theme.get(tag, self.theme["h3"])
        return f"<{tag} style=\"{style}\">{content}</{tag}>"

    def _render_blockquote(self, lines: Sequence[str]) -> str:
        items = []
        for raw in lines:
            content = re.sub(r"^>\s?", "", raw.strip())
            if not content:
                continue
            items.append(f'<p style="{self.theme["blockquote_p"]}">{self._render_inline(content)}</p>')

        prefix = ""
        if "blockquote_prefix" in self.theme:
            prefix = f'<div style="{self.theme["blockquote_symbol_style"]}">{html.escape(self.theme["blockquote_prefix"])}</div>'

        suffix = ""
        if "blockquote_suffix" in self.theme:
            suffix = f'<div style="{self.theme["blockquote_suffix_style"]}">{html.escape(self.theme["blockquote_suffix"])}</div>'

        return f'<blockquote style="{self.theme["blockquote"]}">{prefix}{"".join(items)}{suffix}</blockquote>'

    def _render_code_block(self, lines: Sequence[str]) -> str:
        lang = lines[0].strip()[3:].strip()
        code_lines = list(lines[1:])
        if code_lines and code_lines[-1].strip().startswith("```"):
            code_lines = code_lines[:-1]
        code_text = "\n".join(code_lines)
        safe_code = html.escape(code_text)
        lang_label = ""
        if lang:
            lang_label = f'<div style="{self.theme["code_lang"]}">{html.escape(lang)}</div>'
        return (
            f'<pre style="{self.theme["pre"]}">'
            f"{lang_label}<code style=\"{self.theme['code_block']}\">{safe_code}</code></pre>"
        )

    def _render_table(self, lines: Sequence[str]) -> str:
        headers = self._split_table_row(lines[0])
        data_rows = [self._split_table_row(line) for line in lines[2:]]

        thead = "".join(f'<th style="{self.theme["th"]}">{self._render_inline(cell)}</th>' for cell in headers)
        body_rows = []
        for row in data_rows:
            cols = "".join(f'<td style="{self.theme["td"]}">{self._render_inline(cell)}</td>' for cell in row)
            body_rows.append(f"<tr>{cols}</tr>")

        return (
            f'<table style="{self.theme["table"]}">'
            f"<thead><tr>{thead}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody>"
            "</table>"
        )

    def _split_table_row(self, row: str) -> List[str]:
        trimmed = row.strip().strip("|")
        return [cell.strip() for cell in trimmed.split("|")]

    def _render_inline(self, text: str) -> str:
        code_values: List[str] = []

        def preserve_code(match: re.Match[str]) -> str:
            code_values.append(match.group(1))
            return f"{INLINE_CODE_TOKEN}{len(code_values) - 1}__"

        text = re.sub(r"`([^`]+)`", preserve_code, text)
        text = html.escape(text)

        text = re.sub(
            r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]+)&quot;)?\)",
            lambda m: self._render_image(m.group(1), m.group(2), m.group(3)),
            text,
        )
        text = re.sub(
            r"\[([^\]]+)\]\(([^)\s]+)\)",
            lambda m: f'<a href="{html.escape(m.group(2), quote=True)}" style="{self.theme["a"]}">{m.group(1)}</a>',
            text,
        )
        text = re.sub(r"\*\*([^*]+)\*\*", lambda m: f'<strong style="{self.theme["strong"]}">{m.group(1)}</strong>', text)
        text = re.sub(r"__([^_]+)__", lambda m: f'<strong style="{self.theme["strong"]}">{m.group(1)}</strong>', text)
        text = re.sub(r"~~([^~]+)~~", lambda m: f'<del style="{self.theme["del"]}">{m.group(1)}</del>', text)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", lambda m: f'<em style="{self.theme["em"]}">{m.group(1)}</em>', text)
        text = re.sub(r"(?<!_)_([^_]+)_(?!_)", lambda m: f'<em style="{self.theme["em"]}">{m.group(1)}</em>', text)

        for index, code_text in enumerate(code_values):
            placeholder = f"{INLINE_CODE_TOKEN}{index}__"
            rendered_code = f'<code style="{self.theme["code_inline"]}">{html.escape(code_text)}</code>'
            text = text.replace(placeholder, rendered_code)

        return text

    def _render_image(self, alt_text: str, src: str, title: str | None) -> str:
        attrs = [
            f'src="{html.escape(src, quote=True)}"',
            f'alt="{html.escape(alt_text, quote=True)}"',
            f'style="{self.theme["img"]}"',
        ]
        if title:
            attrs.append(f'title="{html.escape(title, quote=True)}"')
        return f"<img {' '.join(attrs)} />"


def derive_output_path(input_path: Path, explicit_output: str | None, suffix: str) -> Path:
    if explicit_output:
        return Path(explicit_output)
    return input_path.with_suffix("").with_name(f"{input_path.stem}{suffix}")


def derive_batch_output_path(source_path: Path, source_root: Path, output_root: Path | None, suffix: str) -> Path:
    target_root = output_root if output_root else source_path.parent
    relative_parent = source_path.parent.relative_to(source_root) if output_root else Path()
    return target_root / relative_parent / f"{source_path.stem}{suffix}"


def copy_to_clipboard(content: str) -> None:
    if sys.platform.startswith("win"):
        subprocess.run(["clip"], input=content.encode("utf-16le"), check=True)
        return
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=content, text=True, check=True)
        return

    candidates = (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"])
    for command in candidates:
        try:
            subprocess.run(command, input=content, text=True, check=True)
            return
        except FileNotFoundError:
            continue

    raise RuntimeError("当前环境缺少可用的剪贴板命令")


def collect_markdown_files(input_dir: Path, recursive: bool, pattern: str) -> List[Path]:
    iterator = input_dir.rglob(pattern) if recursive else input_dir.glob(pattern)
    files = sorted(path for path in iterator if path.is_file())
    return files


@dataclass
class ConversionResult:
    title: str
    fragment_path: Path
    preview_path: Path
    fragment_html: str


class ImageUploader:
    def upload(self, image_path: Path) -> str:
        raise NotImplementedError


class GitHubImageUploader(ImageUploader):
    def __init__(
        self,
        *,
        token: str,
        repo: str,
        branch: str = "main",
        directory: str = "images",
        cdn: str = "jsdelivr",
        commit_message: str = "chore: upload image",
    ) -> None:
        if "/" not in repo:
            raise ValueError("GitHub 仓库格式必须为 owner/repo")
        self.token = token
        self.repo = repo
        self.owner, self.repo_name = repo.split("/", 1)
        self.branch = branch
        self.directory = directory.strip("/").replace("\\", "/")
        self.cdn = cdn
        self.commit_message = commit_message

    def upload(self, image_path: Path) -> str:
        content = image_path.read_bytes()
        digest = hashlib.sha1(content).hexdigest()[:16]
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", image_path.stem).strip("-") or "image"
        remote_name = f"{safe_name}-{digest}{image_path.suffix.lower()}"
        remote_path = f"{self.directory}/{remote_name}" if self.directory else remote_name

        url = f"https://api.github.com/repos/{self.owner}/{self.repo_name}/contents/{remote_path}"
        payload = {
            "message": self.commit_message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.branch,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "wechat-mdnice-blue-html",
        }
        req = request.Request(url, data=data, headers=headers, method="PUT")

        try:
            with request.urlopen(req, timeout=60) as resp:
                response = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 422 and "sha" in detail and "supplied" in detail:
                return self._cdn_url(remote_path, "")
            raise RuntimeError(f"GitHub 上传失败: HTTP {exc.code} {detail}") from exc

        content_info = response.get("content", {})
        download_url = content_info.get("download_url")
        if not download_url:
            raise RuntimeError("GitHub 上传成功，但未返回下载地址")

        return self._cdn_url(remote_path, download_url)

    def _cdn_url(self, remote_path: str, download_url: str) -> str:
        if self.cdn == "raw":
            if not download_url:
                return f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/{remote_path}"
            return download_url
        if self.cdn == "jsdelivr":
            return f"https://cdn.jsdelivr.net/gh/{self.repo}@{self.branch}/{remote_path}"
        raise ValueError(f"不支持的 GitHub CDN 类型: {self.cdn}")


class ImgBBUploader(ImageUploader):
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def upload(self, image_path: Path) -> str:
        boundary = f"----wechatmdnice{hashlib.md5(str(image_path).encode('utf-8')).hexdigest()}"
        file_bytes = image_path.read_bytes()
        parts = [
            f"--{boundary}\r\n".encode("utf-8"),
            b'Content-Disposition: form-data; name="image"; filename="' + image_path.name.encode("utf-8") + b'"\r\n',
            b"Content-Type: application/octet-stream\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}\r\n".encode("utf-8"),
            b'Content-Disposition: form-data; name="name"\r\n\r\n',
            image_path.stem.encode("utf-8"),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
        data = b"".join(parts)
        url = f"https://api.imgbb.com/1/upload?key={parse.quote(self.api_key)}"
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "wechat-mdnice-blue-html",
        }
        req = request.Request(url, data=data, headers=headers, method="POST")

        try:
            with request.urlopen(req, timeout=60) as resp:
                response = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ImgBB 上传失败: HTTP {exc.code} {detail}") from exc

        if not response.get("success"):
            raise RuntimeError(f"ImgBB 上传失败: {response}")
        image_url = response.get("data", {}).get("url")
        if not image_url:
            raise RuntimeError("ImgBB 上传成功，但未返回图片地址")
        return image_url


def create_image_uploader(args: argparse.Namespace) -> Optional[ImageUploader]:
    if args.image_hosting == "none":
        return None

    if args.image_hosting == "github":
        token = args.github_token or os.environ.get("GITHUB_TOKEN")
        repo = args.github_repo or os.environ.get("GITHUB_REPO")
        branch = args.github_branch or os.environ.get("GITHUB_BRANCH", "main")
        directory = args.github_path or os.environ.get("GITHUB_IMAGE_PATH", "images")
        cdn = args.github_cdn or os.environ.get("GITHUB_CDN", "jsdelivr")
        if not token or not repo:
            raise ValueError("使用 GitHub 图床需要提供 --github-token/环境变量 GITHUB_TOKEN 和 --github-repo/环境变量 GITHUB_REPO")
        return GitHubImageUploader(
            token=token,
            repo=repo,
            branch=branch,
            directory=directory,
            cdn=cdn,
        )

    if args.image_hosting == "imgbb":
        api_key = args.imgbb_key or os.environ.get("IMGBB_API_KEY")
        if not api_key:
            raise ValueError("使用 ImgBB 图床需要提供 --imgbb-key 或环境变量 IMGBB_API_KEY")
        return ImgBBUploader(api_key=api_key)

    raise ValueError(f"不支持的图床类型: {args.image_hosting}")


def process_markdown_images(
    markdown_text: str,
    *,
    base_dir: Path,
    uploader: Optional[ImageUploader],
    upload_remote_images: bool = False,
) -> str:
    if uploader is None:
        return markdown_text

    pattern = r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)"

    def replace(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        raw_src = match.group(2)
        title = match.group(3)

        if re.match(r"^(https?:)?//", raw_src):
            return match.group(0) if not upload_remote_images else match.group(0)

        if raw_src.startswith("data:"):
            return match.group(0)

        resolved = Path(raw_src)
        if not resolved.is_absolute():
            resolved = (base_dir / resolved).resolve()

        if not resolved.exists():
            return match.group(0)

        uploaded_url = uploader.upload(resolved)
        if title:
            return f'![{alt_text}]({uploaded_url} "{title}")'
        return f"![{alt_text}]({uploaded_url})"

    return re.sub(pattern, replace, markdown_text)


def convert_markdown_to_files(
    markdown_text: str,
    *,
    title: str,
    theme_name: str,
    fragment_path: Path,
    preview_path: Path,
    image_uploader: Optional[ImageUploader] = None,
    image_base_dir: Optional[Path] = None,
    promote_h2_to_h1: bool = False,
) -> ConversionResult:
    if image_uploader:
        base_dir = image_base_dir or Path.cwd()
        markdown_text = process_markdown_images(
            markdown_text,
            base_dir=base_dir,
            uploader=image_uploader,
        )

    renderer = MarkdownToWechatHtml(
        theme_name=theme_name,
        promote_h2_to_h1=promote_h2_to_h1,
    )
    fragment = renderer.convert(markdown_text)

    fragment_path.parent.mkdir(parents=True, exist_ok=True)
    fragment_path.write_text(fragment, encoding="utf-8")

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(renderer.wrap_full_html(fragment, title), encoding="utf-8")

    return ConversionResult(
        title=title,
        fragment_path=fragment_path,
        preview_path=preview_path,
        fragment_html=fragment,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 Markdown 转换为微信公众号 HTML")
    parser.add_argument("--input", help="Markdown 文件路径")
    parser.add_argument("--input-dir", help="批量转换目录")
    parser.add_argument("--markdown-text", help="直接传入 Markdown 文本")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取 Markdown 文本")
    parser.add_argument("--output", help="HTML 片段输出路径，默认与输入同目录")
    parser.add_argument("--output-dir", help="批量输出目录")
    parser.add_argument("--full-output", help="完整预览 HTML 输出路径")
    parser.add_argument("--title", help="文档标题，默认使用文件名")
    parser.add_argument("--theme", default="blue", choices=sorted(THEMES.keys()), help="主题名称")
    parser.add_argument(
        "--promote-h2-to-h1",
        action="store_true",
        help="将二级标题按一级标题样式渲染，默认 blue 主题自动开启",
    )
    parser.add_argument("--list-themes", action="store_true", help="列出所有可用主题")
    parser.add_argument("--copy", action="store_true", help="转换后将 HTML 片段复制到剪贴板")
    parser.add_argument("--recursive", action="store_true", help="批量转换时递归扫描子目录")
    parser.add_argument("--pattern", default="*.md", help="批量转换时匹配文件名，默认 *.md")
    parser.add_argument("--base-dir", help="原始 Markdown 文本或 stdin 模式下，解析相对图片路径的基目录")
    parser.add_argument("--image-hosting", default="none", choices=["none", "github", "imgbb"], help="图片上传方式")
    parser.add_argument("--github-token", help="GitHub Token，未提供时读取环境变量 GITHUB_TOKEN")
    parser.add_argument("--github-repo", help="GitHub 仓库 owner/repo，未提供时读取环境变量 GITHUB_REPO")
    parser.add_argument("--github-branch", help="GitHub 分支，默认 main")
    parser.add_argument("--github-path", help="GitHub 仓库内图片目录，默认 images")
    parser.add_argument("--github-cdn", default="jsdelivr", choices=["jsdelivr", "raw"], help="GitHub 图床返回地址类型")
    parser.add_argument("--imgbb-key", help="ImgBB API Key，未提供时读取环境变量 IMGBB_API_KEY")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_themes:
        for key, theme in THEMES.items():
            print(f"{key}\t{theme['display_name']}")
        return

    input_flags = [bool(args.input), bool(args.input_dir), bool(args.markdown_text), bool(args.stdin)]
    if sum(input_flags) != 1:
        parser.error("--input、--input-dir、--markdown-text、--stdin 必须且只能提供一个")

    if args.input_dir and (args.output or args.full_output):
        parser.error("批量转换时请使用 --output-dir，不要使用 --output 或 --full-output")

    image_uploader = create_image_uploader(args)
    promote_h2_to_h1 = args.promote_h2_to_h1 or args.theme == "blue"

    if args.input_dir:
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            raise FileNotFoundError(f"输入目录不存在: {input_dir}")

        output_dir = Path(args.output_dir) if args.output_dir else None
        files = collect_markdown_files(input_dir, args.recursive, args.pattern)
        if not files:
            raise FileNotFoundError(f"目录中没有匹配到 Markdown 文件: {input_dir} ({args.pattern})")

        results: List[ConversionResult] = []
        for file_path in files:
            markdown_text = file_path.read_text(encoding="utf-8")
            title = file_path.stem
            fragment_path = derive_batch_output_path(file_path, input_dir, output_dir, f".{args.theme}.wechat.html")
            preview_path = derive_batch_output_path(file_path, input_dir, output_dir, f".{args.theme}.preview.html")
            result = convert_markdown_to_files(
                markdown_text,
                title=title,
                theme_name=args.theme,
                fragment_path=fragment_path,
                preview_path=preview_path,
                image_uploader=image_uploader,
                image_base_dir=file_path.parent,
                promote_h2_to_h1=promote_h2_to_h1,
            )
            results.append(result)
            print(f"已生成公众号 HTML 片段: {result.fragment_path}")
            print(f"已生成预览 HTML: {result.preview_path}")

        if args.copy:
            copy_to_clipboard(results[-1].fragment_html)
            print(f"已复制最后一个转换结果到剪贴板: {results[-1].title}")
        print(f"批量转换完成，共 {len(results)} 个文件")
        return

    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        markdown_text = input_path.read_text(encoding="utf-8")
        title = args.title or input_path.stem
        fragment_path = derive_output_path(input_path, args.output, f".{args.theme}.wechat.html")
        preview_path = Path(args.full_output) if args.full_output else derive_output_path(input_path, None, f".{args.theme}.preview.html")
        image_base_dir = input_path.parent
    elif args.markdown_text:
        markdown_text = args.markdown_text
        title = args.title or "markdown-text"
        output_root = Path(args.output_dir) if args.output_dir else Path.cwd()
        fragment_path = Path(args.output) if args.output else output_root / f"{title}.{args.theme}.wechat.html"
        preview_path = Path(args.full_output) if args.full_output else output_root / f"{title}.{args.theme}.preview.html"
        image_base_dir = Path(args.base_dir).resolve() if args.base_dir else Path.cwd()
    else:
        markdown_text = sys.stdin.read()
        if not markdown_text.strip():
            raise ValueError("标准输入为空")
        title = args.title or "stdin-markdown"
        output_root = Path(args.output_dir) if args.output_dir else Path.cwd()
        fragment_path = Path(args.output) if args.output else output_root / f"{title}.{args.theme}.wechat.html"
        preview_path = Path(args.full_output) if args.full_output else output_root / f"{title}.{args.theme}.preview.html"
        image_base_dir = Path(args.base_dir).resolve() if args.base_dir else Path.cwd()

    result = convert_markdown_to_files(
        markdown_text,
        title=title,
        theme_name=args.theme,
        fragment_path=fragment_path,
        preview_path=preview_path,
        image_uploader=image_uploader,
        image_base_dir=image_base_dir,
        promote_h2_to_h1=promote_h2_to_h1,
    )
    print(f"已生成公众号 HTML 片段: {result.fragment_path}")
    print(f"已生成预览 HTML: {result.preview_path}")

    if args.copy:
        copy_to_clipboard(result.fragment_html)
        print("已复制 HTML 片段到剪贴板")


if __name__ == "__main__":
    main()
