"""
Self-contained MCP server for uploading Markdown to Feishu documents.
No external project dependencies — all logic lives under this `mcp/` package.

环境变量:
    FEISHU_APP_ID              - 飞书应用 App ID
    FEISHU_APP_SECRET          - 飞书应用 App Secret
    FEISHU_DEFAULT_FOLDER_TOKEN - 默认上传目标文件夹 token
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

from feishu_doc import create_document_from_markdown as _create_doc

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

mcp = FastMCP(
    "feishu-doc",
    instructions="上传 Markdown 到飞书云文档",
)


@mcp.tool()
def create_document_from_markdown(
    file_path: str,
    doc_title: str = "",
    folder_token: str = "",
) -> str:
    """上传本地 Markdown 文件并创建为飞书云文档。

    完整流程: 创建文档 → 解析 Markdown → 转换为飞书 Blocks → 批量上传 → 上传图片。

    Args:
        file_path: Markdown 文件的绝对路径
        doc_title: 云文档标题，留空则使用文件名（不含扩展名）
        folder_token: 目标文件夹 token，留空则使用环境变量 FEISHU_DEFAULT_FOLDER_TOKEN
    """
    try:
        path = Path(file_path).resolve()
        if not path.exists():
            return f"错误: 文件不存在 - {file_path}"
        if path.suffix.lower() not in (".md", ".markdown"):
            return f"错误: 不是 Markdown 文件 - {file_path}"

        result = _create_doc(
            md_file=str(path),
            title=doc_title or None,
            folder_token=folder_token or None,
        )

        return (
            f"文档创建成功!\n"
            f"  标题: {result['title']}\n"
            f"  文档ID: {result['document_id']}\n"
            f"  链接: {result['document_url']}\n"
            f"  Blocks: {result['total_blocks']}\n"
            f"  图片: {result['total_images']}\n"
            f"  批次: {result['total_batches']}"
        )
    except Exception as e:
        return f"错误: {e}"


if __name__ == "__main__":
    mcp.run()
