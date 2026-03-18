import subprocess
import json


def test_list_files_tool():
    result = subprocess.run(
        ["uv", "run", "agent.py", "What files are in the wiki?"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"
    data = json.loads(result.stdout)

    assert "answer" in data
    assert "tool_calls" in data
    tools_used = [tc["tool"] for tc in data["tool_calls"]]
    assert "list_files" in tools_used


def test_read_file_tool():
    result = subprocess.run(
        ["uv", "run", "agent.py", "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"
    data = json.loads(result.stdout)

    assert "answer" in data
    assert "tool_calls" in data
    tools_used = [tc["tool"] for tc in data["tool_calls"]]
    assert "read_file" in tools_used
    assert "wiki/git" in (data.get("source") or "")