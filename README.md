# 🐒 qa-swarm: Autonomous Multi-Agent Chaos Engineering & Mutation Testing Swarm

[![Tests](https://github.com/AbhinavSharma07/Swarm-Monkey/actions/workflows/tests.yml/badge.svg)](https://github.com/AbhinavSharma07/Swarm-Monkey/actions/workflows/tests.yml)

`qa-swarm` is a production-ready autonomous software quality assurance platform. It transforms traditional reactive software testing into an adversarial game. Utilizing a cyclic, multi-agent AI framework powered by **LangGraph**, the system proactively breaks, analyzes, and self-heals target microservices without human intervention. 

Instead of waiting for engineers to write boilerplate tests or maintain brittle UI selectors, `qa-swarm` continuously hardens base applications, outputting production-ready GitHub Pull Requests that bundle logical source fixes along with deterministic regression test suites.

---

## 💡 Project Description

In traditional environments, test coverage is limited by the developer’s ability to anticipate failures. `qa-swarm` breaks this bottleneck by establishing a closed-loop, continuous improvement environment run by three independent AI agent personas:

*   **The Aggressor (Chaos Agent):** Injects subtle, syntactically legal logical bugs into the application code using AST (Abstract Syntax Tree) transformation.
*   **The Detective (Test Engineer Agent):** Scans real-time telemetry and server crash logs to automatically engineer isolated integration tests that capture the unique failure condition.
*   **The Surgeon (Patch Agent):** Analyzes the failing code and test logs, rewrites the source logic inside an isolated sandbox, validates the fix, and automatically updates the central repository via a Git Pull Request.

---

## 📊 System Architecture

The ecosystem relies heavily on non-linear, cyclic state machines. If an agent fails to engineer a functional code patch, the orchestrator automatically intercepts the runtime error and loops the task back through the graph for another evaluation phase.

```
Aggressor ──> Detective ──(silent mutant, retries left)──> back to Aggressor
                  │
            (failure captured)
                  ▼
               Surgeon ──(internal retry loop, feeds back prior failure)
                  │
            (patch validated)              (retries exhausted)
                  ▼                              ▼
        branch + runs/<id>/patch.diff      cycle marked unresolved
```

---

## 🚦 Status

The current implementation is a working MVP of the core loop, run against a small
bundled sample microservice rather than an arbitrary external repo:

- **Aggressor** mutates real Python source via `libcst`, preserving the original file's
  formatting outside the single mutated node (relational-operator swap, boundary shift,
  boolean-operator swap, condition negation, arithmetic-operator swap, unary-operator
  removal) — not yet the full mutation catalog.
- **Detective** runs the target's pytest suite in an isolated `git worktree` and, on
  failure, asks an LLM to synthesize a confirming regression test.
- **Surgeon** asks an LLM to patch the bug, validates against the full suite + the new
  regression test, and retries with feedback up to `MAX_SURGEON_RETRIES` times.
- Successful cycles are committed to a local branch (`qa-swarm/fix-<run_id>`) plus a
  `runs/<run_id>/patch.diff` file. Pass `--open-pr` to additionally push the branch and
  open a real GitHub PR via `gh` — opt-in, off by default, and skips gracefully (with a
  log line, not a crash) if `gh` isn't installed/authenticated.
- Every cycle's outcome is appended to `runs/history.jsonl`; `python -m qa_swarm report`
  (or the summary printed at the end of `run`) shows total cycles, mutation score, and a
  per-operator healed/unresolved breakdown across all runs so far.
- `--parallel N` runs N cycles concurrently, each in its own isolated worktree (git
  worktree add/remove is internally lock-serialized to avoid races; the mutation/test/
  LLM work itself runs fully in parallel).
- The target no longer has to be named `sample_app` with `app`/`tests` subfolders —
  `--app-dir`/`--tests-dir`/`--exclude-files` let it point at any differently-shaped
  target. It must still live inside this same git checkout, though: the sandbox
  isolates cycles via a worktree of *this* repo, not an arbitrary external one.
- LLM calls (Detective's regression-test synthesis, Surgeon's patch generation) retry
  with exponential backoff on transient failures. Surgeon also rejects an oversized
  rewrite before ever running it against the test suite — if a proposed patch changes
  more than `MAX_PATCH_CHANGE_RATIO` (default 50%) of the file relative to the buggy
  version it was asked to fix, it's treated as a failed attempt and retried rather than
  blindly trusted.
- **Runtime telemetry:** if the target defines a `telemetry_requests.json` (a list of
  `{method, path, json, expect_status}` scenarios) next to `--app-dir`, Detective — after
  the target's own pytest suite passes — additionally fires that request battery at the
  real FastAPI app via `TestClient`, exercising actual routing/validation/exception-
  handling, not just whatever the target's own tests happen to check. A mutation that
  slips past the target's suite but breaks one of these request/response contracts still
  gets caught and healed (log lines say `caught via pytest` vs `caught via telemetry`).
  For `sample_app`, whose pricing logic is already thoroughly unit-tested, this mostly
  acts as defense-in-depth rather than the primary catcher — its real value shows up on
  targets with weaker test coverage of the HTTP layer specifically, which is exactly what
  `tests/test_telemetry.py` demonstrates directly (a deliberately narrow test suite that
  stays green while telemetry catches the same regression).

**Not yet implemented** (a bigger, separate effort rather than an incremental add-on):
multi-language support — the mutation engine is Python/libcst-specific.

## 🚀 Getting Started

```bash
pip install -e .
cp .env.example .env   # set LLM_PROVIDER + the matching API key
python -m qa_swarm run --target ./sample_app --cycles 3
```

Against a differently-shaped target (still inside this same checkout):

```bash
python -m qa_swarm run --target ./some_other_service --app-dir src --tests-dir spec --exclude-files __init__.py,bootstrap.py
```

Running cycles concurrently and opening real PRs for healed ones:

```bash
python -m qa_swarm run --target ./sample_app --cycles 5 --parallel 3 --open-pr --pr-base main
```

Checking cumulative mutation-score stats from every run so far:

```bash
python -m qa_swarm report
```

To enable runtime telemetry checks, drop a `telemetry_requests.json` at the target's
root (see `sample_app/telemetry_requests.json` for the format) — no flag needed, it's
auto-discovered. `--app-module` overrides which file inside `--app-dir` holds the
FastAPI `app` object (default: `main`).

Each cycle prints a log of what the Aggressor injected, whether the Detective caught it,
and whether the Surgeon produced a validated fix. Run the test suites with:

```bash
pytest sample_app/tests   # the victim app's own baseline suite
pytest tests               # qa_swarm's own unit tests
```

