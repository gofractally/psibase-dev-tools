import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from . import jobs as _jobs
from . import resources, tools_async
from .schemas import description_for, load_definition
from .tools_sync import SYNC_TOOLS, call_sync_tool


SERVER_NAME = "psibase-mcp"


def _json_content(payload: dict[str, Any]) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2, sort_keys=True))]


def _job_id_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["job_id"],
        "properties": {"job_id": {"type": "string"}},
    }


def _cancel_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["job_id"],
        "properties": {
            "job_id": {"type": "string"},
            "workspace_root": {
                "type": "string",
                "description": "Caller's workspace_root, compared to the job's recorded workspace_root. Defaults to the auto-detected workspace.",
            },
            "force": {
                "type": "boolean",
                "default": False,
                "description": "Bypass the workspace-ownership check. Use only for cleanup of orphaned jobs or jobs whose recorded workspace is stale.",
            },
        },
    }


def _logs_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["job_id"],
        "properties": {
            "job_id": {"type": "string"},
            "stream": {"type": "string", "enum": ["stdout", "stderr"], "default": "stdout"},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
            "max_bytes": {"type": "integer", "minimum": 1},
        },
    }


def _tool(name: str, description: str, input_schema: dict[str, Any]) -> types.Tool:
    return types.Tool(name=name, description=description, inputSchema=input_schema)


def tool_specs() -> list[types.Tool]:
    full_build = load_definition("run_full_build")
    package_build = load_definition("build_package")
    rust_build = load_definition("build_rust_service")
    service_tests = load_definition("run_service_tests")
    launch_chain = load_definition("launch_chain")
    resume_chain = load_definition("resume_chain")

    specs: list[types.Tool] = [
        _tool(
            "start_full_build",
            description_for(
                full_build,
                mcp_name="start_full_build",
                extra="Starts the canonical full build (cmake configure if needed, then make) asynchronously. Poll with get_build_status and inspect output with get_build_logs.",
            ),
            full_build["inputSchema"],
        ),
        _tool(
            "start_package_build",
            description_for(
                package_build,
                mcp_name="start_package_build",
                extra="Starts make for one package target asynchronously.",
            ),
            package_build["inputSchema"],
        ),
        _tool(
            "start_rust_service_build",
            description_for(
                rust_build,
                mcp_name="start_rust_service_build",
                extra="Starts cargo-psibase build for a Rust service asynchronously.",
            ),
            rust_build["inputSchema"],
        ),
        _tool(
            "get_build_status",
            "Read async build job state for a job_id returned by start_*_build.",
            _job_id_schema(),
        ),
        _tool(
            "get_build_logs",
            "Read stdout or stderr slices for an async build job.",
            _logs_schema(),
        ),
        _tool(
            "cancel_build",
            "Cancel a running async build job.",
            _cancel_schema(),
        ),
        _tool(
            "start_service_tests",
            description_for(
                service_tests,
                mcp_name="start_service_tests",
                extra="Starts service tests asynchronously.",
            ),
            service_tests["inputSchema"],
        ),
        _tool(
            "get_test_status",
            "Read async service-test job state for a job_id returned by start_service_tests.",
            _job_id_schema(),
        ),
        _tool(
            "get_test_logs",
            "Read stdout or stderr slices for an async service-test job.",
            _logs_schema(),
        ),
        _tool(
            "cancel_tests",
            "Cancel a running async service-test job.",
            _cancel_schema(),
        ),
        _tool(
            "launch_chain",
            description_for(launch_chain, mcp_name="launch_chain", extra="Starts psinode asynchronously."),
            launch_chain["inputSchema"],
        ),
        _tool(
            "resume_chain",
            description_for(resume_chain, mcp_name="resume_chain", extra="Resumes psinode asynchronously."),
            resume_chain["inputSchema"],
        ),
        _tool(
            "get_chain_status",
            "Read async chain job state.",
            _job_id_schema(),
        ),
        _tool(
            "get_chain_logs",
            "Read stdout or stderr slices for an async chain job.",
            _logs_schema(),
        ),
        _tool(
            "cancel_chain",
            "Cancel a running async chain job.",
            _cancel_schema(),
        ),
    ]

    for name in sorted(SYNC_TOOLS):
        specs.append(
            _tool(
                name,
                description_for(
                    load_definition(name),
                    mcp_name=name,
                    extra=(
                        "Runs psibase boot synchronously against api_url."
                        if name == "boot_chain"
                        else "Returns a generated Rust test snippet synchronously."
                    ),
                ),
                load_definition(name)["inputSchema"],
            )
        )

    return specs


def build_server() -> Server:
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return tool_specs()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        try:
            if name in tools_async.BUILD_STARTERS:
                return _json_content(tools_async.start_build(name, arguments))
            if name == "start_service_tests":
                return _json_content(tools_async.start_tests(arguments))
            if name in tools_async.CHAIN_STARTERS:
                return _json_content(tools_async.start_chain(name, arguments))
            if name in {"get_build_status", "get_test_status", "get_chain_status"}:
                return _json_content(tools_async.status(str((arguments or {})["job_id"])))
            if name in {"get_build_logs", "get_test_logs", "get_chain_logs"}:
                return _json_content(tools_async.logs(arguments))
            if name in {"cancel_build", "cancel_tests", "cancel_chain"}:
                return _json_content(tools_async.cancel(arguments))
            if name in SYNC_TOOLS:
                return _json_content(call_sync_tool(name, arguments))
        except ValueError as exc:
            msg = str(exc)
            error_code = "workspace_mismatch" if "workspace_root mismatch" in msg else "invalid_input"
            return _json_content(
                {
                    "ok": False,
                    "status": "error",
                    "summary": msg,
                    "error_code": error_code,
                    "error_category": "mcp",
                }
            )
        except Exception as exc:
            payload = {
                "ok": False,
                "status": "error",
                "summary": str(exc),
                "error_code": "mcp_call_failed",
                "error_category": "mcp",
            }
            ec = getattr(exc, "error_code", None)
            if isinstance(ec, str):
                payload["error_code"] = ec
            return _json_content(payload)
        raise ValueError(f"Unknown tool: {name}")

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        return [
            types.Resource(uri=entry["uri"], name=entry["name"], mimeType=entry["mimeType"])
            for entry in resources.iter_resources()
        ]

    @server.read_resource()
    async def read_resource(uri: Any) -> str:
        return resources.read_resource(str(uri))

    return server


async def run_stdio() -> None:
    try:
        _jobs.gc_terminal_jobs()
    except Exception:  # noqa: BLE001
        pass

    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
