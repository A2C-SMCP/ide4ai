# filename: test_async_docker_pyright.py
# @Time    : 2024/4/17 18:09
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import asyncio
import json
import socket
import time

import pytest
from cachetools import TTLCache

# 初始化缓存，设置大小和 TTL
response_cache = TTLCache(maxsize=1000, ttl=300)


async def message_receiver(reader: asyncio.StreamReader) -> None:
    """
    Receives and processes messages from a reader asynchronously. | 异步接收并处理来自读取器的消息。

    Args:
        reader: An asyncio.StreamReader object to read data from.

    Returns:
        None

    Raises:
        None

    The method receives and processes messages asynchronously. It reads data from the provided
    `reader` in chunks of 4096 bytes and decodes it as UTF-8 before appending it to a buffer.
    The method then searches for the position of the "Content-Length" declaration within the buffer.
    If found, it extracts the content length and checks if the buffer has enough data to contain the entire message.
    If the buffer is sufficient, it extracts the message, converts it to a dictionary using JSON decoding,
    and checks if the message has an "id". If the message has an "id", it adds the message to a response cache.
    Finally, it removes the processed message from the buffer by skipping the content length.

    Note: This method assumes a specific message format where the content length is declared using "Content-Length:"
    followed by the actual content length in bytes. The message is assumed to be a JSON-formatted string.

    该方法异步接收并处理消息。它从provided中以4096字节的块读取数据`reader`，并在添加到缓冲区之前将其解码为UTF-8。该方法然后在缓冲区内搜索
    "Content-Length"声明的位置。如果找到，它会提取内容长度并检查缓冡区是否有足够的数据包含整个消息。如果缓冲区足够，它提取消息，使用JSON解码将其转换为字典，
    并检查消息是否有一个"id"。如果消息有一个"id"，它将消息添加到响应缓存。最后，它通过跳过内容长度从缓冲区中删除已处理的消息。

    注意：该方法假设一种特殊的消息格式，即使用 "Content-Length:" 声明内容长度
    后面跟着实际的内容长度（以字节为单位）。假定消息是一个JSON格式化的字符串。
    """
    # 创建空 buffer 来接收数据
    buffer = ""

    # 无限循环，接收和处理数据
    while True:
        # 异步读取数据，最多读取 4096 字节
        data = await reader.read(4096)

        # 解码数据，并添加到 buffer 中
        buffer += data.decode("utf-8")

        while "\r\n\r\n" in buffer:
            # 查找内容长度声明的位置
            content_length_pos = buffer.find("Content-Length: ")
            if content_length_pos == -1:
                break  # 这里必须使用break，否则会引起死循环

            content_length_start = content_length_pos + 16
            content_length_end = buffer.find("\r\n", content_length_start)

            # 提取内容长度
            content_length = int(buffer[content_length_start:content_length_end].strip())

            message_start = content_length_end + 4
            message_end = message_start + content_length

            # 检查 buffer 长度是否足以包含整个消息
            if len(buffer) < message_end:
                break  # 这里必须使用break，否则会引起死循环

            # 从 buffer 中提取消息
            message = buffer[message_start:message_end]
            dict_data = json.loads(message.strip())

            # 如果消息有 id，将其添加到缓存中
            if dict_data.get("id"):
                response_cache[int(dict_data["id"])] = message

            # 删除已处理的消息，越过 content_length
            buffer = buffer[message_end:]


async def send_message(
    writer: asyncio.StreamWriter,
    method: str,
    params: dict = None,
    message_id: int = None,
) -> None:
    """
    Args:
        writer: The asyncio.StreamWriter object used to send the message.
        method: The name of the JSON-RPC method to be invoked.
        params: The parameters to be passed to the JSON-RPC method. (default: None)
        message_id: The ID of the JSON-RPC message. (default: None)

    Returns:
        None

    """
    message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if message_id is not None:
        message["id"] = message_id
    message_json = json.dumps(message)
    content_length = len(message_json.encode("utf-8"))
    full_message = f"Content-Length: {content_length}\r\n\r\n{message_json}"
    writer.write(full_message.encode("utf-8"))
    await writer.drain()


async def receive_message(expected_id: int, timeout=5) -> str:
    end_time = time.time() + timeout
    while time.time() < end_time:
        response = response_cache.get(expected_id)
        if response:
            return response
        await asyncio.sleep(0.1)
    return f"No response received within {timeout} seconds."


def is_docker_running_on_port(d_host: str, d_port: int) -> bool:
    try:
        sock = socket.create_connection((d_host, d_port), timeout=1)
        sock.close()
        return True
    except (TimeoutError, ConnectionRefusedError):
        return False


@pytest.fixture(scope="module")
def docker_check():
    d_host = "localhost"
    d_port = 3000
    docker_running = is_docker_running_on_port(d_host, d_port)
    return d_host, d_port, docker_running


@pytest.mark.asyncio
@pytest.mark.skipif(not is_docker_running_on_port("localhost", 3000), reason="Docker is not running on port 3000")
async def test_docker_pyright_process_async(docker_check):
    """

    This method is used to test the `test_docker_pyright_process_async` function.

    Parameters:
        - None

    Returns:
        - None

    Example usage:
        ```
        await test_docker_pyright_process_async()
        ```

    This method opens a connection to a specified host and port using asyncio. It then creates a task to handle message
    receiving. After that, it sends an "initialize" message with some parameters, waits for a response, and prints the
    response. Next, it sends a "shutdown" message, waits for a response, and prints the response. Finally, it cancels
    the task, closes the writer, and waits until the writer is closed.

    Note: This method assumes the existence of the following helper functions:
    - message_receiver
    - send_message
    - receive_message

    These functions should be implemented separately.

    """
    host, port, docker_running = docker_check
    reader, writer = await asyncio.open_connection(host, port)

    task = asyncio.create_task(message_receiver(reader))

    await send_message(
        writer,
        "initialize",
        {"processId": None, "rootUri": "file:////app", "capabilities": {}},
        message_id=1,
    )
    await asyncio.sleep(1)
    print("初始化请求的返回:")
    res_1 = await receive_message(1)
    print(res_1)
    assert json.loads(res_1)["id"] == 1

    await send_message(writer, "shutdown", message_id=5)
    await asyncio.sleep(1)
    print("退出命令的返回:")
    res_5 = await receive_message(5)
    print(res_5)
    assert json.loads(res_5)["id"] == 5

    task.cancel()
    try:
        await task  # 等待任务结束
    except asyncio.CancelledError:
        pass  # 如果任务被取消，则不做任何事情
    writer.close()
    await writer.wait_closed()  # 省的话会阻塞直到该流被关闭，防止过早结束程序
