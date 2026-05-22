from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname


def file_uri_to_path(uri: str) -> str:
    """Convert a local file:// URI to a filesystem path."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Expected file:// URI, got: {uri}")
    if parsed.netloc not in ("", "localhost"):
        raise ValueError(f"Remote file URI is not supported: {uri}")
    return url2pathname(parsed.path)


def path_to_file_uri(path: str | Path) -> str:
    """Convert a filesystem path to a file:// URI."""
    return Path(path).absolute().as_uri()


def normalize_tool_file_path(value: str | Path) -> tuple[str, str]:
    """Return (file_uri, fs_path) for a tool input that may be a path or file:// URI."""
    value_str = str(value)
    if value_str.startswith("file://"):
        fs_path = file_uri_to_path(value_str)
        return path_to_file_uri(fs_path), fs_path
    return path_to_file_uri(value_str), value_str
