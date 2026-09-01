"""Historical HTTP entry point retained to explain the multi-project transport boundary."""


def main() -> None:
    raise SystemExit(
        "Streamable HTTP is not supported by the multi-project MCP server. Configure a stdio MCP client instead."
    )


if __name__ == "__main__":
    main()
