# filename: test_utils.py
# @Time    : 2024/5/8 17:25
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from src.ai_ide.utils import render_symbols


def test_render_symbols():
    # 示例数据，包含不同类型的符号
    symbols = [
        {
            "name": "DataManager",
            "kind": 5,  # 类
            "children": [
                {"name": "fetchData", "kind": 6, "containerName": "DataManager"},  # 方法
                {
                    "name": "dataVersion",
                    "kind": 7,
                    "containerName": "DataManager",
                },  # 属性
            ],
        },
        {
            "name": "User",
            "kind": 10,  # 枚举
            "children": [
                {"name": "ACTIVE", "kind": 8, "containerName": "User"},  # 字段
                {"name": "INACTIVE", "kind": 8, "containerName": "User"},  # 字段
            ],
        },
    ]

    # 调用函数并获取结果
    output = render_symbols(symbols, [5, 6, 7, 8, 10])
    assert (
        output
        == """Class: DataManager
  Method: fetchData
  Property: dataVersion
Enum: User
  Field: ACTIVE
  Field: INACTIVE"""
    )


def test_render_symbols_with_location():
    # 示例数据，包含不同类型的符号
    symbols = [
        {
            "name": "DataManager",
            "kind": 5,  # 类
            "location": {
                "range": {
                    "end": {"character": 13, "line": 19},
                    "start": {"character": 4, "line": 19},
                },
                "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/python_ide/test_pyright.py",
            },
            "children": [
                {
                    "name": "fetchData",
                    "kind": 6,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "DataManager",
                },  # 方法
                {
                    "name": "dataVersion",
                    "kind": 7,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "DataManager",
                },  # 属性
            ],
        },
        {
            "name": "User",
            "kind": 10,  # 枚举
            "location": {
                "range": {
                    "end": {"character": 13, "line": 19},
                    "start": {"character": 4, "line": 19},
                },
                "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/python_ide/test_pyright.py",
            },
            "children": [
                {
                    "name": "ACTIVE",
                    "kind": 8,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "User",
                },  # 字段
                {
                    "name": "INACTIVE",
                    "kind": 8,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "User",
                },  # 字段
            ],
        },
        {
            "name": "User",
            "kind": 11,
            "location": {
                "range": {
                    "end": {"character": 13, "line": 19},
                    "start": {"character": 4, "line": 19},
                },
                "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/python_ide/test_pyright.py",
            },
            "children": [
                {
                    "name": "ACTIVE",
                    "kind": 8,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "User",
                },  # 字段
                {
                    "name": "INACTIVE",
                    "kind": 8,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "User",
                },  # 字段
            ],
        },
    ]

    # 调用函数并获取结果
    output = render_symbols(symbols, [5, 6, 7, 8, 10])

    assert (
        output
        == """Class: DataManager Range(20:5-20:14)
  Method: fetchData Range(20:5-20:14)
  Property: dataVersion Range(20:5-20:14)
Enum: User Range(20:5-20:14)
  Field: ACTIVE Range(20:5-20:14)
  Field: INACTIVE Range(20:5-20:14)"""
    )


def test_render_symbols_with_illegal_kind():
    # 示例数据，包含不同类型的符号
    symbols = [
        {
            "name": "DataManager",
            "kind": 1,  # 类
            "location": {
                "range": {
                    "end": {"character": 13, "line": 19},
                    "start": {"character": 4, "line": 19},
                },
                "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/python_ide/test_pyright.py",
            },
            "children": [
                {
                    "name": "fetchData",
                    "kind": 6,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "DataManager",
                },  # 方法
                {
                    "name": "dataVersion",
                    "kind": 7,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "DataManager",
                },  # 属性
            ],
        },
        {
            "name": "User",
            "kind": 1,  # 枚举
            "location": {
                "range": {
                    "end": {"character": 13, "line": 19},
                    "start": {"character": 4, "line": 19},
                },
                "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/python_ide/test_pyright.py",
            },
            "children": [
                {
                    "name": "ACTIVE",
                    "kind": 8,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "User",
                },  # 字段
                {
                    "name": "INACTIVE",
                    "kind": 8,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "User",
                },  # 字段
            ],
        },
        {
            "name": "User",
            "kind": 1,
            "location": {
                "range": {
                    "end": {"character": 13, "line": 19},
                    "start": {"character": 4, "line": 19},
                },
                "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/python_ide/test_pyright.py",
            },
            "children": [
                {
                    "name": "ACTIVE",
                    "kind": 8,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "User",
                },  # 字段
                {
                    "name": "INACTIVE",
                    "kind": 8,
                    "location": {
                        "range": {
                            "end": {"character": 13, "line": 19},
                            "start": {"character": 4, "line": 19},
                        },
                        "uri": "file:///Users/jqq/PycharmProjects/TFRobotV2/tests/integration_tests/drive/tool/ides/"
                        "python_ide/test_pyright.py",
                    },
                    "containerName": "User",
                },  # 字段
            ],
        },
    ]

    # 调用函数并获取结果
    output = render_symbols(symbols, [5, 6, 7, 8, 10])

    assert output == ""
