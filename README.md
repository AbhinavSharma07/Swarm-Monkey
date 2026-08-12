# 🐒 qa-swarm: Autonomous Multi-Agent Chaos Engineering & Mutation Testing Swarm

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

- **Aggressor** mutates real Python source via `ast` (relational-operator swap, boundary
  shift, boolean-operator swap, condition negation) — not yet the full AST-transform catalog.
- **Detective** runs the target's pytest suite in an isolated `git worktree` and, on
  failure, asks an LLM to synthesize a confirming regression test.
- **Surgeon** asks an LLM to patch the bug, validates against the full suite + the new
  regression test, and retries with feedback up to `MAX_SURGEON_RETRIES` times.
- Successful cycles are committed to a local branch (`qa-swarm/fix-<run_id>`) plus a
  `runs/<run_id>/patch.diff` file — **no GitHub PR automation yet**, that's a planned
  next step once the core loop has seen more mileage.

## 🚀 Getting Started

```bash
pip install -e .
cp .env.example .env   # set LLM_PROVIDER + the matching API key
python -m qa_swarm run --target ./sample_app --cycles 3
```

Each cycle prints a log of what the Aggressor injected, whether the Detective caught it,
and whether the Surgeon produced a validated fix. Run the test suites with:

```bash
pytest sample_app/tests   # the victim app's own baseline suite
pytest tests               # qa_swarm's own unit tests
```

