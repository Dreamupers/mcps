"""
arXiv 论文搜索 MCP Server
通过 arXiv API 搜索论文，返回 ID、标题和摘要
"""
import re
import urllib.parse
import xml.etree.ElementTree as ET

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("arxiv-search", instructions="搜索 arXiv 论文")

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def _parse_entries(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    results = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        raw_id = entry.findtext(f"{ATOM_NS}id", "")
        arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id

        title = entry.findtext(f"{ATOM_NS}title", "").strip()
        title = re.sub(r"\s+", " ", title)

        summary = entry.findtext(f"{ATOM_NS}summary", "").strip()
        summary = re.sub(r"\s+", " ", summary)

        authors = [
            a.findtext(f"{ATOM_NS}name", "")
            for a in entry.findall(f"{ATOM_NS}author")
        ]

        published = entry.findtext(f"{ATOM_NS}published", "")[:10]

        categories = [
            c.get("term", "")
            for c in entry.findall(f"{ARXIV_NS}primary_category")
        ]
        categories += [
            c.get("term", "")
            for c in entry.findall(f"{ATOM_NS}category")
            if c.get("term", "") not in categories
        ]

        pdf_url = ""
        for link in entry.findall(f"{ATOM_NS}link"):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")
                break

        results.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": ", ".join(authors),
            "published": published,
            "categories": ", ".join(categories[:3]),
            "abstract": summary,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf": pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
        })
    return results


@mcp.tool()
def arxiv_search(
    query: str,
    top_k: int = 5,
    sort_by: str = "relevance",
) -> str:
    """搜索 arXiv 论文，返回匹配的论文列表。

    Args:
        query: 搜索关键词，支持 arXiv 查询语法。
               例: "transformer attention" 全文搜索,
               "ti:diffusion policy" 按标题搜索,
               "au:hinton" 按作者搜索,
               "cat:cs.CV" 按分类搜索,
               可用 AND/OR/ANDNOT 组合: "ti:NeRF AND cat:cs.CV"
        top_k: 返回结果数量，1-20，默认 5
        sort_by: 排序方式: relevance(相关度), lastUpdatedDate(最近更新), submittedDate(提交时间)
    """
    top_k = max(1, min(20, top_k))
    valid_sorts = {"relevance", "lastUpdatedDate", "submittedDate"}
    if sort_by not in valid_sorts:
        sort_by = "relevance"

    params = {
        "search_query": query,
        "start": 0,
        "max_results": top_k,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }

    try:
        resp = requests.get(ARXIV_API, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return f"请求 arXiv API 失败: {e}"

    entries = _parse_entries(resp.text)
    if not entries:
        return f"未找到匹配「{query}」的论文"

    lines = [f"找到 {len(entries)} 篇论文:\n"]
    for i, p in enumerate(entries, 1):
        lines.append(
            f"[{i}] {p['title']}\n"
            f"    ID: {p['arxiv_id']}\n"
            f"    作者: {p['authors']}\n"
            f"    日期: {p['published']}  分类: {p['categories']}\n"
            f"    链接: {p['url']}\n"
            f"    摘要: {p['abstract']}\n"
        )
    return "\n".join(lines)


@mcp.tool()
def arxiv_search_by_title(
    title: str,
    top_k: int = 3,
) -> str:
    """按论文标题精确搜索 arXiv 论文。

    Args:
        title: 论文标题（或标题关键词）
        top_k: 返回结果数量，默认 3
    """
    escaped = title.replace('"', "")
    query = f'ti:"{escaped}"'
    return arxiv_search(query=query, top_k=top_k, sort_by="relevance")


@mcp.tool()
def arxiv_get_paper(
    arxiv_id: str,
) -> str:
    """根据 arXiv ID 获取单篇论文的详细信息。

    Args:
        arxiv_id: arXiv 论文 ID，如 "2401.01234" 或 "2401.01234v2"
    """
    clean_id = arxiv_id.strip().replace("arxiv:", "").replace("arXiv:", "")
    params = {"id_list": clean_id, "max_results": 1}

    try:
        resp = requests.get(ARXIV_API, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return f"请求失败: {e}"

    entries = _parse_entries(resp.text)
    if not entries:
        return f"未找到论文: {arxiv_id}"

    p = entries[0]
    return (
        f"标题: {p['title']}\n"
        f"ID: {p['arxiv_id']}\n"
        f"作者: {p['authors']}\n"
        f"日期: {p['published']}\n"
        f"分类: {p['categories']}\n"
        f"链接: {p['url']}\n"
        f"PDF: {p['pdf']}\n"
        f"摘要:\n{p['abstract']}"
    )


if __name__ == "__main__":
    mcp.run()
