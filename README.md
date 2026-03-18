# research mcps

MCP (Model Context Protocol) 服务集合，为 agent提供 arXiv 论文搜索、飞书文档上传等能力。

## 环境要求

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/)

无需 `pip install`，直接通过 `uv run` 运行，首次会自动同步依赖。

## 服务列表

### 1. arxiv-search

通过 arXiv API 搜索论文，支持关键词、标题、作者、分类等查询。

**工具：**


| 工具                      | 说明                   |
| ----------------------- | -------------------- |
| `arxiv_search`          | 全文搜索，支持 arXiv 查询语法   |
| `arxiv_search_by_title` | 按标题精确搜索              |
| `arxiv_get_paper`       | 根据 arXiv ID 获取单篇论文详情 |


**查询语法示例：**

- `transformer attention` — 全文搜索
- `ti:diffusion policy` — 按标题
- `au:hinton` — 按作者
- `cat:cs.CV` — 按分类
- `ti:NeRF AND cat:cs.CV` — 组合条件

---

### 2. feishu-doc-upload

将本地 Markdown 文件上传为飞书云文档，支持图片、表格等富文本转换。

**工具：**


| 工具                              | 说明                     |
| ------------------------------- | ---------------------- |
| `create_document_from_markdown` | 上传 Markdown 文件并创建飞书云文档 |


**环境变量：**


| 变量                            | 说明                  |
| ----------------------------- | ------------------- |
| `FEISHU_APP_ID`               | 飞书应用 App ID         |
| `FEISHU_APP_SECRET`           | 飞书应用 App Secret     |
| `FEISHU_DEFAULT_FOLDER_TOKEN` | 默认上传目标文件夹 token（可选） |


## 在 Cursor 中配置

将服务添加到 Cursor 的 MCP 配置（如 `~/.cursor/mcp.json`），同样使用 `uv run` 运行：

```json
{
  "mcpServers": {
    "arxiv-search": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/mcps", "/path/to/mcps/arxiv_search/arxiv_search.py"]
    },
    "feishu-doc-upload": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/mcps", "/path/to/mcps/feishu_doc_upload/feishu_doc_upload.py"],
      "env": {
        "FEISHU_APP_ID": "your_app_id",
        "FEISHU_APP_SECRET": "your_app_secret"
      }
    }
  }
}
```

将 `/path/to/mcps` 替换为项目实际路径。

## 项目结构

```
mcps/
├── arxiv_search/
│   └── arxiv_search.py      # arXiv 搜索服务
├── feishu_doc_upload/
│   ├── feishu_doc_upload.py  # 飞书文档上传入口
│   ├── feishu_doc.py         # 飞书 API 封装
│   └── md_converter.py       # Markdown 转换
├── pyproject.toml
├── uv.lock
└── README.md
```

