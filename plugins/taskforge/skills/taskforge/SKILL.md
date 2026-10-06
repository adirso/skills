---
name: taskforge
description: Use when the user mentions Task-Forge or TaskForge, pastes a TaskForge URL (a link with ?project= and ?task= query parameters), refers to a task key like TF-4, or asks to read, create, update, or comment on tasks, projects, phases, or sprints in their project management system.
---

# Task-Forge

REST API for a project management system. Agents authenticate with a revocable
bearer token and act as a real identity in the system — tasks they create and
updates they post are attributed to that agent and visible to humans.

**Core principle: project membership is the authorization boundary.** An empty
result is far more often "this agent is not a member" than "nothing exists."

## Setup

```bash
export TASKFORGE_URL="http://127.0.0.1:5173"
export TASKFORGE_TOKEN="tf_..."          # never commit this
```

`:5173` is the web dev server, which proxies `/api/*` to the API on `:4000`.
Either port works. Every request needs `Authorization: Bearer $TASKFORGE_TOKEN`.

If the token is not in the environment, ask the user for it — do not guess a
port or invent a token.

## Which project? Ask, unless you can point at the mapping

**Never infer a project from a repository name, a directory name, or a
similar-sounding project title.** A wrong project is silent: the API accepts the
write, returns `201`, and the task lands in someone else's board where the user
will not look for it.

Resolve the project in this order:

1. **The user named it in this conversation, or pasted a link containing
   `?project=`** — use that.
2. **A recorded mapping exists for this repository** — a `TASKFORGE_PROJECT` in
   the repo's env, a line in its `CLAUDE.md`/`AGENTS.md`, or a mapping the
   operator has previously confirmed. Use it, and say which mapping you used.
3. **Otherwise — ask.** List what the agent can actually see and let the user
   pick:

```bash
curl -sS "$TASKFORGE_URL/api/projects" \
  -H "Authorization: Bearer $TASKFORGE_TOKEN"
```

Similar names are not evidence. A repo called `asolo` and a project called
"Asolo" may well correspond — but confirm it once, then record it, rather than
assuming it every time. When a mapping is confirmed, write it down so the next
session reaches step 2 instead of step 3.

## Resolve a link the user pasted — do this first

A user sharing `http://127.0.0.1:5173/?project=TF&task=TF-4` is handing you the
exact query parameters the API accepts. Pass them straight through instead of
hunting for UUIDs:

```bash
curl -sS "$TASKFORGE_URL/api/context?project=TF&task=TF-4" \
  -H "Authorization: Bearer $TASKFORGE_TOKEN"
```

Returns the project and the complete task — assignment, definition of done,
branch, and pull-request metadata. `project` accepts a key or UUID; `task`
accepts a readable key (`TF-4`) or UUID.

## Quick reference

| Goal | Call |
|---|---|
| Resolve a shared link | `GET /api/context?project=<key>&task=<key>` |
| List my projects | `GET /api/projects` |
| List tasks | `GET /api/projects/:projectId/tasks?status=TODO` |
| Read phases | `GET /api/projects/:projectId/phases` |
| Create a task | `POST /api/projects/:projectId/tasks` |
| Update a task | `PATCH /api/tasks/:taskId` |
| Set task dependencies | `POST /api/tasks/:taskId/dependencies` |
| Post a progress update | `POST /api/tasks/:taskId/updates` |
| Read the timeline | `GET /api/tasks/:taskId/updates` |

Task filters: `status`, `assigneeId`, `priority`, `phaseId`, `minPoints`,
`maxPoints`, `q`.

**Enums** — sending anything else is a `400`:

| Field | Values |
|---|---|
| `status` | The project's own set — read `project.availableStatuses` from `/api/context`, never assume. A base install has `BACKLOG` `TODO` `IN_PROGRESS` `IN_REVIEW` `DONE`; a project with a review workflow also enables `READY_FOR_REVIEW` `FIX_NEEDED` `FIX_IN_PROGRESS` `RE_REVIEW` `APPROVED` `PENDING_DECISION` |
| `priority` | `LOW` `MEDIUM` `HIGH` `URGENT` |
| `pullRequestState` | `DRAFT` `OPEN` `MERGED` `CLOSED` |

PR metadata is exactly two fields: `pullRequestUrl` and `pullRequestState`.
There is no `pullRequestNumber` — sending one returns `200` and drops it
silently, like any unrecognised field. The number is already in the URL.

## Creating and updating

Create a task. Omit `phaseId` and it lands in the project's active phase.
Pass a parent task's UUID as `parentId` to create a subtask — the API rejects
cross-project parents and cycles.

```bash
curl -sS "$TASKFORGE_URL/api/projects/$PROJECT_ID/tasks" \
  -H "Authorization: Bearer $TASKFORGE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "title":"Add retry logic",
    "description":"Retry transient upstream failures with bounded backoff.",
    "definitionOfDone":"Integration tests cover 429 and 503 responses.",
    "status":"IN_PROGRESS",
    "priority":"HIGH",
    "branch":"agent/retry-logic",
    "pullRequestUrl":"https://github.com/example/repo/pull/17",
    "pullRequestState":"OPEN",
    "estimatePoints":3
  }'
```

### Put the definition of done in `definitionOfDone`, not in the description

`definitionOfDone` is its own field. Writing "Definition of done: …" as a
closing paragraph of `description` looks identical on a rendered card and is
not the same thing: the field stays empty, the board shows no DoD, and a
reviewer reading the task sees none.

It has a concrete cost for agents. An assignment prompt built from a task with
an empty field says **"No definition of done provided. Confirm the expected
outcome before making broad changes"** — which is an instruction to stop and
ask. Ten tasks were created that way in one project and the prompt said it
every time; the DoD was sitting in the description prose and got read from
there instead, so the guard fired ten times and was silently worked around.

```bash
curl -sS "$TASKFORGE_URL/api/projects/$PROJECT_ID/tasks" \
  -H "Authorization: Bearer $TASKFORGE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "title":"Add retry logic",
    "description":"Why this matters and what is known so far.",
    "definitionOfDone":"Integration tests cover 429 and 503 responses."
  }'
```

Keep one home for it. `description` carries the why, the evidence and the
constraints; `definitionOfDone` carries the observable outcome. Duplicating the
sentence in both means one of them goes stale.

Settable on create and on `PATCH /api/tasks/:id`, so an existing task with an
empty field can be corrected without rewriting it. Read it back to confirm —
the field is silently ignored if misnamed, exactly like `dependencies` vs
`dependencyIds`.

### Fix work starts at FIX_IN_PROGRESS, not IN_PROGRESS

When a task comes back as `FIX_NEEDED` and the project enables
`FIX_IN_PROGRESS`, that is the status to move it to. Assignment prompts phrase
this as *"PATCH with status IN_PROGRESS (FIX_IN_PROGRESS workflow start)"*,
which reads like an instruction to send `IN_PROGRESS`; it is naming the
workflow step, and the parenthetical is the status to send. Sending
`IN_PROGRESS` puts the task back in the fresh-implementation lane and the board
loses the distinction between work not yet reviewed and work being corrected —
which is the whole point of a separate status.

The rule underneath: **let `project.availableStatuses` decide.** If the project
enables a status that names the phase you are actually in, use it rather than
the nearest generic one.

| Situation | Status to PATCH |
|---|---|
| Picking up new work | `IN_PROGRESS` |
| Picking up a `FIX_NEEDED` task | `FIX_IN_PROGRESS` (fall back to `IN_PROGRESS` only if not enabled) |
| Implementation finished, needs review | `READY_FOR_REVIEW` |
| Fixes finished, needs another look | `RE_REVIEW` |

**PATCH only what changed** — send the single field, not the whole task:

```bash
curl -sS -X PATCH "$TASKFORGE_URL/api/tasks/$TASK_ID" \
  -H "Authorization: Bearer $TASKFORGE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"status":"IN_REVIEW"}'
```

### Dependencies — set them when you create a series

Whenever you create more than one task and the order matters, wire the
dependencies. They are a real, enforced feature: an **agent** claiming a task
whose dependencies are not yet in the project's `dependencyResolutionStatuses`
(default `DONE`, `CANCELLED`) is rejected with `Task is blocked by incomplete
dependencies`. A `Depends on:` line in the description explains *why* and is
worth keeping, but on its own it blocks nothing.

The read field and the write field have different names — you read
`dependencies`, you write **`dependencyIds`** — so sending `dependencies` is
silently discarded and looks exactly like the feature not existing. Send task
**UUIDs**, not `ASO-1` keys:

```bash
curl -sS "$TASKFORGE_URL/api/tasks/$TASK_ID/dependencies" \
  -H "Authorization: Bearer $TASKFORGE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"dependencyIds":["<uuid-of-ASO-1>","<uuid-of-ASO-2>"]}'
```

This **replaces** the whole set, so send every dependency the task should keep,
not just the new one. `dependencyIds` is also accepted inline on task create and
on `PATCH /api/tasks/:id`.

Read back to confirm: the task returns `dependencies` with each entry's
`number`, `status`, and `isBlocking`, plus a `blockedReason`. A `200` is not
evidence — a wrong field name produces exactly that.

A progress update appears in the task's timeline where humans read it. Write it
for a teammate catching up, not for a log:

```bash
curl -sS "$TASKFORGE_URL/api/tasks/$TASK_ID/updates" \
  -H "Authorization: Bearer $TASKFORGE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"body":"Implementation complete, PR #17 open for review."}'
```

## Three things the API guide does not tell you

**PATCH silently ignores fields it does not recognise, and still returns `200`.**
`{"totallyMadeUpField":"xyz"}` succeeds. So a `200` from PATCH is *not* evidence
your change was applied — only that the request was well-formed. After any PATCH
whose field you have not used before, read the task back and confirm the value
actually changed.

**Readable task keys are composed, not stored.** A task has no `key` field. It
has `number`, a per-project sequence, and the readable key is
`<projectKey>-<number>` — project `ASO` plus `number: 1` is `ASO-1`, which
`/api/context?project=ASO&task=ASO-1` resolves. Build the key for display; never
expect to read one off a task.

**Dependencies exist, and the write field is `dependencyIds`.** Tasks read back
a `dependencies` array but are written through `dependencyIds`, so PATCHing
`dependencies` is accepted and discarded — which is indistinguishable from the
feature not existing. See *Dependencies* under Creating and updating.

## Reading errors

Errors always carry an `error` string. Validation failures add Zod `issues`
with the exact failing path — read it rather than guessing:

```json
{"error":"Validation failed",
 "issues":[{"path":["title"],"message":"String must contain at least 1 character(s)"}]}
```

An enum failure also lists every accepted value, so a `400` tells you the fix
outright — never guess a second time after seeing one:

```json
{"error":"Validation failed",
 "issues":[{"path":["status"],"code":"invalid_enum_value","received":"In Progress",
            "options":["BACKLOG","TODO","IN_PROGRESS","IN_REVIEW","DONE"]}]}
```

| Status | Means | Do |
|---|---|---|
| `400` | Invalid input or relationship | Read `issues[].path`; check an enum value |
| `401` | Bad, expired, or missing token | Stop. Ask the user for a token — do not retry |
| `403` | Not a member of that project | Stop. Ask a human admin to add the agent |
| `404` | No such resource | Check the key; confirm membership (see below) |
| `409` | Unique-key conflict | The thing already exists — read before writing |

`401` bodies differ and tell you which problem you have: `Authentication
required` means no header was sent; `Invalid or expired credentials` means the
token was rejected. A request to a route that does not exist returns a
Fastify-shaped `404` with `message` and `statusCode` instead of `error`.

## Common mistakes

**Guessing the project.** See the section above — a wrong project is accepted
silently and the work lands somewhere the user will never look. Ask.

**Reading `{"projects":[]}` as "there are no projects."** It almost always means
this agent identity is a member of none. Membership is the authorization
boundary, and a non-member gets an empty list rather than an error. A human
admin must run `POST /api/projects/:id/members` with the agent's user id. If a
user says "look at my project" and you get an empty list, say you are not a
member — do not report that they have no projects.

**Chasing UUIDs when the user gave you keys.** `/api/context` takes `TF` and
`TF-4` directly. Listing every project to find one by name wastes calls and can
fail outright when the agent cannot list projects.

**Sending a full task object to PATCH.** Send only changed fields.

**Trusting a PATCH `200`.** Unrecognised fields are accepted and discarded
without error. Read the task back when you are not certain a field is writable.

**Recording task ordering only as prose.** `Depends on: ASO-1` in a description
documents the reason but enforces nothing. If you created the tasks, set
`dependencyIds` as well — otherwise an agent can claim work whose prerequisites
do not exist yet.

**Retrying a `401`.** The token is wrong or revoked; retrying cannot fix it.
Tokens are shown once at issue and stored only as a hash — a lost token is
replaced, never recovered.

**Inventing enum values.** `"In Progress"`, `"in_progress"`, and `"Done"` are
all `400`. The values are uppercase with underscores, exactly as listed above.

## Token lifecycle

Tokens are revocable without changing the agent identity. Listing tokens returns
metadata only, never the secret. Issuing and revoking require a **human** JWT
from `POST /api/auth/login` — an agent token cannot mint or revoke tokens, so
route those requests to the user rather than attempting them.
