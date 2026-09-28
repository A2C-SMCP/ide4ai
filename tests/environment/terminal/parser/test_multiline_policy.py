"""Executable shell syntax must be distinguished from quoted/heredoc data."""

import pytest

from ide4ai.environment.terminal.command_filter import CommandFilterConfig


@pytest.mark.parametrize(
    "command",
    [
        "cat <<EOF\n`touch x`\nEOF",
        "cat <<EOF\n$(echo hi) `touch x`\nEOF",
        "echo hi\ntouch x",
        "echo hi & touch x",
        "echo hi # comment\ntouch x",
        "cat <<EOF\ndata\nEOF\ntouch x",
        "cat <<'EOF'\ndata\nEOF\ntouch x",
        "cat <<< 'data'\ntouch x",
        "echo '<<EOF'\ntouch x",
        'echo "$(touch x)"',
        "echo `touch x`",
        "cat <(touch x)",
        "cat <<EOF\n$(touch x)\nEOF",
        "echo $((1 + $(touch x)))",
    ],
)
def test_all_executable_commands_are_checked(command):
    assert not CommandFilterConfig.from_white_list(["echo", "cat"]).is_allowed(command)
    assert not CommandFilterConfig.allow_all_except(["touch"]).is_allowed(command)


@pytest.mark.parametrize(
    "command",
    [
        "echo one\necho two",
        "echo 'one\ntouch x'",
        'echo "one\ntouch x"',
        "echo ';' touch x",
        r"echo \; touch x",
        "echo one \\\ntwo",
        "cat <<'EOF'\n$(touch x)\nEOF",
        'cat <<EOF\ntouch x\n"data\nEOF',
        "cat <<-EOF\n\tdata\n\tEOF",
        "cat <<< 'one\ntouch x'",
    ],
)
def test_quoted_words_and_heredoc_bodies_are_data(command):
    assert CommandFilterConfig.from_white_list(["echo", "cat"]).is_allowed(command)


def test_invalid_shell_syntax_fails_closed():
    assert not CommandFilterConfig.allow_all().is_allowed("cat <<EOF\nmissing delimiter")


@pytest.mark.timeout(10)
def test_real_pty_rejects_multiline_before_any_command_runs(tmp_path):
    from ide4ai.environment.terminal.base import EnvironmentArguments
    from ide4ai.environment.terminal.pexpect_terminal_env import PexpectTerminalEnv

    marker = tmp_path / "unauthorized"
    env = PexpectTerminalEnv(
        args=EnvironmentArguments(image_name="local", timeout=2),
        work_dir=str(tmp_path),
        cmd_filter=CommandFilterConfig.from_white_list(["echo", "cat"]),
    )
    try:
        with pytest.raises(ValueError, match="not in whitelist"):
            env.step({"category": "terminal", "action_name": f"echo safe\ntouch {marker}", "action_args": []})
        assert not marker.exists()
        recovered = env.step({"category": "terminal", "action_name": "echo still-usable", "action_args": []})
        assert recovered[3] is True
        assert "still-usable" in recovered[0]["obs"]
    finally:
        env.close()
