---
description: Python IDE MCP 封装
---

我们需要将PythonIDE的相关能力封装成一个MCP Server对外提供服务。

PythonIDE相关代码在： @ide4ai/python_ide 下

我们需要在 @ide4ai/python_ide/mcp 下展开封装

主要封装实现两个大模块：

1. Tools
2. Resource

对于Tools，我们需要封装如下工具：

{
    "name": "Bash",
    "description": "关于Bash工具的描述我会自己填写，目前不是重点",
    "inputSchema": {
      "type": "object",
      "properties": {
        "command": {
          "type": "string",
          "description": "The command to execute"
        },
        "timeout": {
          "type": "number",
          "description": "Optional timeout in milliseconds (max 600000)"
        },
        "description": {
          "type": "string",
          "description": "Clear, concise description of what this command does in 5-10 words, in active voice. Examples:\nInput: ls\nOutput: List files in current directory\n\nInput: git status\nOutput: Show working tree status\n\nInput: npm install\nOutput: Install package dependencies\n\nInput: mkdir foo\nOutput: Create directory 'foo'"
        },
        "run_in_background": {
          "type": "boolean",
          "description": "Set to true to run this command in the background. Use BashOutput to read the output later."
        },
        "dangerouslyDisableSandbox": {
          "type": "boolean",
          "description": "Set this to true to dangerously override sandbox mode and run commands without sandboxing."
        }
      },
      "required": [
        "command"
      ],
      "additionalProperties": false,
      "$schema": "http://json-schema.org/draft-07/schema#"
    }
  },
  {
    "name": "Glob",
    "description": "- Fast file pattern matching tool that works with any codebase size\n- Supports glob patterns like \"**/*.js\" or \"src/**/*.ts\"\n- Returns matching file paths sorted by modification time\n- Use this tool when you need to find files by name patterns\n- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead\n- You can call multiple tools in a single response. It is always better to speculatively perform multiple searches in parallel if they are potentially useful.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "pattern": {
          "type": "string",
          "description": "The glob pattern to match files against"
        },
        "path": {
          "type": "string",
          "description": "The directory to search in. If not specified, the current working directory will be used. IMPORTANT: Omit this field to use the default directory. DO NOT enter \"undefined\" or \"null\" - simply omit it for the default behavior. Must be a valid directory path if provided."
        }
      },
      "required": [
        "pattern"
      ],
      "additionalProperties": false,
      "$schema": "http://json-schema.org/draft-07/schema#"
    }
  },
  {
    "name": "Grep",
    "description": "A powerful search tool built on ripgrep\n\n  Usage:\n  - ALWAYS use Grep for search tasks. NEVER invoke `grep` or `rg` as a Bash command. The Grep tool has been optimized for correct permissions and access.\n  - Supports full regex syntax (e.g., \"log.*Error\", \"function\\s+\\w+\")\n  - Filter files with glob parameter (e.g., \"*.js\", \"**/*.tsx\") or type parameter (e.g., \"js\", \"py\", \"rust\")\n  - Output modes: \"content\" shows matching lines, \"files_with_matches\" shows only file paths (default), \"count\" shows match counts\n  - Use Task tool for open-ended searches requiring multiple rounds\n  - Pattern syntax: Uses ripgrep (not grep) - literal braces need escaping (use `interface\\{\\}` to find `interface{}` in Go code)\n  - Multiline matching: By default patterns match within single lines only. For cross-line patterns like `struct \\{[\\s\\S]*?field`, use `multiline: true`\n",
    "inputSchema": {
      "type": "object",
      "properties": {
        "pattern": {
          "type": "string",
          "description": "The regular expression pattern to search for in file contents"
        },
        "path": {
          "type": "string",
          "description": "File or directory to search in (rg PATH). Defaults to current working directory."
        },
        "glob": {
          "type": "string",
          "description": "Glob pattern to filter files (e.g. \"*.js\", \"*.{ts,tsx}\") - maps to rg --glob"
        },
        "output_mode": {
          "type": "string",
          "enum": [
            "content",
            "files_with_matches",
            "count"
          ],
          "description": "Output mode: \"content\" shows matching lines (supports -A/-B/-C context, -n line numbers, head_limit), \"files_with_matches\" shows file paths (supports head_limit), \"count\" shows match counts (supports head_limit). Defaults to \"files_with_matches\"."
        },
        "-B": {
          "type": "number",
          "description": "Number of lines to show before each match (rg -B). Requires output_mode: \"content\", ignored otherwise."
        },
        "-A": {
          "type": "number",
          "description": "Number of lines to show after each match (rg -A). Requires output_mode: \"content\", ignored otherwise."
        },
        "-C": {
          "type": "number",
          "description": "Number of lines to show before and after each match (rg -C). Requires output_mode: \"content\", ignored otherwise."
        },
        "-n": {
          "type": "boolean",
          "description": "Show line numbers in output (rg -n). Requires output_mode: \"content\", ignored otherwise."
        },
        "-i": {
          "type": "boolean",
          "description": "Case insensitive search (rg -i)"
        },
        "type": {
          "type": "string",
          "description": "File type to search (rg --type). Common types: js, py, rust, go, java, etc. More efficient than include for standard file types."
        },
        "head_limit": {
          "type": "number",
          "description": "Limit output to first N lines/entries, equivalent to \"| head -N\". Works across all output modes: content (limits output lines), files_with_matches (limits file paths), count (limits count entries). When unspecified, shows all results from ripgrep."
        },
        "multiline": {
          "type": "boolean",
          "description": "Enable multiline mode where . matches newlines and patterns can span lines (rg -U --multiline-dotall). Default: false."
        }
      },
      "required": [
        "pattern"
      ],
      "additionalProperties": false,
      "$schema": "http://json-schema.org/draft-07/schema#"
    }
  },
  {
    "name": "Read",
    "description": "...",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_path": {
          "type": "string",
          "description": "The absolute path to the file to read"
        },
        "offset": {
          "type": "number",
          "description": "The line number to start reading from. Only provide if the file is too large to read at once"
        },
        "limit": {
          "type": "number",
          "description": "The number of lines to read. Only provide if the file is too large to read at once."
        }
      },
      "required": [
        "file_path"
      ],
      "additionalProperties": false,
      "$schema": "http://json-schema.org/draft-07/schema#"
    }
  },
  {
    "name": "Edit",
    "description": "...",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_path": {
          "type": "string",
          "description": "The absolute path to the file to modify"
        },
        "old_string": {
          "type": "string",
          "description": "The text to replace"
        },
        "new_string": {
          "type": "string",
          "description": "The text to replace it with (must be different from old_string)"
        },
        "replace_all": {
          "type": "boolean",
          "default": false,
          "description": "Replace all occurences of old_string (default false)"
        }
      },
      "required": [
        "file_path",
        "old_string",
        "new_string"
      ],
      "additionalProperties": false,
      "$schema": "http://json-schema.org/draft-07/schema#"
    }
  },
  {
    "name": "Write",
    "description": "...",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_path": {
          "type": "string",
          "description": "The absolute path to the file to write (must be absolute, not relative)"
        },
        "content": {
          "type": "string",
          "description": "The content to write to the file"
        }
      },
      "required": [
        "file_path",
        "content"
      ],
      "additionalProperties": false,
      "$schema": "http://json-schema.org/draft-07/schema#"
    }
  },

---

未来我们还需要扩展更多工具，我们先开展工具的开发这部分。
