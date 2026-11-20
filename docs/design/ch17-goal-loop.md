# ch17 design notes: goal loop

Status: accepted for ch17 implementation.

## Context

`agent_loop` ends as soon as the model answers without a tool call. That is the
right contract for a chat turn, but not for a long-running objective: "make the
test suite pass" often needs several model calls, and a text-only reply in the
middle ("I found the failing assertion") is progress, not completion.

ch17 adds a goal loop on top of `agent_loop`'s tool dispatch:

- an objective with a turn budget;
- an explicit completion signal (`GoalDone`) instead of inferring completion
  from prose;
- a progress log (`GoalCheckpoint`) that is re-injected every turn so it
  survives context compaction;
- an idle guard for models that keep talking without acting.

## Decisions

### One model call per turn

`GoalManager.run(messages, registry, objective)` runs a loop where each turn is
exactly one `client.chat` call:

1. call the model (through `ErrorHandler` when configured);
2. append the assistant message;
3. dispatch requested tools through the registry;
4. append tool results plus a continuation prompt;
5. stop when the goal is done, the budget is spent, or the model goes idle.

This is deliberately deterministic: tests scripted with a mock client get a
fixed sequence of turns. It is also the same shape as `agent_loop`, so learners
can diff the two loops and see which extra state a goal needs.

### Completion must be explicit

A text-only turn does not finish a goal. The model has to call `GoalDone` with a
summary. Two reasons:

- progress updates are text too, so "text means done" would end the run at the
  first status report;
- completion is a claim that can be logged, reviewed, and tested, instead of an
  emergent property of phrasing.

`GoalDone` is a normal tool: it runs through `PreToolUse`, the registry, and
`PostToolUse` like everything else, so permissions and logging still apply.

### Checkpoints survive compaction

Long runs hit the context budget. ch08/ch09 reclaim space, but they do not know
which facts matter. `GoalCheckpoint(note)` is a short, model-written progress
log. The continuation prompt includes the last three notes, so the plan stays
visible even after old messages are compacted away.

### Idle guard

A model that answers with prose turn after turn makes no progress but burns the
budget. After `max_idle_turns` consecutive turns without tool calls, the goal is
paused with a readable reason instead of silently looping.

### Budget exhaustion is a result, not an error

Hitting `max_turns` sets status `paused`, not `failed`. The run is incomplete,
the transcript is intact, and the caller can report partial progress. `failed`
is reserved for the model call raising an exception.

### The registry is passed per run

`GoalManager` does not own tools. `create_default_registry(goal_manager=...)`
registers `GoalDone` and `GoalCheckpoint`; `run()` receives the registry and
dispatches through it. This avoids a constructor cycle (registry needs the
manager to build the tools, the manager needs the registry to run) and lets the
CLI reuse one registry for chat turns and goal turns.

## Tool surface

| Tool | Arguments | Purpose |
|---|---|---|
| `GoalDone` | `summary` | mark the active goal complete |
| `GoalCheckpoint` | `note` | append to the progress log |

Both tools are registered only when `goal_manager` is passed to
`create_default_registry`, so default tool sets stay unchanged.

## Run result

`run()` returns a dict:

| key | meaning |
|---|---|
| `status` | `done`, `paused`, or `failed` |
| `turns` | model calls used |
| `summary` | text passed to `GoalDone` |
| `reason` | why a paused/failed run stopped |
| `checkpoints` | progress notes recorded during the run |

## Testing contract

- completion: `GoalDone` ends the run and records the summary;
- continuation: after tool results the next user message carries the remaining
  turn count and recent checkpoints;
- budget: `max_turns` caps model calls; status is `paused`;
- idle: consecutive text-only turns pause the goal;
- errors: an exception from the client sets status `failed` with the message;
- wiring: goal tools exist only when a manager is provided;
- safety: `PreToolUse` denials reach the tool result and `Stop` fires once at
  the end.

## Non-goals

- durable goal state across process restarts (ch10 sessions already keep the
  transcript; a goal journal is a later exercise);
- a separate judge model that decides completion;
- concurrent goals or nested goal runs;
- resuming a paused goal in place.
