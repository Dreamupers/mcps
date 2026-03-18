---
name: arxiv-paper-reader
description: Read and summarize arXiv papers from title. Use when the user asks to read/understand an arXiv paper, provides a paper title, or mentions downloading arXiv TeX source (arxiv.org/src). Fetch paper metadata, download and extract source, locate main .tex, read the full paper, and write structured Chinese notes to arxiv_paper_notes using {paper_id}_{method}.md.
---

# arXiv Paper Reader

## Goal
给定论文标题（优先）或 arXiv id，检索确定 paper_id，下载 PDF 与源码，阅读 TeX 源码，输出markdown中文笔记到 `arxiv_paper_notes/`，并将核心问题与创新点总结给用户。

## Hard Requirements
- 在当前工作目录进行操作
- 论文源码放在 `arxiv_paper_source/` 下。
- 阅读笔记放在 `arxiv_paper_notes/` 下。
- 论文PDF必须放在`arxiv_paper_pdf/`下。 
- 笔记文件命名：`{paper_id}_{method}.md`（例如：`2401.01234v2_DiffusionPolicy.md`）。
- 笔记内容必须包含：基本信息、主要发现、创新点与方法、实验效果（含关键指标/对比/消融）、局限性与未来工作。
- 在笔记中出现的公式使用md文件支持的Latex公式格式，行内公式使用`$`包裹，行间公式使用`$$`包裹。
- 在笔记中出现的表格使用md文件支持的表格格式。
- 论文中的重要图片（框架图、可视化结果、问题说明示意图）提取并嵌入笔记，使用 `pdftoppm` 将 PDF 转为 JPG，图片存放在 `arxiv_paper_notes/{paper_id}_figures/` 下。

## Inputs
- 论文标题或者arXiv id

## Workflow

### 0) 准备目录
确保存在：
- `arxiv_paper_source/`
- `arxiv_paper_notes/`
- `arxiv_paper_pdf/`

### 1) 通过arxiv-search工具确定最匹配的论文paper_id和论文题目，如果arxiv_paper_source目录中存在当前论文的源码文件夹，则直接读取。

### 2) 下载 PDF 与latex源码并解压

#### 2.1 下载 PDF

- `curl -L "https://arxiv.org/pdf/{paper_id}.pdf" -o "arxiv_paper_pdf/{paper_id}_{title}.pdf"`

#### 2.2 下载源码（src）并解压

在工作区创建论文源文件目录`arxiv_paper_source/{paper_id}/`

下载并解压：
- `curl -L "https://arxiv.org/src/{paper_id}" -o "arxiv_paper_source/{paper_id}/source.tar.gz"`
- `tar -xzf "arxiv_paper_source/{paper_id}/source.tar.gz" -C "arxiv_paper_source/{paper_id}"`

### 3) 定位TeX主文件

- 筛选所有 `*.tex` 文件（含补充材料，如 `supp*`, `appendix*`）。
- 优先条件：包含 `\documentclass` 和 `\begin{document}`，或具备标题/作者/正文结构，常见文件名优先（如 `main.tex`、`paper.tex`）。
- 若有多个候选，优先引用其他章节（含 `\input{}`/`\include{}`）且结构完整者。
- 以主文件为起点，按实际章节展开阅读。

### 4) 阅读与理解

- 摘要 + 引言：问题定义、动机、挑战、贡献列表
- 方法：核心假设、模型/算法步骤、损失函数、训练/推理流程
- 理论（如有）：定理、证明思路、条件与适用范围
- 实验：
  - 数据集/任务、评估指标、对比方法（SOTA/强基线）
  - 关键结果表/图：提升幅度、显著性、失败案例
  - 消融：每个组件的作用
- 局限性与伦理（如有）：可复现性、数据偏差、计算成本

### 5) 提取论文中的重要图片

arXiv 源码中的图片大多为 PDF 格式矢量图，需要转换为 JPG 后嵌入笔记。

#### 5.1 扫描源码中的图片文件

在解压目录中查找所有 `.pdf` 矢量图片文件或普通图片文件（通常在 `figures/`、`figs/`、`fig/`、`images/`、`imgs/` 等子目录，或直接在根目录）。同时关注 TeX 源码中 `\includegraphics` 引用的文件路径来确定哪些是论文实际使用的图片。

#### 5.2 筛选需要保留的图片

阅读 TeX 源码后，根据上下文判断每张图的内容，筛选出以下三类重要图片：

1. **问题说明 / 动机示意图**：作者用来说明研究问题、现有方法局限性的示意图（通常在 Introduction 或 Method 开头）
2. **Framework / Pipeline 框图**：论文提出方法的整体架构图、流程图
3. **可视化结果图**：定性对比、生成结果、注意力可视化等能直观展示方法效果的图

不需要保留的图：仅含数值曲线的训练 loss 图、与正文重复的补充材料图、不影响理解的装饰性图。

#### 5.3 使用 pdftoppm 将 PDF 图片转换为 JPG

在笔记目录下为该论文创建图片文件夹：`arxiv_paper_notes/{paper_id}_figures/`

转换命令（逐个文件执行）：

```bash
pdftoppm -jpeg -cropbox -r 300 -f 1 -l 1 -singlefile "arxiv_paper_source/{paper_id}/path/to/figure.pdf" "arxiv_paper_notes/{paper_id}_figures/figure_name"
```

注意：`pdftoppm` 会自动为输出文件添加 `.jpg` 后缀，所以输出路径 **不要** 加后缀。

参数说明：
- `-jpeg`：输出 JPEG 格式
- `-r 300`：以 300 DPI 渲染，保证清晰度
- `-f 1 -l 1`：只转换第 1 页（论文图片 PDF 通常只有一页）
- `-singlefile`：不在文件名末尾追加页码编号

转换后的 JPG 文件名应具备可读性，建议用 `fig{序号}_{简短描述}` 的格式（不加后缀），例如 `fig1_framework`、`fig3_qualitative_results`，最终生成 `fig1_framework.jpg`、`fig3_qualitative_results.jpg`。PNG/JPG 等可直接复制到 `{paper_id}_figures/`中，并修改文件名，无需转换。

#### 5.4 在笔记中嵌入图片

在笔记的对应章节插入图片引用，使用相对路径：

```markdown
![Framework Overview]({paper_id}_figures/fig1_framework.jpg)
```

图片应出现在笔记中与其内容最相关的位置（而非集中堆在末尾），并附上简要中文说明。

### 6) 生成阅读笔记到 arxiv_paper_notes/
输出文件：
- 路径：`arxiv_paper_notes/{paper_id}_{method}.md`
- 其中 `{method}`：
  - 从论文提出的核心方法命名（短、唯一、可读；优先论文中 method 名称）
  - 如果论文没有名称，则用论文标题

笔记markdown没有固定的模板，但要包括基本信息，一段话总结，研究问题是什么，作者的发现是什么，创新点是什么，方法的核心思路，模型的输入输出，与现有方法的主要差异，损失函数，训练和推理流程，技术细节，实验结果，各个模块的作用，局限性和未来可以改进的方向。生成的阅读笔记可以基本当做演示文稿以便将论文清楚地讲解给其他人。你不能假设我对一些论文中每个概念都非常清楚，请用通俗易懂的语言撰写笔记，而不是简单词汇和短语的组合。
