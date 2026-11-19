# ch16 design notes: multi-agent teams and worktree isolation

Status: accepted for ch16 implementation.

## Context

ch12 introduced `SubAgent`: a one-shot delegation that runs a task in an isolated
message history and returns a summary. It covers "give this job to someone else",
but not "keep working with someone": there is no way to send a follow-up, no shared
queue of work, and no isolation for agents that edit the same repository at the same
time.

ch16 adds a small team layer on top of the existing harness:

- named members with their own message history, status, and tool registry;
- a mailbox between the lead and each member;
- git worktree isolation so two members can edit the same files in parallel;
- deterministic scheduling so every behavior is testable with a mock LLM.

## Decisions

### Deterministic scheduler instead of threads

`TeamManager.step(name)` runs exactly one model turn for one member. A turn is:
drain unread mail, call the model once, and if it requested tools, dispatch them
and append the results. `run_round()` steps every unfinished member once;
`wait()` repeats rounds until everyone is done or a hard round cap is reached.

Real Claude Code-style teams run asynchronously. We keep the same message-passing
semantics but schedule turns explicitly. This makes tests reproducible (a scripted
mock client returns responses in a fixed order) and makes the lesson about the
protocol, not about thread safety. The upgrade path, if needed later, is to move
`step()` calls behind a queue or thread pool; the mailbox API does not change.

### Mailbox instead of return values

A member's result is delivered as a `result` message to the lead's inbox, and the
lead can reply with a new `message`, which the member sees on its next turn. This
is what makes a team different from a function call: the conversation can continue
after the first answer.

Messages are in-memory for ch16. Persisting mailboxes is out of scope; the session
layer (ch10) is the obvious place to add it later.

### Members cannot spawn

Members get `bash`, `read`, `write`, `search`, `TeamSend`, and `TeamInbox` only.
Neither `SubAgent` nor `TeamSpawn` is registered for a member, mirroring the depth
guard in `SubAgent.spawn`. This keeps the topology flat and prevents runaway
recursion.

### Worktrees for isolation

`TeamManager.spawn(..., isolate=True)` creates a git worktree under
`.tiny-claude-code/worktrees/<name>` on branch `tiny/team/<name>` and binds the
member's file and shell tools to that path. The lead keeps working in the main
workspace and merges with `WorktreeMerge`, which delegates to `git merge` and
aborts on conflicts instead of resolving them.

Isolation requires a git repository; when the workspace is not one, spawn fails
with a readable error instead of silently sharing files.

Worktrees are runtime state, so the root lives under the already-ignored
`.tiny-claude-code/` directory. `TeamManager.shutdown()` removes created
worktrees and their branches.

## Tool surface

| Tool | Arguments | Visible to |
|---|---|---|
| `TeamSpawn` | `name, role, task, isolate?` | lead |
| `TeamSend` | `to, message` | lead and members |
| `TeamInbox` | none | lead and members |
| `TeamStatus` | none | lead |
| `TeamWait` | `max_rounds?` | lead |
| `TeamShutdown` | `name?` | lead |
| `WorktreeMerge` | `name, message?` | lead |

All of them are optional extensions to `create_default_registry`: when no
`team_manager` is passed, the default tool set is unchanged.

## Testing contract

- mailbox: send, drain, broadcast, validation of unknown recipients;
- lifecycle: member becomes `done` on a final text turn and its text is queued to
  the lead as a `result`;
- scheduler: one step makes exactly one model call; `wait` respects the round cap;
- isolation: members write to different worktrees; the main workspace is untouched;
- tools: members never see `TeamSpawn` or `SubAgent`;
- worktree manager: create/remove/merge against a real temporary git repository.

Mock LLM responses are consumed in step order, so tests drive `step()` explicitly
instead of relying on timing.

## Non-goals

- true parallelism (threads, process pools);
- persistent mailboxes or team state across sessions;
- nested teams or member-to-member broadcasts beyond `to="all"`;
- automatic merge-conflict resolution.
