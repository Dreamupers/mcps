---
name: cc-connect-send
description: Send message, files or images to Feishu/Telegram via cc-connect. Use when the user wants to send a generated file, report, chart, or image to their messaging platform (Feishu, Telegram, etc.).
---

# CC-Connect Send

When the user wants to send message, file or image to their messaging platform:

```bash
cc-connect send --message "hello"
cc-connect send --file /absolute/path/to/file.pdf
cc-connect send --image /absolute/path/to/chart.png
