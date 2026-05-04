# openclaw-ouroboros

Ouroboros as an OpenClaw skill + MCP. Spec-first workflow engine inside Claude Code.

---

## Quick Start — Install

```bash
uvx --from git+https://github.com/jkf87/openclaw-ouroboros openclaw-ouroboros install
```

Then in OpenClaw: `/ouroboros:setup`

Done! You now have `/ouroboros:interview`, `/ouroboros:run`, `/ouroboros:status`, `/ouroboros:cancel`.

Verify: `uvx --from git+https://github.com/jkf87/openclaw-ouroboros openclaw-ouroboros doctor`

Uninstall: `uvx --from git+https://github.com/jkf87/openclaw-ouroboros openclaw-ouroboros uninstall`

---

## Building this Repo

See `docs/design.md` (spec) and `prompts/build-handoff.md` (build brief).

Run tests: `pytest tests/ -v`

Auto-test: `bash verification/auto/run_install_test.sh`

---

## Using Ouroboros in OpenClaw

```
/ouroboros:interview "your idea"
↓
Ouroboros generates seed.yaml
↓
/ouroboros:run <seed.yaml>
↓
Workflow executes: plan → code → test → verify
```

See `prompts/usage.md` for templates.

---

## License

MIT — See `LICENSE` file.
