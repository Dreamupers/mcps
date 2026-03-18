"""
Feishu API Client (Standalone)

Self-contained client for creating Feishu documents from Markdown.
Extracted from feishu-doc-tools for independent maintenance.

"""

import os
import json
import logging
import threading
import time
import mimetypes
from typing import Dict, List, Any, Optional
from pathlib import Path
import requests


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FeishuDocClientError(Exception):
    """Base exception for Feishu API client errors"""


class FeishuApiAuthError(FeishuDocClientError):
    """Authentication related errors"""


class FeishuApiRequestError(FeishuDocClientError):
    """API request errors"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class FeishuDocClient:
    """
    Feishu API client for uploading Markdown to Feishu documents.

    Uses tenant_access_token (app identity) authentication.

    Usage:
        client = FeishuDocClient.from_env()
        result = client.create_document("My Doc")
    """

    BASE_URL = "https://open.feishu.cn/open-apis"
    AUTH_ENDPOINT = "/auth/v3/tenant_access_token/internal"
    BLOCKS_ENDPOINT_TEMPLATE = "/docx/v1/documents/{doc_id}/blocks/{parent_id}/children"
    IMAGE_UPLOAD_ENDPOINT = "/drive/v1/medias/upload_all"

    _token_cache: Optional[Dict[str, str]] = None
    _token_expire_time: Optional[int] = None
    _token_lock = threading.Lock()


    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json; charset=utf-8"})

        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry_kwargs = {
            "total": 3,
            "backoff_factor": 0.5,
            "status_forcelist": [429, 500, 502, 503, 504],
        }
        try:
            retry_strategy = Retry(
                **retry_kwargs,
                allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            )
        except TypeError:
            retry_strategy = Retry(
                **retry_kwargs,
                method_whitelist=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            )

        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @classmethod
    def from_env(cls) -> "FeishuDocClient":
        app_id = os.environ.get("FEISHU_APP_ID") or os.environ.get("FEISHU_APPID")
        app_secret = os.environ.get("FEISHU_APP_SECRET") or os.environ.get("FEISHU_APPSECRET")

        if not app_id:
            raise ValueError(
                "FEISHU_APP_ID not set. "
                "Set it via environment variable, .env file, or pass directly."
            )
        if not app_secret:
            raise ValueError(
                "FEISHU_APP_SECRET not set. "
                "Set it via environment variable, .env file, or pass directly."
            )

        return cls(app_id, app_secret)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_token(self, force_refresh: bool = False) -> str:
        current_time = int(time.time())
        with self._token_lock:
            if not force_refresh and self._token_cache and self._token_expire_time:
                if current_time < self._token_expire_time - 300:
                    return self._token_cache.get("tenant_access_token", "")

            url = f"{self.BASE_URL}{self.AUTH_ENDPOINT}"
            payload = {"app_id": self.app_id, "app_secret": self.app_secret}
            response = self.session.post(url, json=payload, timeout=10)

            if response.status_code != 200:
                raise FeishuApiAuthError(f"Failed to get tenant token: HTTP {response.status_code}")

            data = response.json()
            if data.get("code") != 0:
                raise FeishuApiAuthError(
                    f"Failed to get tenant token: {data.get('msg', 'Unknown error')}"
                )

            token = data.get("tenant_access_token")
            expire = data.get("expire", 7200)
            if not token:
                raise FeishuApiAuthError("No tenant_access_token in response")

            self._token_cache = {"tenant_access_token": token}
            self._token_expire_time = current_time + expire
            logger.info(f"Obtained tenant token, expires in {expire}s")
            return token

    # ------------------------------------------------------------------
    # Document Operations
    # ------------------------------------------------------------------

    def get_default_folder_token(self) -> Optional[str]:
        return os.environ.get("FEISHU_DEFAULT_FOLDER_TOKEN")

    def create_document(
        self, title: str, folder_token: Optional[str] = None
    ) -> Dict[str, Any]:
        token = self._get_token()
        url = f"{self.BASE_URL}/docx/v1/documents"
        payload: Dict[str, Any] = {"title": title}
        if folder_token:
            payload["folder_token"] = folder_token

        headers = {"Authorization": f"Bearer {token}"}
        logger.info(f"Creating document: {title}")
        response = self.session.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code != 200:
            raise FeishuApiRequestError(
                f"Failed to create document: HTTP {response.status_code}\n{response.text}"
            )

        result = response.json()
        if result.get("code") != 0:
            raise FeishuApiRequestError(
                f"Failed to create document: {result.get('msg', 'Unknown error')}"
            )

        doc_data = result.get("data", {}).get("document", {})
        doc_id = doc_data.get("document_id")
        logger.info(f"Created document: {doc_id}")

        return {
            "document_id": doc_id,
            "url": f"https://feishu.cn/docx/{doc_id}",
            "title": doc_data.get("title", title),
            "revision_id": doc_data.get("revision_id"),
        }

    # ------------------------------------------------------------------
    # Block Creation
    # ------------------------------------------------------------------

    def batch_create_blocks(
        self,
        doc_id: str,
        blocks: List[Dict[str, Any]],
        parent_id: Optional[str] = None,
        index: int = 0,
        batch_size: int = 50,
    ) -> Dict[str, Any]:
        """Batch create blocks. Handles tables separately, auto-splits at 50 blocks."""
        token = self._get_token()
        batch_size = min(batch_size, 50)
        if parent_id is None:
            parent_id = doc_id

        all_image_block_ids: List[str] = []
        current_index = index
        i = 0

        while i < len(blocks):
            block = blocks[i]
            block_type = block.get("blockType", "")

            if block_type == "table":
                table_config = block.get("options", {}).get("table", {})
                logger.info(
                    f"Creating table at index {current_index}: "
                    f"{table_config.get('rowSize')}x{table_config.get('columnSize')}"
                )
                self.create_table_block(doc_id, table_config, parent_id, current_index)
                current_index += 1
                i += 1
                continue

            children: List[Dict[str, Any]] = []
            image_block_indices: List[int] = []

            while i < len(blocks) and len(children) < batch_size:
                block = blocks[i]
                block_type = block.get("blockType", "")
                if block_type == "table":
                    break
                options = block.get("options", {})

                formatted = self._format_block(block_type, options)
                if formatted is None:
                    logger.warning(f"Unknown block type: {block_type}, skipping")
                    i += 1
                    continue

                children.append(formatted)
                if block_type == "image":
                    image_block_indices.append(len(children) - 1)
                i += 1

            if not children:
                continue

            endpoint = self.BLOCKS_ENDPOINT_TEMPLATE.format(doc_id=doc_id, parent_id=parent_id)
            url = f"{self.BASE_URL}{endpoint}?document_revision_id=-1"
            payload = {"children": children, "index": current_index}
            headers = {"Authorization": f"Bearer {token}"}

            logger.info(f"Creating {len(children)} blocks at index {current_index}")
            response = self.session.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code != 200:
                debug_file = "/tmp/feishu_error_payload.json"
                Path(debug_file).write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                raise FeishuApiRequestError(
                    f"Failed to create blocks: HTTP {response.status_code}\n{response.text}"
                )

            result = response.json()
            if result.get("code") != 0:
                raise FeishuApiRequestError(
                    f"Failed to create blocks: {result.get('msg', 'Unknown error')} "
                    f"(code={result.get('code')})"
                )

            logger.info(f"Created {len(children)} blocks")
            all_image_block_ids.extend(self._extract_image_block_ids(result, image_block_indices))
            current_index += len(children)

        return {
            "code": 0,
            "image_block_ids": all_image_block_ids,
            "total_blocks_created": len(blocks),
        }

    # ------------------------------------------------------------------
    # Image Upload
    # ------------------------------------------------------------------

    def upload_and_bind_image(
        self, doc_id: str, block_id: str, image_path_or_url: str, file_name: Optional[str] = None
    ) -> Dict[str, Any]:
        token = self._get_token()
        logger.info(f"Uploading image: {image_path_or_url}")

        if image_path_or_url.startswith(("http://", "https://")):
            file_token = image_path_or_url
        else:
            file_token = self._upload_image_file(image_path_or_url, file_name, token, parent_node=block_id)

        logger.info(f"Binding image to block {block_id}")
        url = f"{self.BASE_URL}/docx/v1/documents/{doc_id}/blocks/{block_id}?document_revision_id=-1"
        payload = {"replace_image": {"token": file_token}}
        headers = {"Authorization": f"Bearer {token}"}

        response = self.session.patch(url, json=payload, headers=headers, timeout=30)
        if response.status_code != 200:
            raise FeishuApiRequestError(
                f"Failed to bind image: HTTP {response.status_code}\n{response.text}"
            )

        result = response.json()
        if result.get("code") != 0:
            raise FeishuApiRequestError(
                f"Failed to bind image: {result.get('msg', 'Unknown error')}"
            )

        logger.info(f"Bound image to block {block_id}")
        return result

    def _upload_image_file(
        self, file_path: str, file_name: Optional[str], token: str, parent_node: Optional[str] = None
    ) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FeishuApiRequestError(f"Image file not found: {file_path}")

        if not file_name:
            file_name = path.name

        file_size = path.stat().st_size
        mime_type, _ = mimetypes.guess_type(file_name)
        if not mime_type:
            mime_type = "image/png"

        url = f"{self.BASE_URL}{self.IMAGE_UPLOAD_ENDPOINT}"

        with path.open("rb") as f:
            form_data = {
                "file_name": (None, file_name),
                "parent_type": (None, "docx_image"),
                "parent_node": (None, parent_node or ""),
                "size": (None, str(file_size)),
                "file": (file_name, f, mime_type),
            }
            headers = {"Authorization": f"Bearer {token}", "Content-Type": None}
            response = self.session.post(url, files=form_data, headers=headers, timeout=60)

        if response.status_code != 200:
            raise FeishuApiRequestError(
                f"Failed to upload image: HTTP {response.status_code}\n{response.text}"
            )

        result = response.json()
        if result.get("code") != 0:
            raise FeishuApiRequestError(
                f"Failed to upload image: {result.get('msg', 'Unknown error')}"
            )

        file_token = result.get("data", {}).get("file_token")
        if not file_token:
            raise FeishuApiRequestError("No file_token in upload response")

        logger.info(f"Uploaded image, file_token: {file_token}")
        return file_token

    # ------------------------------------------------------------------
    # Table Block
    # ------------------------------------------------------------------

    def create_table_block(
        self, doc_id: str, table_config: Dict[str, Any],
        parent_id: Optional[str] = None, index: int = 0,
    ) -> Dict[str, Any]:
        token = self._get_token()
        if parent_id is None:
            parent_id = doc_id

        column_size = table_config.get("columnSize", 0)
        row_size = table_config.get("rowSize", 0)
        cells_config = table_config.get("cells", [])
        table_id = f"table_{int(time.time() * 1000)}"

        descendants: List[Dict[str, Any]] = []
        table_cells: List[str] = []

        table_block: Dict[str, Any] = {
            "block_id": table_id,
            "block_type": 31,
            "table": {"property": {"row_size": row_size, "column_size": column_size}},
            "children": [],
        }

        for row in range(row_size):
            for col in range(column_size):
                cell_id = f"{table_id}_cell_{row}_{col}"
                table_cells.append(cell_id)

                cell_config = None
                for cfg in cells_config:
                    coord = cfg.get("coordinate", {})
                    if coord.get("row") == row and coord.get("column") == col:
                        cell_config = cfg
                        break

                if cell_config:
                    content = cell_config.get("content", {})
                    options = content.get("options", {})
                    content_block = self._format_text_block(options)
                else:
                    content_block = self._format_text_block(
                        {"text": {"textStyles": [{"text": "", "style": {}}], "align": 1}}
                    )

                cell_content_id = f"{cell_id}_content"
                descendants.append({
                    "block_id": cell_id, "block_type": 32,
                    "table_cell": {}, "children": [cell_content_id],
                })
                descendants.append({"block_id": cell_content_id, **content_block, "children": []})

        table_block["children"] = table_cells
        descendants.insert(0, table_block)

        endpoint = f"/docx/v1/documents/{doc_id}/blocks/{parent_id}/descendant?document_revision_id=-1"
        url = f"{self.BASE_URL}{endpoint}"
        payload = {"children_id": [table_id], "descendants": descendants, "index": index}
        headers = {"Authorization": f"Bearer {token}"}

        logger.info(f"Creating table: {row_size}x{column_size}")
        response = self.session.post(url, json=payload, headers=headers, timeout=60)

        if response.status_code != 200:
            raise FeishuApiRequestError(
                f"Failed to create table: HTTP {response.status_code}\n{response.text}"
            )

        result = response.json()
        if result.get("code") != 0:
            raise FeishuApiRequestError(
                f"Failed to create table: {result.get('msg', 'Unknown error')} "
                f"(code={result.get('code')})"
            )

        logger.info(f"Created table: {row_size}x{column_size}")
        return result

    # ------------------------------------------------------------------
    # Block Formatting Helpers
    # ------------------------------------------------------------------

    def _format_block(self, block_type: str, options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Route block formatting by type."""
        if block_type == "text":
            return self._format_text_block(options)
        if block_type.startswith("heading"):
            return self._format_heading_block(block_type, options)
        if block_type == "code":
            return self._format_code_block(options)
        if block_type == "list":
            return self._format_list_block(options)
        if block_type == "image":
            return self._format_image_block(options)
        if block_type == "board":
            return self._format_board_block(options)
        return None

    def _format_text_block(self, options: Dict[str, Any]) -> Dict[str, Any]:
        text_config = options.get("text", {})
        text_styles = text_config.get("textStyles", [])
        align = text_config.get("align", 1)

        text_elements: List[Dict[str, Any]] = []
        for style in text_styles:
            text_content = style.get("text", "")
            equation_content = style.get("equation", "")
            if not text_content and not equation_content:
                continue

            if equation_content:
                text_elements.append({
                    "equation": {
                        "content": equation_content + "\n",
                        "text_element_style": {
                            "bold": False, "italic": False, "strikethrough": False,
                            "underline": False, "inline_code": False,
                        },
                    }
                })
            else:
                text_elements.append({
                    "text_run": {
                        "content": text_content,
                        "text_element_style": self._convert_text_style(style.get("style", {})),
                    }
                })

        if not text_elements:
            text_elements.append({"text_run": {"content": ""}})

        return {"block_type": 2, "text": {"elements": text_elements, "style": {"align": align}}}

    def _format_heading_block(self, block_type: str, options: Dict[str, Any]) -> Dict[str, Any]:
        level = int(block_type[-1]) if block_type.startswith("heading") else 1
        content = options.get("heading", {}).get("content", "")
        align = options.get("heading", {}).get("align", 1)
        feishu_type = 2 + level
        field = f"heading{level}"

        return {
            "block_type": feishu_type,
            field: {
                "elements": [{
                    "text_run": {
                        "content": content,
                        "text_element_style": {
                            "bold": False, "italic": False, "strikethrough": False,
                            "underline": False, "inline_code": False,
                        },
                    }
                }],
                "style": {"align": align},
            },
        }

    def _format_code_block(self, options: Dict[str, Any]) -> Dict[str, Any]:
        cfg = options.get("code", {})
        return {
            "block_type": 14,
            "code": {
                "elements": [{
                    "text_run": {
                        "content": cfg.get("code", ""),
                        "text_element_style": {
                            "bold": False, "italic": False, "strikethrough": False,
                            "underline": False, "inline_code": False,
                        },
                    }
                }],
                "style": {"language": cfg.get("language", 1), "wrap": cfg.get("wrap", False)},
            },
        }

    def _format_list_block(self, options: Dict[str, Any]) -> Dict[str, Any]:
        cfg = options.get("list", {})
        is_ordered = cfg.get("isOrdered", False)
        block_type = 13 if is_ordered else 12
        field = "ordered" if is_ordered else "bullet"

        text_styles = cfg.get("textStyles")
        if text_styles:
            text_elements: List[Dict[str, Any]] = []
            for style in text_styles:
                text_content = style.get("text", "")
                equation_content = style.get("equation", "")
                if not text_content and not equation_content:
                    continue

                if equation_content:
                    text_elements.append({
                        "equation": {
                            "content": equation_content + "\n",
                            "text_element_style": {
                                "bold": False, "italic": False, "strikethrough": False,
                                "underline": False, "inline_code": False,
                            },
                        }
                    })
                else:
                    text_elements.append({
                        "text_run": {
                            "content": text_content,
                            "text_element_style": self._convert_text_style(style.get("style", {})),
                        }
                    })

            if not text_elements:
                text_elements.append({"text_run": {"content": ""}})

            elements = text_elements
        else:
            content = cfg.get("content", "")
            elements = [{
                "text_run": {
                    "content": content,
                    "text_element_style": {
                        "bold": False, "italic": False, "strikethrough": False,
                        "underline": False, "inline_code": False,
                    },
                }
            }]

        return {
            "block_type": block_type,
            field: {
                "elements": elements,
                "style": {"align": cfg.get("align", 1)},
            },
        }

    def _format_image_block(self, options: Dict[str, Any]) -> Dict[str, Any]:
        align = options.get("image", {}).get("align", 2)
        return {"block_type": 27, "image": {"align": align}}

    def _format_board_block(self, options: Dict[str, Any]) -> Dict[str, Any]:
        cfg = options.get("board", {})
        data: Dict[str, Any] = {"align": cfg.get("align", 2)}
        if "width" in cfg:
            data["width"] = cfg["width"]
        if "height" in cfg:
            data["height"] = cfg["height"]
        return {"block_type": 43, "board": data}

    @staticmethod
    def _convert_text_style(style: Dict[str, Any]) -> Dict[str, Any]:
        api_style: Dict[str, Any] = {
            "bold": style.get("bold", False),
            "italic": style.get("italic", False),
            "underline": style.get("underline", False),
            "strikethrough": style.get("strikethrough", False),
            "inline_code": style.get("inline_code", False),
        }
        if "text_color" in style:
            api_style["text_color"] = style["text_color"]
        if "background_color" in style:
            api_style["background_color"] = style["background_color"]
        return api_style

    @staticmethod
    def _extract_image_block_ids(result: Dict[str, Any], indices: List[int]) -> List[str]:
        block_ids: List[str] = []
        for child in result.get("data", {}).get("children", []):
            if child.get("block_type") == 27:
                bid = child.get("block_id")
                if bid:
                    block_ids.append(bid)
        return block_ids

    def upload_markdown(self, md_file: str, doc_id: str) -> Dict[str, Any]:
        """Convert Markdown file to blocks and upload to an existing Feishu document."""
        from md_converter import MarkdownToFeishuConverter

        logger.info(f"Converting Markdown: {md_file}")
        converter = MarkdownToFeishuConverter(md_file=Path(md_file), doc_id=doc_id)
        conversion_result = converter.convert()

        if not conversion_result.get("success"):
            raise RuntimeError(
                f"Markdown conversion failed: {conversion_result.get('error', 'Unknown error')}"
            )

        all_batches = conversion_result.get("batches", [])
        all_images = conversion_result.get("images", [])
        total_blocks = 0
        total_images = 0
        created_image_block_ids: List[str] = []

        for batch in all_batches:
            logger.info(f"Uploading batch {batch['batchIndex'] + 1}/{len(all_batches)}")
            result = self.batch_create_blocks(
                doc_id=doc_id, blocks=batch["blocks"], index=batch["startIndex"]
            )
            total_blocks += result.get("total_blocks_created", 0)
            created_image_block_ids.extend(result.get("image_block_ids", []))

        if all_images and created_image_block_ids:
            for i, img in enumerate(all_images):
                if i < len(created_image_block_ids):
                    block_id = created_image_block_ids[i]
                    try:
                        self.upload_and_bind_image(
                            doc_id=doc_id, block_id=block_id, image_path_or_url=img["localPath"]
                        )
                        total_images += 1
                    except Exception as e:
                        logger.error(f"Failed to upload image {img['localPath']}: {e}")

        return {
            "success": True,
            "document_id": doc_id,
            "document_url": f"https://feishu.cn/docx/{doc_id}",
            "total_blocks": total_blocks,
            "total_images": total_images,
            "total_batches": len(all_batches),
        }


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def create_document_from_markdown(
    md_file: str,
    title: Optional[str] = None,
    folder_token: Optional[str] = None,
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new Feishu document and upload Markdown content to it.

    Workflow: create doc -> convert MD -> upload blocks -> upload images.
    """
    if app_id and app_secret:
        client = FeishuDocClient(app_id, app_secret)
    else:
        client = FeishuDocClient.from_env()

    if title is None:
        title = Path(md_file).stem

    effective_folder_token = folder_token
    if effective_folder_token is None:
        effective_folder_token = client.get_default_folder_token()
        if effective_folder_token:
            logger.info(f"Using default folder: {effective_folder_token}")
        else:
            logger.warning(
                "No folder_token and FEISHU_DEFAULT_FOLDER_TOKEN not set. "
                "Document goes to app space (only app has access)."
            )

    doc_result = client.create_document(title=title, folder_token=effective_folder_token)
    doc_id = doc_result["document_id"]

    logger.info(f"Uploading content to {doc_id}")
    upload_result = client.upload_markdown(md_file=md_file, doc_id=doc_id)

    return {
        "success": True,
        "document_id": doc_id,
        "document_url": doc_result["url"],
        "title": doc_result["title"],
        "total_blocks": upload_result.get("total_blocks", 0),
        "total_images": upload_result.get("total_images", 0),
        "total_batches": upload_result.get("total_batches", 0),
    }
