# psibase AI tools (MCP)

Portable Python package providing psibase **build / test / chain** tools over MCP (and a small CLI).

This package is developed in `psibase-dev-tools` and **bundled into** the Psibase DX Tools VS Code/Cursor extension. Prefer installing the extension; it owns the venv and registers the MCP server when a psibase workspace is open.

Agent-team (`ai-tools team …`) is **not** included here yet.

## Local development

```bash
cd ai/tools
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

MCP stdio entrypoint:

```bash
.venv/bin/python -m psibase_ai_tools.mcp
```

## Layout

| Path                                | Role                                    |
| ----------------------------------- | --------------------------------------- |
| `src/psibase_ai_tools/lib/`         | Build/test/chain implementations        |
| `src/psibase_ai_tools/mcp/`         | MCP stdio adapter                       |
| `src/psibase_ai_tools/data/`        | Packaged default `project-profile.yaml` |
| `src/psibase_ai_tools/definitions/` | Tool JSON schemas                       |
