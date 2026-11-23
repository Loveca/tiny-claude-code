# ch20 design notes: OpenAI-compatible provider adapter

Status: accepted for ch20 implementation.

## Context

ch01 anchored the harness to the Anthropic Messages API: `LLMClient.chat()`
returns a `Message` whose `content` is a list of text/tool_use blocks and whose
`stop_reason` says whether the loop continues. `agent_loop` only reads those
attributes, and `ErrorHandler` only inspects `status_code` and headers on
exceptions — nothing in the harness depends on the SDK itself.

That is the opening: providers that speak OpenAI-style chat completions
expose the same concepts under different field names. ch20 adds a second
client that converts messages, tools, and responses at the boundary, so the
same agent runs against both API shapes.

## Decisions

### Convert at the wire level, not the SDK level

The adapter speaks HTTP chat completions directly through `urllib.request`
instead of pulling in the `openai` package. The project already depends on the
Anthropic SDK; adding a second SDK to teach a message-format conversion would
hide the thing the chapter is about. It also keeps `requirements.txt` unchanged
and makes the transport trivial to stub in tests.

### Provider selection is one environment variable

`create_client()` returns an Anthropic client by default; `LLM_PROVIDER=openai`
switches to `OpenAICompatibleClient`, which reads `OPENAI_API_KEY`,
`OPENAI_BASE_URL` (default `https://api.openai.com/v1`), and reuses `MODEL_ID`.
Env vars are already the project's config channel (`ANTHROPIC_API_KEY`,
`MODEL_ID`, `ANTHROPIC_BASE_URL`), so no CLI flag or constructor plumbing is
added. Any OpenAI-compatible server — OpenAI, DeepSeek, Ollama, vLLM — is one
env block away.

### One conversion table, not two code paths

Everything the harness stores is Anthropic-shaped; the adapter converts on the
way out and back in:

| Anthropic shape | chat completions shape |
|---|---|
| `system` parameter | leading `{"role": "system"}` message |
| user text block (or plain string) | `{"role": "user", "content": text}` |
| assistant text block | `{"role": "assistant", "content": text}` |
| assistant `tool_use` block | `tool_calls[]`, `arguments` as a JSON string |
| user `tool_result` block | `{"role": "tool", "tool_call_id": ...}` message |
| `{name, description, input_schema}` | `{type: "function", function: {..., parameters}}` |
| `stop_reason` `tool_use` / `end_turn` / `max_tokens` | `finish_reason` `tool_calls` / `stop` / `length` |

Because the harness keeps working in Anthropic shapes, agent loop, hooks,
context manager, compaction, sessions, and memory are untouched — and
conversations stay resumable if the user switches providers.

### Tool results precede trailing user text

One Anthropic user message may carry several `tool_result` blocks plus text.
OpenAI requires `tool` messages to directly follow the assistant message that
made the calls, so the adapter emits all `tool` messages first and appends the
joined user text (if any) after them. Ordering this way keeps every provider's
strict role-sequencing validation happy.

### Failures reuse the ErrorHandler contract

The HTTP transport raises `OpenAIError` with `.status_code` and `.headers`
populated. `ErrorHandler` already retries 429 with backoff and 529 with
`Retry-After`, keyed on exactly those attributes, so provider errors get the
same treatment as Anthropic errors without touching ch07 code. Connection
errors carry no status code and are not retried.

### Malformed tool arguments degrade, not crash

Some servers return invalid JSON in `arguments`. The adapter maps that to a
`tool_use` block with `input=None`; `agent_loop` already answers non-dict input
with `"Error: malformed tool_use block"`, which lands in the transcript as a
normal tool result. One bad call does not kill the run.

## Response shape returned to the harness

```python
ChatResponse(
    content=[TextBlock(text="..."), ToolUseBlock(id=..., name=..., input={...})],
    stop_reason="tool_use" | "end_turn" | "max_tokens",
)
```

Plain dataclasses with the same attribute names the loop reads, so tests can
use them without the SDK.

## Testing contract

- conversion: system message placement, plain-string and block user messages,
  assistant text + `tool_calls` round-trip, `tool` message ordering before
  trailing text, tool schema conversion;
- response: text-only, tool calls with parsed arguments, invalid JSON
  arguments, `finish_reason` mapping (`length` → `max_tokens`);
- client: injected transport sees the right endpoint, bearer header, model,
  and payload; its canned reply comes back as `ChatResponse`;
- end-to-end: a two-turn `agent_loop` run (tool call, then final text) against
  the fake transport, asserting the second request carries the assistant
  `tool_calls` and the `tool` message;
- error path: `ErrorHandler` retries a 429 `OpenAIError` (zero backoff) and
  returns the eventual success;
- selection: `create_client()` honours `LLM_PROVIDER` and defaults to
  Anthropic.

## Non-goals

- streaming (token-by-token rendering is its own chapter-sized change);
- image/audio content blocks and the OpenAI Responses API;
- provider-specific extras (reasoning fields, prompt caching, `logprobs`);
- parallel tool execution beyond what the existing loop already does;
- unifying token accounting across providers (ch08 estimates by characters).