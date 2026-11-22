# ch19 design notes: workflow runtime

Status: accepted for ch19 implementation.

## Context

ch16 and ch17 gave the harness more execution shapes — teams and budgeted
autonomous runs — but the *control flow* still belongs to the model: each run
decides what to do next from prose. That is the right default for open-ended
tasks, and the wrong tool for repeatable procedures. A "collect changes → draft
notes → human sign-off → publish" pipeline should run the same way every time,
pause at the same point, and leave a record you can inspect afterwards.

ch19 adds a workflow runtime on top of the existing pieces:

- a declarative step graph loaded from JSON definitions;
- three step kinds: `tool` (deterministic registry call), `agent` (one bounded
  `agent_loop` run), `approval` (pause until a human decides);
- per-step retries;
- a persisted run record per execution that survives restarts.

## Decisions

### The engine owns control flow, the model only fills steps

In a goal run (ch17) the model chooses the next action every turn. In a
workflow the graph is fixed: the engine schedules steps, the model only runs
inside `agent` steps. This is the workflow-vs-agent distinction in one line:
agents decide as they go, workflows repeat a declared procedure. Keeping the
scheduler deterministic is also what makes the chapter testable with a mock
client and no sleeps.

### Steps form a validated DAG

A definition is `{name, description, steps}`; each step has `id`, `type`,
optional `depends_on`, optional `max_retries`, plus kind-specific fields.
`run()` validates before executing: unique ids, existing dependencies, no
cycles, kind-specific required fields. Scheduling picks, in declaration order,
any step whose dependencies are all `done`; steps whose dependencies were
skipped are skipped too. The outer loop repeats until no progress is made, so
declaration order does not have to be a topological order.

### Failure is a string convention

`ToolRegistry.dispatch` already wraps tool exceptions as `"Error: ..."`. A
`tool` step treats any result starting with `Error:` as a failure and retries
up to `max_retries` extra times; a final failure marks the run `failed` and
stops scheduling. Agent steps join the same convention because `agent_loop`
returns `"Error: maximum number of turns reached."` when out of budget. No new
exception channel, no separate result type.

### Approval pauses the run, not the process

When the engine reaches an `approval` step it records the step as `waiting`,
persists the run as `waiting_approval`, and returns to the caller. Approving
resumes scheduling in the same process; denying marks the step and every still
pending step `skipped` and the run `denied`. The engine never blocks on input,
so the same code path serves the REPL, an agent tool, and a future queue.

### Run records are JSON files

Every state change writes
`.tiny-claude-code/workflows/runs/<run_id>.json` (name, status, per-step
status/attempts/output/error). `approve()` and `resume()` reload records from
disk, so approval can happen in a different process than the run — that is the
point of a human gate. Run ids are `"<name>-<hex>"`; names, step ids, and run
ids are restricted to `[A-Za-z0-9][A-Za-z0-9._-]*` so a definition file can
never escape the runs directory.

### Data flows through output substitution

String values in tool inputs and agent prompts may contain
`{outputs.<step_id>}`, replaced at execution time with the output of any
already-done step. Plain string replacement — no expression language, no
format-string pitfalls from user-authored JSON.

### The registry is passed per run

Same resolution as ch17: `create_default_registry(workflow_manager=...)`
registers the workflow tools, and the run receives the registry through the
tool that starts it. No constructor cycle, one registry shared by chat turns,
goal runs, and workflow steps.

### Triggers are entry points, not new machinery

A trigger is just a way to call `run()`: the `WorkflowRun` tool for the model,
`/workflow` in the REPL, and direct API use. The existing `CronScheduler`
already persists prompts; scheduling one that starts a workflow is a one-line
composition and stays an exercise rather than new surface.

## Step schema

```json
{
  "name": "release-notes",
  "description": "Draft release notes and require sign-off before publishing",
  "steps": [
    {"id": "collect", "type": "tool", "tool": "search", "input": {"pattern": "ch19"}},
    {"id": "draft", "type": "agent", "prompt": "Draft release notes from:\n{outputs.collect}", "depends_on": ["collect"]},
    {"id": "signoff", "type": "approval", "message": "Publish these notes?", "depends_on": ["draft"]},
    {"id": "publish", "type": "tool", "tool": "write", "input": {"path": "NOTES.md", "content": "{outputs.draft}"}, "depends_on": ["signoff"], "max_retries": 1}
  ]
}
```

## Statuses

| level | values |
|---|---|
| run | `running` → `waiting_approval` → `done` / `failed` / `denied` |
| step | `pending` → `running` → `done` / `failed` / `skipped` / `waiting` |

A failed run leaves its remaining steps `pending` in the record: the record
shows where the run stopped, not a rewritten history.

## Tool surface

| Tool | Arguments | Purpose |
|---|---|---|
| `WorkflowRun` | `name` | run a declared workflow |
| `WorkflowStatus` | `run_id?` | inspect a run (latest when omitted) |
| `WorkflowApprove` | `run_id?`, `decision`, `comment?` | approve or deny a waiting run |

All three are registered only when `workflow_manager` is passed to
`create_default_registry`, so default tool sets stay unchanged.

## Testing contract

- scheduling: linear runs, out-of-order DAGs, skip cascade from a skipped
  dependency;
- validation: unknown name, duplicate/invalid ids, unknown dependency, cycles,
  missing kind-specific fields;
- retries: a tool that fails once then succeeds records `attempts=2`; a tool
  that always fails marks the run `failed` with the last error;
- approval: `run()` returns `waiting_approval`; approve resumes to `done`;
  deny skips the rest and the run is `denied`;
- persistence: records exist on disk after each change; a new manager instance
  approves or resumes a run from disk;
- substitution: `{outputs.<id>}` reaches tool inputs and agent prompts;
- wiring: workflow tools exist only when a manager is provided;
- agent steps: bounded `agent_loop` with the mock client; final text becomes
  the step output.

## Non-goals

- scheduled triggers in code (cron composition stays an exercise);
- parallel step execution (declaration-order scheduling; concurrency is a
  thread-scheduling exercise once mailboxes exist in ch16);
- conditional branching (`when` clauses) and loops;
- retry backoff (in-process immediate retries keep tests deterministic);
- nested workflows;
- multi-approver quorums.
