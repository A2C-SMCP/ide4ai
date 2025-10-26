# -*- coding: utf-8 -*-
# filename: test_pyright.py
# @Time    : 2024/4/17 12:20
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import json
import pprint
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator, Optional

import pytest
from cachetools import TTLCache


@pytest.fixture
def workspace_root() -> str:
    current_file_path = Path(__file__).resolve()
    root_path = current_file_path.parent.parent.parent.parent.parent.parent.parent
    return str(root_path)


@pytest.fixture
def fake_py_with_err_path(workspace_root) -> Generator[str, Any, None]:
    with tempfile.NamedTemporaryFile() as f:
        f.write(
            b"""# -*- coding: utf-8 -*-
# filename: fake_py_with_err.py.py
# @Time    : 2024/4/29 10:24
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import pydantic


def test():
    print("pydantic")


print(os.path)
"""
        )
        f.flush()
        yield f.name


def send_message(
    process: subprocess.Popen,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    message_id: Optional[int] = None,
) -> None:
    message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if message_id is not None:
        message["id"] = message_id

    # 转换成 JSON 字符串
    message_json = json.dumps(message)
    # 计算 content length
    content_length = len(message_json.encode("utf-8"))
    # 发送请求
    full_message = f"Content-Length: {content_length}\r\n\r\n{message_json}"
    process.stdin.write(full_message.encode("utf-8"))
    process.stdin.flush()


def receive_message(process: subprocess.Popen, expected_id: int, cache: TTLCache) -> str:
    print("打印Pyright进程输出:")
    while True:
        line = process.stdout.readline()
        line_str = line.decode("utf-8")
        print(line_str)
        if "Content-Length:" in line_str:
            length = int(line_str.split(":")[1].strip())
            response = process.stdout.read(length + 2)  # 之所以+2，是因为还有一个换行符(\r\n)
            response_str = response.decode("utf-8")
            response_data = json.loads(response_str.strip())
            pprint.pprint(response_data)
            # 将结果存储在缓存中，使用响应的id作为key
            if "id" in response_data and response_data["id"] == expected_id:
                cache[response_data["id"]] = response
                break
        else:
            # 跳过无关的日志信息
            continue
    return cache[expected_id]


def handle_diagnostics(process: subprocess.Popen) -> str:
    """
    处理诊断信息

    Args:
        process:

    Returns:

    """
    n = 0
    while n < 10:
        line = process.stdout.readline()
        line_str = line.decode("utf-8")
        print(line_str)
        if "Content-Length:" in line_str:
            length = int(line_str.split(":")[1].strip())
            response = process.stdout.read(length + 2)  # 之所以+2，是因为还有一个换行符(\r\n)
            response_str = response.decode("utf-8")
            response_data = json.loads(response_str.strip())
            pprint.pprint(response_data)
            if response_data.get("method") == "textDocument/publishDiagnostics":
                return response
        else:
            n += 1
            continue


def test_pyright_process(workspace_root) -> None:
    """
    测试启动一个pyright-langserver服务作用子进程运行。最终退出
    Returns:

    """
    # 启动 Pyright 语言服务器
    process = subprocess.Popen(
        ["pyright-langserver", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=False,
    )
    # 设置一个大小为1000的缓存，可以根据需要调整TTL
    response_cache = TTLCache(maxsize=1000, ttl=300)  # TTL为300秒
    try:
        # 发送初始化请求
        send_message(
            process,
            "initialize",
            {
                "processId": None,
                "workspaceFolders": [{"uri": f"file://{workspace_root}", "name": "TFRobotV2"}],
                "initializationOptions": {"disablePullDiagnostics": True},
                "capabilities": {},
            },
            message_id=1,
        )

        # 打印响应
        res_1 = receive_message(process, expected_id=1, cache=response_cache)
        assert json.loads(res_1)["id"] == 1

        # 发送退出命令
        send_message(process, "shutdown", message_id=5)
        res_5 = receive_message(process, expected_id=5, cache=response_cache)
        assert json.loads(res_5)["id"] == 5

    finally:
        # 关闭进程
        process.stdin.close()
        process.terminate()
        process.wait()


def test_lsp_diagnostic_notification(workspace_root, fake_py_with_err_path) -> None:
    """
    测试LSP对一个语法错误文件的检查机制

    Returns:

    """
    # 启动 Pyright 语言服务器
    process = subprocess.Popen(
        ["pyright-langserver", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=False,
    )
    # 设置一个大小为1000的缓存，可以根据需要调整TTL
    response_cache = TTLCache(maxsize=1000, ttl=300)  # TTL为300秒
    try:
        # 发送初始化请求
        send_message(
            process,
            "initialize",
            {
                "processId": None,
                "workspaceFolders": [{"uri": f"file://{workspace_root}", "name": "TFRobotV2"}],
                "initializationOptions": {
                    "disablePullDiagnostics": True,
                },
                "capabilities": {
                    "textDocument": {
                        "synchronization": {
                            "dynamicRegistration": False,
                            "willSave": True,
                            "didSave": True,
                            "willSaveWaitUntil": True,
                        },
                        "publishDiagnostics": {
                            "relatedInformation": True,
                            "versionSupport": True,
                            "codeDescriptionSupport": True,
                            "dataSupport": True,
                        },
                        "diagnostic": {
                            "dynamicRegistration": True,
                            "relatedDocumentSupport": True,
                        },
                        "codeAction": {
                            "dataSupport": True,
                        },
                    },
                    "workspace": {
                        "applyEdit": True,
                        "workspaceEdit": {
                            "documentChanges": True,
                            "resourceOperations": ["create", "rename", "delete"],
                        },
                        "diagnostics": {
                            "refreshSupport": True,
                        },
                        "fileOperations": {
                            "didCreate": True,
                            "didRename": True,
                            "didDelete": True,
                        },
                    },
                },
            },
            message_id=1,
        )

        # 打印响应
        res_1 = receive_message(process, expected_id=1, cache=response_cache)
        assert json.loads(res_1)["id"] == 1

        # 发送initialized通知
        send_message(process, "initialized")

        # 发送文本打开通知
        err_py_path = fake_py_with_err_path
        with open(err_py_path, "r") as f:
            content = f.read()

        # 需要注意textDocument/didOpen是一个Notification，并不是method，所以不需要ID，也无法获取返回。如果输出ID会作为method处理，会发生异常
        send_message(
            process,
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": f"file://{err_py_path}",
                    "languageId": "python",
                    "version": 1,
                    "text": content,
                }
            },
        )

        # 发送文本变更通知
        send_message(
            process,
            "textDocument/didChange",
            {
                "textDocument": {
                    "uri": f"file://{err_py_path}",
                    "version": 2,
                },
                "contentChanges": [
                    {
                        "range": {
                            "start": {"line": 0, "character": 1},
                            "end": {"line": 0, "character": 1},
                        },
                        "text": "a",
                    }
                ],
            },
        )

        diagnostics = handle_diagnostics(process)
        assert any(
            '"os" is not defined' in diagnostic["message"]
            for diagnostic in json.loads(diagnostics)["params"]["diagnostics"]
        )

        # 发送诊断请求
        send_message(
            process,
            "textDocument/codeAction",
            {
                "textDocument": {"uri": f"file://{err_py_path}"},
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 7, "character": 14},
                },
                "context": {"diagnostics": json.loads(diagnostics)["params"]["diagnostics"]},
            },
            message_id=3,
        )

        res_3 = receive_message(process, expected_id=3, cache=response_cache)
        assert json.loads(res_3)["id"] == 3

        # 发送退出命令
        send_message(process, "shutdown", message_id=999)
        print("结束动作的返回")
        res_999 = receive_message(process, expected_id=999, cache=response_cache)
        pprint.pprint(json.loads(res_999))
        assert json.loads(res_999)["id"] == 999

    finally:
        # 关闭进程
        process.stdin.close()
        process.terminate()
        process.wait()


def test_get_file_symbols(workspace_root) -> None:
    """
    测试启动一个pyright-langserver服务作用子进程运行。尝试获取文件的structures
    Returns:

    """
    # 启动 Pyright 语言服务器
    process = subprocess.Popen(
        ["pyright-langserver", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=False,
    )
    # 设置一个大小为1000的缓存，可以根据需要调整TTL
    response_cache = TTLCache(maxsize=1000, ttl=300)  # TTL为300秒
    try:
        # 发送初始化请求
        send_message(
            process,
            "initialize",
            {
                "processId": None,
                "workspaceFolders": [
                    {
                        "uri": f"file://{workspace_root}",
                        "name": "TFRobotV2",
                    }
                ],
                "initializationOptions": {
                    "disablePullDiagnostics": True,
                },
                "capabilities": {
                    "textDocument": {
                        "synchronization": {
                            "dynamicRegistration": False,
                            "willSave": True,
                            "didSave": True,
                            "willSaveWaitUntil": True,
                        },
                        "publishDiagnostics": {
                            "relatedInformation": True,
                            "versionSupport": True,
                            "codeDescriptionSupport": True,
                            "dataSupport": True,
                        },
                        "diagnostic": {
                            "dynamicRegistration": True,
                            "relatedDocumentSupport": True,
                        },
                        "codeAction": {
                            "dataSupport": True,
                        },
                        "documentSymbol": {"symbolKind": {"valueSet": [5, 6, 7, 8, 10]}},
                    },
                    "workspace": {
                        "applyEdit": True,
                        "workspaceEdit": {
                            "documentChanges": True,
                            "resourceOperations": ["create", "rename", "delete"],
                        },
                        "diagnostics": {
                            "refreshSupport": True,
                        },
                        "fileOperations": {
                            "didCreate": True,
                            "didRename": True,
                            "didDelete": True,
                        },
                    },
                },
            },
            message_id=1,
        )

        # 打印响应
        res_1 = receive_message(process, expected_id=1, cache=response_cache)
        assert json.loads(res_1)["id"] == 1

        # 发送initialized通知
        send_message(process, "initialized")

        # 发送文本打开通知
        err_py_path = f"{workspace_root}/tests/integration_tests/drive/tool/ides/python_ide/test_pyright.py"
        with open(err_py_path, "r") as f:
            content = f.read()

        # 需要注意textDocument/didOpen是一个Notification，并不是method，所以不需要ID，也无法获取返回。如果输出ID会作为method处理，会发生异常
        send_message(
            process,
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": f"file://{err_py_path}",
                    "languageId": "python",
                    "version": 1,
                    "text": content,
                }
            },
        )

        # 发送查看文件结构请求
        send_message(
            process,
            "textDocument/documentSymbol",
            {"textDocument": {"uri": f"file://{err_py_path}"}},
            message_id=2,
        )

        res_2 = receive_message(process, expected_id=2, cache=response_cache)
        assert json.loads(res_2)["id"] == 2

        # 发送退出命令
        send_message(process, "shutdown", message_id=5)
        res_5 = receive_message(process, expected_id=5, cache=response_cache)
        assert json.loads(res_5)["id"] == 5

    finally:
        # 关闭进程
        process.stdin.close()
        process.terminate()
        process.wait()
