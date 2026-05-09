# nomon — Design Spec

- **Date**: 2026-05-04
- **Owner**: jkf87 (블 크)
- **Status**: Approved (brainstorming complete, awaiting user spec review)
- **Next step**: writing-plans skill → implementation plan → autopilot execution

## 1. Goal

Make Nomon conveniently usable from inside OpenClaw, distributed as its own GitHub repo, and verified end-to-end on the user's machine. The integration must:

1. Expose Nomon via **two entry points** in OpenClaw: a slash skill and an MCP server.
2. Install with **one command** (no `curl | bash`).
3. Be packaged in a **separate repo** (`jkf87/nomon`) decoupled from the heavy nomon-ai Python distribution.
4. Pass a **5-dimension reviewer gate at ≥95%** before being declared done.
5. Ship with **agent-handoff prompts** so the work can be re-executed or extended by other agent teams.

## 2. Non-Goals

- Replacing the existing `feat/openclaw-runtime` adapter inside the `nomon` repo. That work stays where it is and lands via its own PR; this repo is the OpenClaw-side companion.
- ClawHub registry submission in v1. Structure must allow it later, but it is not in scope now.
- Bundling Nomon' Python source. Nomon is invoked via `uvx --from nomon-ai[mcp]`; this repo only carries the OpenClaw entry points.

## 3. Architecture

Three layers, top to bottom:

```
┌─ nomon (this new repo) ──────────────┐
│  skills/nomon/SKILL.md       ← slash skill    │
│  src/openclaw_nomon/         ← uvx installer  │
│  prompts/                     ← agent-facing   │
│  verification/                ← 95% gate       │
└──────────────────────┬─────────────────────────┘
                       │ depends on (uvx)
┌──────────────────────▼────────────────────────────┐
│ nomon-ai (PyPI / git, jkf87/nomon)              │
│   feat/openclaw-runtime branch contains the       │
│   OpenClaw runtime backend adapter (already done) │
└──────────────────────┬────────────────────────────┘
                       │ runtime backend (CLI subprocess)
┌──────────────────────▼────────────────────────────┐
│ openclaw CLI (already installed on user's machine)│
└───────────────────────────────────────────────────┘
```

Boundaries:
- **nomon** owns: OpenClaw skill files, MCP entry merge logic, install/uninstall/doctor commands, agent prompts, verification harness.
- **nomon-ai** owns: workflow engine, MCP server, runtime adapters (including `OpenClawCliRuntime`).
- **openclaw** owns: CLI, agent runtime, model routing, sandbox.

Each layer is independently testable and replaceable.

## 4. Entry Points

### 4.1 Slash skill — `~/.openclaw/skills/nomon/SKILL.md`

Korean + English natural-language triggers. Slash commands mirror the existing `ooo` skill set already shipped inside `~/nomon/skills/`:

| Skill | Purpose |
|-------|---------|
| `/nomon:setup` | Run `nomon setup --runtime openclaw` and verify |
| `/nomon:interview` | Start a spec-first interview |
| `/nomon:run` | Execute a workflow (`nomon run workflow ...`) |
| `/nomon:status` | Inspect execution status |
| `/nomon:cancel` | Cancel a running execution |

The SKILL.md body wraps `uvx --from nomon-ai[mcp] nomon <subcommand>` calls and parses the JSON envelope so the agent can stream user-facing text.

### 4.2 MCP server — `~/.openclaw/mcp/claude-mcp-config.json`

Add a `nomon` entry alongside the existing `openclaw` entry:

```json
{
  "mcpServers": {
    "openclaw": { "type": "stdio", "command": "openclaw", "args": ["mcp", "serve"] },
    "nomon": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "nomon-ai[mcp]", "nomon", "mcp", "serve"]
    }
  }
}
```

Merge must be **idempotent**: re-installing must not duplicate the entry; uninstalling must remove only the `nomon` key without disturbing siblings.

## 5. Installer UX

One command, end to end:

```bash
uvx --from git+https://github.com/jkf87/nomon nomon install
```

Subcommands the installer must expose:

| Command | Behavior |
|---------|----------|
| `install` | Stage SKILL.md, merge MCP entry, write `~/.nomon/config.yaml` (runtime_backend=openclaw), warm uvx cache, print diagnostics |
| `uninstall` | Reverse all of the above; never delete user-authored skills/MCP entries |
| `doctor` | Verify each artifact is present and Nomon responds via uvx |

**Idempotency**: install/uninstall must be safe to run repeatedly. State is detected by checking file presence + a managed-block marker inside the JSON / YAML files (e.g. JSON object key, YAML comment fences). No silent overwrites of user content.

**Failure mode**: any sub-step failure prints the diagnostic and exits non-zero without leaving the system half-installed. Partial state is rolled back.

## 6. Repo Layout

```
nomon/
├── README.md                     # B (end-user install) → A (build) → C (usage)
├── LICENSE                       # default MIT (autopilot may override)
├── pyproject.toml                # uvx entry point: nomon
├── src/openclaw_nomon/
│   ├── __init__.py
│   ├── cli.py                    # install / uninstall / doctor
│   ├── installer.py              # idempotent merge logic
│   ├── paths.py                  # OpenClaw / Nomon path resolution
│   └── skill_template/
│       └── SKILL.md              # copied verbatim into ~/.openclaw/skills/nomon/
├── prompts/
│   ├── build-handoff.md          # A: master brief for executor agent team
│   ├── install.md                # B: end-user natural-language install prompt
│   └── usage.md                  # C: ooo workflow usage templates
├── verification/
│   ├── auto/
│   │   └── run_install_test.sh   # clean-env install/uninstall/doctor exit-code test
│   ├── reviewers/
│   │   ├── 01-install-correctness.md
│   │   ├── 02-security.md
│   │   ├── 03-ux.md
│   │   ├── 04-test-coverage.md
│   │   └── 05-nomon-compat.md
│   └── logs/
│       └── round-N/              # scores.json + reviewer-*.md + install-test.log
├── tests/
│   ├── test_installer.py         # unit: idempotent merge, rollback
│   └── test_cli.py               # CLI smoke tests
└── docs/
    └── design.md                 # this spec, copied in
```

README ordering rationale: end-users hit install (B) first; contributors find the build prompt (A) below; existing users find usage templates (C) at the bottom. Difficulty increases top to bottom.

## 7. Agent-Handoff Prompts

| Prompt | Audience | Purpose |
|--------|----------|---------|
| `prompts/build-handoff.md` | Implementer agent or team | Self-contained brief: read this spec, scaffold the repo, run the verification gate, iterate until ≥95%, open PR. |
| `prompts/install.md` | OpenClaw end-user (paste into Claude Code session) | "Install Nomon for me, run doctor, report back" — wraps the uvx command with diagnostic and rollback context. |
| `prompts/usage.md` | OpenClaw user mid-workflow | Templates for `ooo interview` → `ooo run` flow, with example seeds. |

`build-handoff.md` must reference this spec by relative path and explicitly call out the 95% gate.

## 8. Verification Gate (5 Dimensions, ≥95%)

Each dimension scored 0–100 by a dedicated reviewer agent. All five must reach ≥95 before the work is declared done. One miss → fix → re-run all five.

| # | Dimension | Scoring inputs |
|---|-----------|----------------|
| 1 | Install correctness | Auto-test (70%) + qualitative (30%). Auto-test = clean ephemeral dir, run `install`, assert SKILL.md present, MCP entry merged, `doctor` exits 0; then `uninstall`, assert clean state. |
| 2 | Security | No `curl \| bash`; path-traversal safe; idempotent; uninstall verified; no execution of untrusted user content; secrets never logged. |
| 3 | UX | README clarity (Korean + English), error messages actionable, doctor output diagnostic. |
| 4 | Test coverage | Unit (installer logic, JSON/YAML merge, rollback) + integration (CLI subcommands) + E2E (auto-test from #1). |
| 5 | Nomon compat | SKILL.md commands match `feat/openclaw-runtime` adapter contract; MCP entry uses `nomon-ai[mcp]` extra; config.yaml schema matches `~/nomon/docs/runtime-guides/openclaw.md`. |

Per-round artifact at `verification/logs/round-N/`:
- `scores.json` — `{dim: {score, reviewer, summary, blockers}}`
- `reviewer-<dim>.md` — full reviewer output
- `install-test.log` — auto-test stdout/stderr + exit codes
- `diff.patch` — changes made this round in response to feedback

Loop terminates when all five `score ≥ 95` AND no `blockers` remain.

## 9. Deliverables

1. New public GitHub repo `jkf87/nomon` with the layout in §6.
2. Installer working on the user's machine — slash skill visible in OpenClaw, MCP entry registered, `doctor` clean.
3. Verification logs committed (final round + history).
4. README with install / build / usage sections in that order.
5. (Adjacent, not in this repo) PR or branch hygiene for `~/nomon@feat/openclaw-runtime` so the upstream side is presentable.

## 10. Deferred to autopilot

Choices the autopilot may make without further consultation:

- License file content (default: MIT, matching nomon-ai)
- README split: single bilingual file vs. `README.md` + `README.ko.md`
- GitHub Actions CI configuration
- Exact wording / structure of reviewer prompts (constraints in §8 are binding)
- Test framework (default: pytest)
- Repo description, topics, badges, branding
- Whether to add a `Makefile` or stay pyproject-only

## 11. Out of Scope (v1)

- ClawHub registry submission
- Windows-specific installer behavior (assume macOS/Linux first; `paths.py` should not block Windows but is not validated there)
- Automatic upgrade flow (`nomon upgrade`)
- Telemetry / usage reporting

## 12. Risks

- **uvx availability**: installer assumes `uv` is installed. Guard with a clear error message and link to install instructions if `uvx` is not on PATH.
- **MCP merge collisions**: existing user customizations of `claude-mcp-config.json` could conflict. Mitigation: managed-block marker + refuse-and-diagnose on collision rather than overwrite.
- **nomon adapter drift**: `feat/openclaw-runtime` is unmerged upstream; if it gets rebased, the SKILL.md command surface might shift. Mitigation: §8 dim 5 makes this an explicit reviewer concern.
- **Reviewer flakiness**: agent reviewers may score inconsistently. Mitigation: run each dim with deterministic prompt + seeded examples; record full reviewer output for audit.
