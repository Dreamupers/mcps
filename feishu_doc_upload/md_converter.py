"""
Markdown to Feishu Blocks Converter (Standalone)

Converts Markdown content into Feishu document block JSON representation.
Extracted from feishu-doc-tools/scripts/md_to_feishu.py.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

try:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token
except ImportError:
    print(
        "Error: markdown-it-py not found. Install: pip install markdown-it-py",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from mdit_py_plugins.dollarmath import dollarmath_plugin
except ImportError:
    dollarmath_plugin = None


logger = logging.getLogger(__name__)

# Markdown language name -> Feishu language code
LANGUAGE_MAP = {
    "python": 49, "py": 49,
    "javascript": 30, "js": 30,
    "typescript": 63, "ts": 63,
    "java": 29,
    "cpp": 9, "c++": 9,
    "c": 10,
    "go": 22, "golang": 22,
    "rust": 53, "rs": 53,
    "bash": 7, "sh": 7,
    "shell": 60,
    "json": 28,
    "html": 24,
    "css": 12,
    "sql": 56,
    "yaml": 67, "yml": 67,
    "xml": 66,
    "markdown": 39, "md": 39,
    "dockerfile": 18,
    "php": 43,
    "ruby": 52, "rb": 52,
    "swift": 61,
    "kotlin": 32,
    "scala": 57,
    "r": 50,
    "perl": 44,
    "lua": 36,
    "matlab": 37,
}


class MarkdownToFeishuConverter:
    """Converts a Markdown file into Feishu block JSON batches."""

    def __init__(
        self,
        md_file: Path,
        doc_id: str,
        batch_size: int = 200,
        image_mode: str = "local",
        max_text_length: int = 2000,
    ):
        self.md_file = md_file
        self.doc_id = doc_id
        self.batch_size = batch_size
        self.image_mode = image_mode
        self.max_text_length = max_text_length

        self.blocks: List[Dict[str, Any]] = []
        self.images: List[Dict[str, Any]] = []
        self.md_parser = MarkdownIt().enable("table")
        if dollarmath_plugin is not None:
            dollarmath_plugin(self.md_parser, double_inline=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self) -> Dict[str, Any]:
        try:
            content = self.md_file.read_text(encoding="utf-8")
            logger.info(f"Read file: {self.md_file} ({len(content)} chars)")

            tokens = self.md_parser.parse(content)
            logger.info(f"Parsed {len(tokens)} tokens")

            self._process_tokens(tokens)
            logger.info(f"Generated {len(self.blocks)} blocks")

            batches = self._create_batches()
            logger.info(f"Created {len(batches)} batches")

            return {
                "success": True,
                "documentId": self.doc_id,
                "batches": batches,
                "images": self.images,
                "metadata": {
                    "totalBlocks": len(self.blocks),
                    "totalBatches": len(batches),
                    "totalImages": len(self.images),
                },
            }
        except Exception as e:
            logger.error(f"Conversion failed: {e}", exc_info=True)
            return {"success": False, "error": str(e), "errorType": type(e).__name__}

    # ------------------------------------------------------------------
    # Token processing
    # ------------------------------------------------------------------

    def _process_tokens(self, tokens: List[Token]):
        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token.type == "heading_open":
                level = int(token.tag[1])
                i = self._process_heading(tokens, i, level)
            elif token.type == "paragraph_open":
                i = self._process_paragraph(tokens, i)
            elif token.type == "fence":
                self._process_code_block(token)
                i += 1
            elif token.type == "bullet_list_open":
                i = self._process_list(tokens, i, ordered=False)
            elif token.type == "ordered_list_open":
                i = self._process_list(tokens, i, ordered=True)
            elif token.type == "blockquote_open":
                i = self._process_blockquote(tokens, i)
            elif token.type == "table_open":
                i = self._process_table(tokens, i)
            elif token.type in ("math_block", "math_block_double"):
                self._process_math_block(token)
                i += 1
            else:
                i += 1

    # ------------------------------------------------------------------
    # Block processors
    # ------------------------------------------------------------------

    def _process_heading(self, tokens: List[Token], start: int, level: int) -> int:
        inline = tokens[start + 1]
        content = self._extract_inline_text(inline)
        self.blocks.append({
            "blockType": f"heading{level}",
            "options": {"heading": {"level": level, "content": content}},
        })
        return start + 3

    def _process_paragraph(self, tokens: List[Token], start: int) -> int:
        inline = tokens[start + 1]
        text_styles = self._extract_inline_styles(inline)

        if not text_styles or all(
            not s.get("text", "").strip() and not s.get("equation", "")
            for s in text_styles
        ):
            return start + 3

        total_len = sum(len(s.get("text", "") or s.get("equation", "")) for s in text_styles)
        if total_len > self.max_text_length:
            self._split_long_paragraph(text_styles)
        else:
            self.blocks.append({
                "blockType": "text",
                "options": {"text": {"textStyles": text_styles, "align": 1}},
            })
        return start + 3

    def _process_code_block(self, token: Token):
        code = token.content.rstrip("\n")
        lang = LANGUAGE_MAP.get(token.info.strip().lower(), 1)
        self.blocks.append({
            "blockType": "code",
            "options": {"code": {"code": code, "language": lang, "wrap": False}},
        })

    def _process_list(self, tokens: List[Token], start: int, ordered: bool) -> int:
        i = start + 1
        while i < len(tokens):
            token = tokens[i]
            if token.type in ("bullet_list_close", "ordered_list_close"):
                return i + 1
            if token.type == "list_item_open":
                inline = tokens[i + 2]
                text_styles = self._extract_inline_styles(inline)
                self.blocks.append({
                    "blockType": "list",
                    "options": {"list": {"textStyles": text_styles, "isOrdered": ordered, "align": 1}},
                })
                i += 5
            else:
                i += 1
        return i

    def _process_blockquote(self, tokens: List[Token], start: int) -> int:
        i = start + 1
        lines: List[str] = []
        while i < len(tokens):
            if tokens[i].type == "blockquote_close":
                break
            if tokens[i].type == "paragraph_open":
                lines.append(self._extract_inline_text(tokens[i + 1]))
                i += 3
            else:
                i += 1

        content = "\n".join(f"> {line}" for line in lines)
        self.blocks.append({
            "blockType": "text",
            "options": {"text": {"textStyles": [{"text": content, "style": {}}], "align": 1}},
        })
        return i + 1

    def _process_table(self, tokens: List[Token], start: int) -> int:
        i = start + 1
        headers: List[str] = []
        rows: List[List[str]] = []

        while i < len(tokens):
            token = tokens[i]
            if token.type == "table_close":
                break

            if token.type == "thead_open":
                i += 2  # thead_open, tr_open
                while i < len(tokens) and tokens[i].type != "tr_close":
                    if tokens[i].type == "th_open":
                        headers.append(self._extract_inline_text(tokens[i + 1]))
                        i += 3
                    else:
                        i += 1
                i += 2  # tr_close, thead_close

            elif token.type == "tbody_open":
                i += 1
                while i < len(tokens) and tokens[i].type != "tbody_close":
                    if tokens[i].type == "tr_open":
                        row: List[str] = []
                        i += 1
                        while i < len(tokens) and tokens[i].type != "tr_close":
                            if tokens[i].type == "td_open":
                                row.append(self._extract_inline_text(tokens[i + 1]))
                                i += 3
                            else:
                                i += 1
                        rows.append(row)
                        i += 1
                    else:
                        i += 1
            else:
                i += 1

        col_size = len(headers) if headers else 0
        row_size = len(rows) + (1 if headers else 0)
        if col_size == 0 or row_size == 0:
            return i + 1

        table_block: Dict[str, Any] = {
            "blockType": "table",
            "options": {"table": {"columnSize": col_size, "rowSize": row_size, "cells": []}},
        }
        cells = table_block["options"]["table"]["cells"]

        for ci, ht in enumerate(headers):
            cells.append({
                "coordinate": {"row": 0, "column": ci},
                "content": {
                    "blockType": "text",
                    "options": {"text": {"textStyles": [{"text": ht, "style": {"bold": True}}], "align": 1}},
                },
            })

        for ri, rd in enumerate(rows):
            for ci, ct in enumerate(rd):
                cells.append({
                    "coordinate": {"row": ri + 1, "column": ci},
                    "content": {
                        "blockType": "text",
                        "options": {"text": {"textStyles": [{"text": ct, "style": {}}], "align": 1}},
                    },
                })

        self.blocks.append(table_block)
        logger.info(f"Created table: {row_size}x{col_size}")
        return i + 1

    def _process_math_block(self, token: Token):
        eq = token.content.strip()
        if eq:
            self.blocks.append({
                "blockType": "text",
                "options": {"text": {"textStyles": [{"equation": eq, "style": {}}], "align": 1}},
            })

    # ------------------------------------------------------------------
    # Inline helpers
    # ------------------------------------------------------------------

    def _extract_inline_text(self, inline_token: Token) -> str:
        if not inline_token.children:
            return inline_token.content
        parts: List[str] = []
        for child in inline_token.children:
            if child.type == "text":
                parts.append(child.content)
            elif child.type == "code_inline":
                parts.append(f"`{child.content}`")
            elif child.type in ("math_inline", "math_inline_double"):
                parts.append(f"${child.content}$")
            elif child.type == "image":
                parts.append(f"[图片: {child.attrGet('alt') or 'image'}]")
        return "".join(parts)

    def _extract_inline_styles(self, inline_token: Token) -> List[Dict[str, Any]]:
        if not inline_token.children:
            return [{"text": inline_token.content, "style": {}}]

        styles: List[Dict[str, Any]] = []
        cur_style: Dict[str, Any] = {}
        cur_text: List[str] = []

        def _flush():
            if cur_text:
                styles.append({"text": "".join(cur_text), "style": cur_style.copy()})
                cur_text.clear()

        for child in inline_token.children:
            if child.type == "text":
                cur_text.append(child.content)
            elif child.type == "code_inline":
                _flush()
                styles.append({"text": child.content, "style": {**cur_style, "inline_code": True}})
            elif child.type == "strong_open":
                _flush()
                cur_style["bold"] = True
            elif child.type == "strong_close":
                _flush()
                cur_style.pop("bold", None)
            elif child.type == "em_open":
                _flush()
                cur_style["italic"] = True
            elif child.type == "em_close":
                _flush()
                cur_style.pop("italic", None)
            elif child.type == "s_open":
                _flush()
                cur_style["strikethrough"] = True
            elif child.type == "s_close":
                _flush()
                cur_style.pop("strikethrough", None)
            elif child.type in ("math_inline", "math_inline_double"):
                _flush()
                styles.append({"equation": child.content, "style": {}})
            elif child.type == "image":
                self._handle_image(child, len(self.blocks))

        _flush()
        return styles if styles else [{"text": "", "style": {}}]

    def _handle_image(self, token: Token, block_index: int):
        src = token.attrGet("src")
        alt = token.attrGet("alt") or "image"
        if not src:
            return

        if src.startswith(("http://", "https://")):
            if self.image_mode == "local":
                logger.warning(f"Network image in local mode: {src}")
                return
            elif self.image_mode == "skip":
                return
        else:
            local_path = (self.md_file.parent / src).resolve()
            if not local_path.exists():
                logger.warning(f"Image not found: {local_path}")
                return

            self.blocks.append({"blockType": "image", "options": {"image": {}}})
            self.images.append({
                "blockIndex": len(self.blocks) - 1,
                "batchIndex": -1,
                "localPath": str(local_path),
                "altText": alt,
            })

    # ------------------------------------------------------------------
    # Long paragraph splitting & batching
    # ------------------------------------------------------------------

    def _split_long_paragraph(self, text_styles: List[Dict[str, Any]]):
        chunk: List[Dict[str, Any]] = []
        length = 0
        for style in text_styles:
            tl = len(style.get("text", ""))
            if length + tl > self.max_text_length and chunk:
                self.blocks.append({
                    "blockType": "text",
                    "options": {"text": {"textStyles": chunk, "align": 1}},
                })
                chunk = []
                length = 0
            chunk.append(style)
            length += tl
        if chunk:
            self.blocks.append({
                "blockType": "text",
                "options": {"text": {"textStyles": chunk, "align": 1}},
            })

    def _create_batches(self) -> List[Dict[str, Any]]:
        batches: List[Dict[str, Any]] = []
        for i in range(0, len(self.blocks), self.batch_size):
            batch_blocks = self.blocks[i : i + self.batch_size]
            idx = len(batches)
            batches.append({"batchIndex": idx, "startIndex": i, "blocks": batch_blocks})
            for img in self.images:
                if i <= img["blockIndex"] < i + self.batch_size:
                    img["batchIndex"] = idx
        return batches
