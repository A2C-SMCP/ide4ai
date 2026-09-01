"""Historical HTTP entry point retained to explain the multi-project V1 boundary."""


def main() -> None:
    raise SystemExit(
        "Streamable HTTP is not supported by the multi-project MCP V1. Configure a legacy stdio MCP client instead."
    )


if __name__ == "__main__":
    main()
