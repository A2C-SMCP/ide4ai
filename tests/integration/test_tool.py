# filename: test_tool.py
# @Time    : 2024/5/14 16:06
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import pytest


def test_ide_singleton(apply_edits_tool, create_file_tool) -> None:
    """
    Test the singleton of IDE.

    Args:
        apply_edits_tool:
        create_file_tool:

    Returns:

    """
    assert apply_edits_tool._ide is create_file_tool._ide


def test_create_file(create_file_tool) -> None:
    """
    Test the creation of a file.

    Args:
        create_file_tool:

    Returns:

    """
    new_file_uri = f"file://{create_file_tool.root_dir}/print_without_os.py"
    res = create_file_tool.run(tool_params={"uri": new_file_uri})
    print(res)


def test_create_file_with_init_content(create_file_tool) -> None:
    """
    Test the creation of a file with initial content.

    Args:
        create_file_tool:

    Returns:

    """
    new_file_uri = f"file://{create_file_tool.root_dir}/write_with_init_content.py"

    res_with_init_content = create_file_tool.run(
        tool_params={"uri": new_file_uri, "init_content": "import os\nprint(os.path)"}
    )
    print(res_with_init_content)
    assert "import os" in res_with_init_content.origin
    print(res_with_init_content)


def test_read_file(create_file_tool, read_file_tool) -> None:
    """
    Test the reading of a file.

    Args:
        read_file_tool:

    Returns:
    """
    new_file_uri = f"file://{read_file_tool.root_dir}/print_without_os.py"
    res = create_file_tool.run(tool_params={"uri": new_file_uri})
    print(res)
    res = read_file_tool.run(tool_params={"uri": new_file_uri})
    print(res)


def test_open_file(create_file_tool, open_file_tool) -> None:
    """
    Test open a file.

    Returns:
    """
    new_file_uri = f"file://{open_file_tool.root_dir}/print_without_os.py"
    res = create_file_tool.run(tool_params={"uri": new_file_uri})
    print(res)
    res = open_file_tool.run(tool_params={"uri": new_file_uri})
    print(res)
    assert "1    |" in res.origin
    assert ">primary|1:1<" not in res.origin


def test_apply_edit(create_file_tool, apply_edits_tool) -> None:
    """
    Test the application of edits.

    Args:
        create_file_tool:
        apply_edits_tool:

    Returns:

    """
    new_file_uri = f"file://{create_file_tool.root_dir}/print_without_os.py"
    res = create_file_tool.run(tool_params={"uri": new_file_uri})
    print(res)
    res = apply_edits_tool.run(
        tool_params={
            "uri": new_file_uri,
            "edits": [
                {
                    "range": {"start_position": [6, -1], "end_position": [6, -1]},
                    "new_text": "\n\nprint('Hello, world!')\n",
                }
            ],
        }
    )
    print(res)


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_ai_editor_init(ai_editor, create_file_tool, apply_edits_tool) -> None:
    """
    Test the initialization of the AI editor.

    Returns:

    """
    new_file_uri = f"file://{create_file_tool.root_dir}/print_without_os.py"
    res = create_file_tool.run(tool_params={"uri": new_file_uri})
    print(res)
    res = apply_edits_tool.run(
        tool_params={
            "uri": new_file_uri,
            "edits": [
                {
                    "range": {"start_position": [6, -1], "end_position": [6, -1]},
                    "new_text": "\n\nprint(os.path)\n",
                }
            ],
        }
    )
    print(res)
    res = ai_editor.run(
        tool_params={"job_des": "帮我解决一下print_without_os.py（位置项目根目录下）中的未正确导入的语法错误"}
    )
    print(res)
    with open(f"{ai_editor.root_dir}/print_without_os.py") as f:
        content = f.read()
    assert "import os" in content
    print(content)


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_ai_editor_wm_create_file(ai_editor, create_file_tool, apply_edits_tool) -> None:
    res = ai_editor.run(
        tool_params={"job_des": "帮我在项目根目录创建一个print_without_os.py文件，然后写入 import os\nprint(os.path)\n"}
    )
    print(res)
    with open(f"{ai_editor.root_dir}/print_without_os.py") as f:
        content = f.read()
    assert "import os" in content
    print("--------" * 3)
    print(content)


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_gpt_editor_create_file(gpt_editor, create_file_tool, apply_edits_tool) -> None:
    res = gpt_editor.run(
        tool_params={"job_des": "帮我在项目根目录创建一个print_without_os.py文件，然后写入 import os\nprint(os.path)\n"}
    )
    print(res)
    with open(f"{gpt_editor.root_dir}/print_without_os.py") as f:
        content = f.read()
    assert "import os" in content
    print("--------" * 3)
    print(content)


@pytest.mark.skip(reason="手动执行，QWQ目前的工具调用能力还无法完成此类任务")
@pytest.mark.xfail(reason="QWQ目前的工具调用能力还无法完成此类任务")
def test_ollama_editor_create_file(ollama_editor, create_file_tool, apply_edits_tool) -> None:
    res = ollama_editor.run(
        tool_params={"job_des": "帮我在项目根目录创建一个print_without_os.py文件，然后写入 import os\nprint(os.path)\n"}
    )
    print(res)
    with open(f"{ollama_editor.root_dir}/print_without_os.py") as f:
        content = f.read()
    assert "import os" in content
    print("--------" * 3)
    print(content)
