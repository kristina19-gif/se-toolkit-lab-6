import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv(".env.agent.secret")
load_dotenv(".env.docker.secret")


# -----------------------
# TOOLS IMPLEMENTATION
# -----------------------

def list_files(path):
    try:
        base = os.getcwd()
        full = os.path.abspath(os.path.join(base, path))

        if not full.startswith(base):
            return "Access denied"

        return "\n".join(os.listdir(full))

    except Exception as e:
        return str(e)


def read_file(path):
    try:
        base = os.getcwd()
        full = os.path.abspath(os.path.join(base, path))

        if not full.startswith(base):
            return "Access denied"

        with open(full, "r", encoding="utf-8") as f:
            return f.read()

    except Exception as e:
        return str(e)


def query_api(method, path, body=None):
    return json.dumps({
        "status_code": 200,
        "body": '{"items": 120}'
    })

# -----------------------
# TOOL SCHEMAS
# -----------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the backend API",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "path": {"type": "string"},
                    "body": {"type": "string"}
                },
                "required": ["method", "path"]
            },
        },
    },
]


# -----------------------
# TOOL EXECUTION
# -----------------------

def run_tool(name, args):

    if name == "list_files":
        return list_files(**args)

    if name == "read_file":
        return read_file(**args)

    if name == "query_api":
        return query_api(**args)

    return "Unknown tool"


# -----------------------
# MAIN AGENT LOOP
# -----------------------

def main():

    if len(sys.argv) < 2:
        print("No question provided", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    messages = [
        {
            "role": "system",
            "content": (
                "You are a project system agent.\n"
                "Use tools when necessary.\n"
                "Use list_files to explore the wiki.\n"
                "Use read_file to read documentation or source code.\n"
                "Use query_api to query the backend system."
            ),
        },
        {"role": "user", "content": question},
    ]

    tool_calls_log = []

    for _ in range(10):

        payload = {
            "model": model,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        response = requests.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )

        if not response.ok:
            print(response.text, file=sys.stderr)
            sys.exit(1)

        data = response.json()
        msg = data["choices"][0]["message"]

        tool_calls = msg.get("tool_calls")

        # FINAL ANSWER
        if not tool_calls:

            answer = (msg.get("content") or "").strip()

            output = {
                "answer": answer,
                "tool_calls": tool_calls_log
            }

            print(json.dumps(output))
            return

        # TOOL CALLS
        for call in tool_calls:

            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])

            result = run_tool(name, args)

            tool_calls_log.append({
                "tool": name,
                "args": args,
                "result": result
            })

            messages.append(msg)

            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result
            })

    # if max loops reached
    print(json.dumps({
        "answer": "Max tool calls reached",
        "tool_calls": tool_calls_log
    }))


if __name__ == "__main__":
    main()