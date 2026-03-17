# Agent

## Overview

This project implements a CLI agent that connects to an LLM and answers questions about the software engineering lab system. The agent receives a question from the command line, runs an agentic loop with function calling, and prints a JSON response.

## Architecture

```
User question → agent.py → LLM API (function calling) → tools → LLM → JSON output
```

## Configuration

The agent reads all configuration from environment variables (loaded from `.env.agent.secret` and `.env.docker.secret`):

| Variable | Purpose |
|----------|---------|
| `LLM_API_KEY` | LLM provider API key |
| `LLM_API_BASE` | LLM API endpoint URL (OpenAI-compatible) |
| `LLM_MODEL` | Model name |
| `LMS_API_KEY` | Backend API key for `query_api` authentication |
| `AGENT_API_BASE_URL` | Backend base URL (default: `http://localhost:42002`) |

## Running the agent

```bash
uv run agent.py "How many items are in the database?"
```

Output format:

```json
{"answer": "...", "source": "...", "tool_calls": [...]}
```

## Tools

### list_files

Lists files in a directory within the project root. Used to discover available wiki articles or source files.

Parameters: `path` (string) — relative directory path.

### read_file

Reads contents of a file within the project root. Used for wiki documentation, source code, and configuration files. Content is limited to 8000 characters to stay within LLM context limits.

Parameters: `path` (string) — relative file path.

### query_api

Sends an HTTP request to the deployed backend API. Authenticated with `LMS_API_KEY` via Bearer token. Used for any question requiring live runtime data: item counts, scores, analytics, endpoint behavior.

Parameters: `method` (string), `path` (string), `body` (string, optional).

Returns a JSON string with `status_code` and `body`.

## How the LLM decides between tools

The system prompt gives clear guidance:

- **Documentation/wiki questions** → `list_files("wiki")` then `read_file` the relevant article
- **Source code questions** (framework, architecture, implementation details) → `read_file` the relevant source file
- **Runtime/data questions** (item counts, scores, analytics, completion rates) → `query_api`
- **Multi-step questions** (e.g., diagnose a bug by reading an API error then the source) → chain multiple tools

## Agentic loop

1. Send question + tools schema to LLM.
2. If LLM returns `tool_calls`: execute each tool and send results back as `tool` role messages.
3. Repeat up to 10 iterations until LLM produces a text answer (no tool calls).
4. Return `{"answer": ..., "source": ..., "tool_calls": [...]}`.

## System Agent (Task 3)

In Task 3 the agent was extended with a new `query_api` tool that allows it to talk to the running backend. This enables answering data-dependent questions (item counts, analytics scores) that cannot be answered from static files alone.

### Authentication

Backend requests are authenticated with `LMS_API_KEY` from environment variables via `Authorization: Bearer <key>` header. The base URL is read from `AGENT_API_BASE_URL` (default `http://localhost:42002`). Neither value is hardcoded.

### Lessons learned from the benchmark

1. **Rule-based heuristics fail**: The initial implementation used keyword matching instead of an LLM. It failed on question variations the heuristic did not anticipate. Replacing it with a proper LLM agentic loop fixed the majority of failures.

2. **Tool descriptions matter**: The LLM chooses tools based on their descriptions. Vague descriptions cause wrong tool selection. Explicit guidance ("use query_api for runtime data, NOT for documentation") significantly improved tool choice accuracy.

3. **Content limits**: Large files cause the LLM to loop or get confused. Truncating `read_file` output to 8000 characters prevents this while keeping enough context.

4. **`content` can be null**: When the LLM returns tool calls, `content` is `null` (not missing). Using `msg.get("content") or ""` avoids `NoneType` errors.

5. **Source tracking**: The `source` field should be set to the first meaningful file or API path used, giving the checker a reference for verification.

### Final eval score

All 10 local questions passed after switching from heuristics to a real LLM agentic loop with function calling.
