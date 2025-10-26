# -*- coding: utf-8 -*-
# filename: test_docker_pyright.py
# @Time    : 2024/4/17 17:08
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import json
import socket
import threading
import time
from queue import Empty
from typing import Any, Dict, Optional

import pytest
from cachetools import TTLCache

# 初始化缓存，设置大小和 TTL
response_cache = TTLCache(maxsize=1000, ttl=300)  # TTL 为 300 秒

# 初始化消息队列的事件标志
start_event = threading.Event()


def message_receiver(sock):
    print("Thread started, waiting for data...")
    start_event.set()  # 通知主线程已经开始执行
    buffer = ""
    while True:
        data = sock.recv(4096).decode("utf-8")
        buffer += data

        # 处理可能接收到的多个消息
        while "\r\n\r\n" in buffer:
            # 查找第一个 Content-Length 标头
            content_length_pos = buffer.find("Content-Length: ")
            if content_length_pos == -1:
                break  # 如果没有找到 Content-Length，继续接收数据

            # 解析 Content-Length 的值
            content_length_start = content_length_pos + 16  # 跳过 "Content-Length: "
            content_length_end = buffer.find("\r\n", content_length_start)
            content_length = int(buffer[content_length_start:content_length_end].strip())

            # 检查是否接收到了完整的消息
            message_start = content_length_end + 4  # 跳过后续的 "\r\n\r\n"
            message_end = message_start + content_length
            if len(buffer) < message_end:
                break  # 如果没有接收完整，继续接收数据

            # 提取消息
            message = buffer[message_start:message_end]
            dict_data = json.loads(message.strip())  # 返回解析后的 JSON 对象
            if dict_data.get("id"):
                response_cache[int(dict_data["id"])] = message  # 将响应存储在缓存中

            # 截断缓冲区以处理下一个消息
            buffer = buffer[message_end:]


def send_message(
    sock: socket.socket,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    message_id: Optional[int] = None,
) -> None:
    message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if message_id is not None:
        message["id"] = message_id

    # 将消息转换成 JSON 字符串
    message_json = json.dumps(message)
    # 计算 content length
    content_length = len(message_json.encode("utf-8"))
    # 构造完整的消息，包括 HTTP-like 头
    full_message = f"Content-Length: {content_length}\r\n\r\n{message_json}"
    # 发送消息
    sock.sendall(full_message.encode("utf-8"))


def receive_message(expected_id: int, timeout=5) -> str:
    end_time = time.time() + timeout
    try:
        while time.time() < end_time:
            response = response_cache.get(expected_id)
            if response:
                return response
            else:
                time.sleep(0.1)  # 防止紧密循环
    except Empty:
        return f"No response received within {timeout} seconds."  # 超时后返回错误信息


def is_docker_running_on_port(d_host: str, d_port: int) -> bool:
    try:
        sock = socket.create_connection((d_host, d_port), timeout=1)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError):
        return False


@pytest.fixture(scope="module")
def docker_check():
    host = "localhost"
    port = 3000
    docker_running = is_docker_running_on_port(host, port)
    return host, port, docker_running


@pytest.mark.skipif(not is_docker_running_on_port("localhost", 3000), reason="Docker is not running on port 3000")
def test_docker_pyright_process(docker_check) -> None:
    host, port, docker_running = docker_check
    # 连接到 Docker 容器中的 pyright-langserver
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        # 启动接收线程
        receiver_thread = threading.Thread(target=message_receiver, args=(sock,), daemon=True)
        receiver_thread.start()
        start_event.wait()  # 等待接收线程真正开始运行

        # 发送初始化请求
        send_message(
            sock,
            "initialize",
            {"processId": None, "rootUri": "file:////app", "capabilities": {}},
            message_id=1,
        )
        time.sleep(1)  # 给服务器时间来响应
        print("初始化请求的返回:")
        res_1 = receive_message(1)
        print(res_1)
        assert json.loads(res_1)["id"] == 1

        # 发送退出命令
        send_message(sock, "shutdown", message_id=5)
        time.sleep(1)  # 给服务器时间来响应
        print("退出命令的返回:")
        res_5 = receive_message(5)
        print(res_5)
        assert json.loads(res_5)["id"] == 5
