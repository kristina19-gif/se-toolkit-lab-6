import sys
import os
import json
import urllib.request
from pathlib import Path
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).parent.resolve()


# ─── Environment ──────────────────────────────────────────────────────────────
def load_env():
    env = {**dotenv_values(".env.agent.secret"), **dotenv_values(".env.docker.secret")}
    env.update(os.environ)
    return env


# ─── Tools ────────────────────────────────────────────────────────────────────
def safe_path(path):
    p = (PROJECT_ROOT / path).resolve()
    if not str(p).startswith(str(PROJECT_ROOT)):
        return None
    return p


def tool_read_file(path):
    p = safe_path(path)
    if not p:
        return "Error: access denied (path outside project root)"
    try:
        content = p.read_text(encoding="utf-8")
        # Limit to 8000 chars to avoid overwhelming the LLM context
        if len(content) > 8000:
            content = content[:8000] + "\n...[truncated]"
        return content
    except Exception as e:
        return f"Error: {e}"


def tool_list_files(path):
    p = safe_path(path)
    if not p:
        return "Error: access denied (path outside project root)"
    try:
        entries = sorted(f.name for f in p.iterdir())
        return "\n".join(entries)
    except Exception as e:
        return f"Error: {e}"


def tool_query_api(env, method, path, body=None):
    base = env.get("AGENT_API_BASE_URL", "http://localhost:42002").rstrip("/")
    url = f"{base}{path}"
    data = body.encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    api_key = env.get("LMS_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode()
            return json.dumps({"status_code": resp.status, "body": text})
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        return json.dumps({"status_code": e.code, "body": body_text})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Tool schemas ──────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file in the project. "
                "Use this for source code questions (backend/, frontend/), "
                "for reading wiki articles, or any local file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root, e.g. 'backend/app/main.py' or 'wiki/git.md'",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List files in a directory of the project. "
                "Use this to discover what wiki articles exist or what files are in a folder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root, e.g. 'wiki' or 'backend/app'",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": (
                "Send an HTTP request to the deployed backend API. "
                "Use this for runtime/live data questions: item counts, scores, analytics, "
                "status codes returned by endpoints, or any question about what the system does at runtime. "
                "Do NOT use for documentation or source code questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method: GET, POST, PUT, DELETE, etc.",
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path, e.g. '/items/' or '/analytics/completion-rate?lab=lab-99'",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON body as a string for POST/PUT requests.",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a helpful assistant for a software engineering lab project.

You have access to three tools:
- list_files: list files in a directory (use to explore wiki/ or source code directories)
- read_file: read a file (use for wiki articles, source code, config files)
- query_api: call the deployed backend API (use for live data: item counts, scores, analytics, runtime behavior)

Guidelines for choosing tools:
- Documentation/wiki questions → list_files("wiki") then read_file the relevant wiki article
- Source code questions (framework, architecture, implementation) → read_file the relevant source file
- Runtime/data questions (how many items, scores, completion rates) → query_api
- Multi-step questions may require chaining tools

When you have gathered enough information, respond with a final JSON object in this exact format:
{"answer": "...", "source": "...", "tool_calls": [...]}

The "source" field should reference the main file or API endpoint used.
The "tool_calls" field is populated automatically — do not add it yourself.
Just provide your final answer as plain text when you are ready.
"""


# ─── LLM call ─────────────────────────────────────────────────────────────────
def llm_call(env, messages):
    api_key = env.get("LLM_API_KEY", "")
    api_base = env.get("LLM_API_BASE", "").rstrip("/")
    model = env.get("LLM_MODEL", "")

    url = f"{api_base}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": TOOLS,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


# ─── Agent logic ──────────────────────────────────────────────────────────────
def run_agent(env, question):
    tool_calls_log = []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    source = ""

    for _ in range(10):  # max iterations
        try:
            response = llm_call(env, messages)
        except Exception as e:
            return {
                "answer": f"LLM call failed: {e}",
                "source": source,
                "tool_calls": tool_calls_log,
            }
        msg = response["choices"][0]["message"]
        messages.append(msg)

        # If LLM returned tool calls
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])

                if fn_name == "read_file":
                    result = tool_read_file(fn_args["path"])
                    if not source:
                        source = fn_args["path"]
                elif fn_name == "list_files":
                    result = tool_list_files(fn_args["path"])
                elif fn_name == "query_api":
                    result = tool_query_api(env, fn_args["method"], fn_args["path"], fn_args.get("body"))
                    if not source:
                        source = fn_args["path"]
                else:
                    result = f"Unknown tool: {fn_name}"

                tool_calls_log.append({
                    "tool": fn_name,
                    "args": fn_args,
                    "result": result[:2000],
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
        else:
            # LLM gave a final answer
            answer = (msg.get("content") or "").strip()
            return {
                "answer": answer,
                "source": source,
                "tool_calls": tool_calls_log,
            }

    return {
        "answer": "Unable to complete the task within iteration limit.",
        "source": source,
        "tool_calls": tool_calls_log,
    }


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    env = load_env()
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)
    question = sys.argv[1]
    try:
        result = run_agent(env, question)
    except Exception as e:
        result = {"answer": f"Agent error: {e}", "source": "", "tool_calls": []}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
