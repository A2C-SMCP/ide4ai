import os
import tempfile
from pathlib import Path

import pytest
from pydantic import AnyUrl

from ide4ai.environment.workspace.uri_utils import file_uri_to_path, normalize_tool_file_path, path_to_file_uri


class TestFileUriToPath:
    """Unit tests for file_uri_to_path utility function."""

    def test_ascii_path(self) -> None:
        assert file_uri_to_path("file:///tmp/test.py") == "/tmp/test.py"

    def test_chinese_path(self) -> None:
        assert file_uri_to_path("file:///tmp/淘宝报告.md") == "/tmp/淘宝报告.md"

    def test_percent_encoded_chinese_path(self) -> None:
        """After AnyUrl construction, Chinese chars are percent-encoded."""
        uri = AnyUrl("file:///tmp/淘宝报告.md")
        assert file_uri_to_path(str(uri)) == "/tmp/淘宝报告.md"

    def test_mixed_path(self) -> None:
        uri = AnyUrl("file:///Users/test/项目/src/main.py")
        assert file_uri_to_path(str(uri)) == "/Users/test/项目/src/main.py"

    def test_no_file_prefix_rejected(self) -> None:
        """Plain paths must not be implicitly URL-decoded."""
        with pytest.raises(ValueError, match="Expected file:// URI"):
            file_uri_to_path("/tmp/test.py")

    def test_already_decoded_path(self) -> None:
        """unquote on already-decoded string is a no-op."""
        assert file_uri_to_path("file:///tmp/already_中文.md") == "/tmp/already_中文.md"

    def test_spaces_in_path(self) -> None:
        uri = AnyUrl("file:///tmp/my file.py")
        assert file_uri_to_path(str(uri)) == "/tmp/my file.py"

    def test_localhost_file_uri(self) -> None:
        assert file_uri_to_path("file://localhost/tmp/test.py") == "/tmp/test.py"

    def test_remote_file_uri_rejected(self) -> None:
        with pytest.raises(ValueError, match="Remote file URI"):
            file_uri_to_path("file://server/share/test.py")


class TestPathToFileUri:
    def test_chinese_path_to_uri(self) -> None:
        uri = path_to_file_uri("/tmp/淘宝报告.md")
        assert uri == "file:///tmp/%E6%B7%98%E5%AE%9D%E6%8A%A5%E5%91%8A.md"

    def test_percent_literal_is_encoded(self) -> None:
        uri = path_to_file_uri("/tmp/a%20b.py")
        assert uri == "file:///tmp/a%2520b.py"


class TestNormalizeToolFilePath:
    def test_plain_path_is_not_unquoted(self) -> None:
        file_uri, fs_path = normalize_tool_file_path("/tmp/a%20b.py")
        assert fs_path == "/tmp/a%20b.py"
        assert file_uri == "file:///tmp/a%2520b.py"

    def test_file_uri_is_decoded_and_canonicalized(self) -> None:
        file_uri, fs_path = normalize_tool_file_path("file:///tmp/a%2520b.py")
        assert fs_path == "/tmp/a%20b.py"
        assert file_uri == "file:///tmp/a%2520b.py"


class TestChinesePathFileSystemOps:
    """Regression tests: verify file operations work with Chinese paths."""

    def test_create_and_read_chinese_file(self) -> None:
        """Simulate the exact MCP Write→Read flow with a Chinese filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "巡店报告.md")
            uri = f"file://{file_path}"

            # Simulate Write: create file via extracted path
            extracted = file_uri_to_path(uri)
            assert extracted == file_path

            with open(extracted, "w", encoding="utf-8") as f:
                f.write("# 巡店报告\n")

            # Simulate Read: verify file exists and content matches
            assert os.path.exists(extracted)
            with open(extracted, encoding="utf-8") as f:
                assert f.read() == "# 巡店报告\n"

    def test_anyurl_roundtrip_chinese_path(self) -> None:
        """AnyUrl percent-encodes, file_uri_to_path decodes back correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            real_path = os.path.join(tmpdir, "淘宝报告.md")
            uri = AnyUrl(f"file://{real_path}")

            # Write using decoded path
            decoded = file_uri_to_path(str(uri))
            assert decoded == real_path
            Path(decoded).write_text("hello", encoding="utf-8")

            # Read back
            assert Path(decoded).read_text(encoding="utf-8") == "hello"
