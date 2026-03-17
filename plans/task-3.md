# Task 3 Plan – The System Agent

## Goal

Extend the agent from Task 2 by adding a `query_api` tool that allows it to talk to the deployed backend, and replace the heuristic-based agent with a proper LLM agentic loop using function calling.

## Tool Schema

A new tool `query_api` added to the existing tool set.

Parameters:
- `method` — HTTP method (GET, POST, etc.)
- `path` — API endpoint path (e.g. `/items/`)
- `body` — optional JSON body string

Returns a JSON string with `status_code` and `body`.

## Authentication

The tool authenticates using the environment variable `LMS_API_KEY` via `Authorization: Bearer <key>` header.

The base URL is read from `AGENT_API_BASE_URL` (default: `http://localhost:42002`).

## LLM Agentic Loop

The agent uses a proper LLM agentic loop with function calling:
1. Send question + tool schemas to LLM
2. If LLM returns tool calls — execute them, send results back
3. Repeat until LLM produces a final text answer
4. Return `{"answer": ..., "source": ..., "tool_calls": [...]}`

## System Prompt Strategy

The system prompt guides the LLM on tool selection:
- wiki questions → `list_files("wiki")` + `read_file`
- source code questions → `read_file`
- runtime/data questions → `query_api`

## Benchmark Results

Initial implementation used keyword-based heuristics without any LLM calls. This failed on many eval questions because:
- Heuristics did not cover question variations
- Multi-step and reasoning questions require actual LLM capability
- Tool selection must be context-aware, not keyword-based

After replacing heuristics with a real LLM agentic loop:
- All 10 local benchmark questions pass
- The LLM correctly selects `query_api` for data questions and `read_file` for code/wiki questions

## Iteration Strategy

1. Implement the LLM agentic loop with all three tools
2. Run `uv run run_eval.py` and check failures
3. If tool selection is wrong: improve tool descriptions in the schema
4. If answers are wrong: improve the system prompt
5. If agent loops: check content limits and max iteration cap
