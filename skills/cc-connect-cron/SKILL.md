---
name: cc-connect-cron
description: Manage scheduled tasks for cc-connect (Feishu/Telegram agent sessions) via cc-connect cron — add agent prompts or shell commands on a cron schedule. Use when the user wants recurring automation, cron jobs, timed agent runs, or to list/edit/delete cc-connect scheduled tasks.
---

# CC-Connect Cron（定时任务）

通过 **cc-connect** 的 `cron` 子命令，在已连接的 Agent 会话（飞书/ Telegram 等）上创建**定时任务**：任务可以是 **Agent 自然语言提示**（走模型）或 **直接执行的 Shell 命令**。

## 何时使用本技能

- 用户要「每天/每小时固定让 Agent 做某事」「定时汇总/抓取/检查」
- 用户要配置、查看、修改、删除 **cc-connect** 侧的定时任务（而非系统 crontab）
- 需要说明 `CC_PROJECT`、`CC_SESSION_KEY`、会话模式、超时等与定时相关的选项

## 环境约定

- 目标项目：`-p` / `--project`，或环境变量 **`CC_PROJECT`**
- 目标会话：`-s` / `--session-key`，或环境变量 **`CC_SESSION_KEY`**
- 数据目录：`--data-dir`（默认 `~/.cc-connect`）

## 子命令总览

```text
cc-connect cron <command> [options]

Commands:
  add       新建定时任务
  list      列出全部定时任务
  edit      编辑某任务的字段
  info <id> [field]   查看任务详情（可选只查某一字段）
  del <id>  删除定时任务

详细参数：cc-connect cron <command> --help
```

## `cron add` — 新建任务

### 用法一：Cron 表达式 + 命名参数（推荐）

```text
cc-connect cron add [options]

Options:
  -p, --project <name>       目标项目（可用 CC_PROJECT）
  -s, --session-key <key>    目标会话（可用 CC_SESSION_KEY）
  -c, --cron <expr>          Cron 表达式，例如 "0 6 * * *"
      --prompt <text>        任务提示（经 Agent 执行）
      --exec <command>       Shell 命令（直接执行；与 --prompt 互斥）
      --desc <text>          简短描述
      --session-mode <mode>  reuse（默认）或 new-per-run（每次运行新会话）
      --timeout-mins <n>     单次运行最长等待分钟数（0=不限制；省略时默认 30）
      --data-dir <path>      数据目录（默认 ~/.cc-connect）
  -h, --help                 帮助
```

**示例：**

```bash
# 每天 6:00（cron）让 Agent 执行任务
cc-connect cron add --cron "0 6 * * *" --prompt "Collect GitHub trending data" --desc "Daily Trending"

# 每 30 分钟执行一次 shell（不经 Agent）
cc-connect cron add --cron "*/30 * * * *" --exec "df -h" --desc "Disk usage check"
```

### 用法二：位置参数（min hour day month weekday + prompt）

```text
cc-connect cron add [<min> <hour> <day> <month> <weekday> <prompt>]
```

**示例：**

```bash
cc-connect cron add 0 6 * * * "Collect GitHub trending data and send me a summary"
```

### 互斥与注意

- **`--prompt` 与 `--exec` 二选一**（不能同时用于同一任务）。
- **`--session-mode`**：`reuse` 复用会话；`new-per-run` 每次新开会话（与 `cron edit` 中的 `session_mode` 取值 `new_per_run` 对应，CLI 命名习惯不同）。
- **`--timeout-mins`**：控制单次运行最长等待；`0` 表示不限制。

## `cron list` / `cron info` / `cron del`

- **`list`**：列出所有已配置的定时任务。
- **`info <id> [field]`**：查看指定 `id` 的任务详情；若带 `field` 则只输出该字段。
- **`del <id>`**：删除指定 `id` 的任务。

## `cron edit` — 修改已有任务

```text
cc-connect cron edit <id> <field> <value> [options]

Edit a specific field of an existing scheduled task.

Options:
      --data-dir <path>  Data directory (default: ~/.cc-connect)
  -h, --help             Show this help
```

### 可编辑字段（字符串）

| field | 说明 |
| --- | --- |
| `project` | 目标项目名 |
| `session_key` | 目标会话 key |
| `cron_expr` | Cron 表达式，如 `"0 6 * * *"` |
| `prompt` | 任务提示（经 Agent） |
| `exec` | Shell 命令（直接执行） |
| `work_dir` | `exec` 的工作目录 |
| `description` | 简短描述 |
| `session_mode` | `reuse` 或 `new_per_run` |

### 可编辑字段（布尔：`true` / `false`）

| field | 说明 |
| --- | --- |
| `enabled` | 是否启用任务 |
| `mute` | 是否屏蔽所有消息 |
| `silent` | 是否屏蔽开始通知 |

### 可编辑字段（整数）

| field | 说明 |
| --- | --- |
| `timeout_mins` | 单次运行最长分钟数（`0` = 不限制） |

### 只读字段（不可 `edit`）

`id`、`created_at`、`last_run`、`last_error`

### 示例

```bash
cc-connect cron edit abc123 cron_expr "0 9 * * *"
cc-connect cron edit abc123 enabled false
cc-connect cron edit abc123 description "Daily standup reminder"
cc-connect cron edit abc123 timeout_mins 60
cc-connect cron edit abc123 mute true
```

## 代理执行建议

1. 若用户未指定项目/会话，先确认 **`CC_PROJECT` / `CC_SESSION_KEY`** 是否已设置，或根据 `cc-connect` 文档用 `-p`/`-s` 显式指定。
2. 区分需求：要 **对话式 Agent 推理** 用 `--prompt`；要 **固定命令输出** 用 `--exec`。
3. 长 prompt 或特殊字符较多时，可考虑用 shell 引号或 `cc-connect cron add` 支持的输入方式（以 `--help` 为准），避免未转义破坏命令行。
