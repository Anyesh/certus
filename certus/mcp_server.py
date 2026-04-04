"""Certus MCP server: exposes certificate validation and checking as MCP tools.

The pure handler functions (handle_*) are importable and testable without MCP
installed. The MCP transport layer is confined to create_mcp_server() and main().
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from certus.generation.core import parse_llm_response, validate_and_score
from certus.generation.prompts import get_format_spec, get_safe_expression_context
from certus.sidecar.hashing import compute_body_hash, compute_signature_hash, extract_function_info
from certus.sidecar.models import SidecarCertificate, SidecarFileEntry
from certus.sidecar.store import SidecarStore
from certus.checker.runner import check_from_sidecar


# ---------------------------------------------------------------------------
# Pure handler functions (no MCP dependency)
# ---------------------------------------------------------------------------


def handle_validate_certificate(
    project_root: str,
    function_name: str,
    source_file: str,
    certificate_json: str,
    strength_threshold: float = 0.5,
    num_runs: int = 30,
) -> dict:
    """Validate a certificate JSON against a function and return structured feedback.

    Returns a dict with keys: structural_pass, strength, passed, feedback.
    """
    cert = parse_llm_response(certificate_json)
    if cert is None:
        return {
            "structural_pass": False,
            "strength": 0.0,
            "passed": False,
            "feedback": "Could not parse certificate JSON.",
        }

    source_path = Path(project_root) / source_file
    if not source_path.exists():
        return {
            "structural_pass": False,
            "strength": 0.0,
            "passed": False,
            "feedback": f"Source file not found: {source_file}",
        }

    source_code = source_path.read_text()

    result = validate_and_score(
        cert,
        source_code,
        function_name,
        strength_threshold=strength_threshold,
        num_runs=num_runs,
    )

    # structural_pass is True when there are no unverified (unsafe/unparseable) claims
    structural_pass = len(result.structural_errors) == 0

    return {
        "structural_pass": structural_pass,
        "strength": result.strength,
        "passed": result.passed,
        "feedback": result.feedback,
    }


def handle_save_certificate(
    project_root: str,
    function_name: str,
    source_file: str,
    certificate_json: str,
    strength_threshold: float = 0.5,
    num_runs: int = 30,
) -> dict:
    """Validate then persist a certificate. Refuses to save if validation fails.

    Returns a dict with keys: saved, feedback.
    """
    validation = handle_validate_certificate(
        project_root=project_root,
        function_name=function_name,
        source_file=source_file,
        certificate_json=certificate_json,
        strength_threshold=strength_threshold,
        num_runs=num_runs,
    )

    if not validation["passed"]:
        return {
            "saved": False,
            "feedback": validation["feedback"],
        }

    # parse_llm_response cannot return None here since validation passed
    cert = parse_llm_response(certificate_json)
    assert cert is not None

    source_path = Path(project_root) / source_file
    source_code = source_path.read_text()

    funcs = extract_function_info(source_code)
    func_info = next((f for f in funcs if f.qualname == function_name), None)
    if func_info is None:
        return {
            "saved": False,
            "feedback": f"Function '{function_name}' not found in {source_file}.",
        }

    entry = SidecarFileEntry(
        signature_hash=compute_signature_hash(func_info),
        body_hash=compute_body_hash(func_info),
        generated_by="certus.mcp_server",
        generated_at=datetime.now(tz=timezone.utc),
        certificate=cert,
    )

    store = SidecarStore(project_root)
    store.init()
    store.save_certificate(source_file, function_name, entry)

    return {
        "saved": True,
        "feedback": validation["feedback"],
    }


def handle_list_uncertified(
    project_root: str,
    source_file: str | None = None,
) -> dict:
    """List functions that lack a valid certificate.

    If source_file is provided, scan only that file; otherwise scan all .py
    files in project_root, skipping .certus/ and .venv/ directories.

    Returns a dict with key: functions (list of dicts with qualname and file).
    """
    store = SidecarStore(project_root)
    root = Path(project_root)

    if source_file is not None:
        files: list[str] = [source_file]
    else:
        files = []
        for py_file in root.rglob("*.py"):
            relative = py_file.relative_to(root)
            if any(part in (".certus", ".venv") for part in relative.parts):
                continue
            files.append(str(relative))

    results = []
    for sf in files:
        for func_info in store.get_uncertified_functions(sf):
            results.append({"qualname": func_info.qualname, "file": sf})

    return {"functions": results}


def handle_check_file(
    project_root: str,
    source_file: str,
    num_runs: int = 30,
) -> dict:
    """Run the checker against all certified functions in a source file.

    Returns a dict with key: results (list of per-function dicts).
    """
    store = SidecarStore(project_root)
    sidecar = store.load_file(source_file)
    if sidecar is None or not sidecar.functions:
        return {"results": []}

    source_path = Path(project_root) / source_file
    if not source_path.exists():
        return {"results": []}

    source_code = source_path.read_text()
    results = []

    for func_name, entry in sidecar.functions.items():
        report = check_from_sidecar(func_name, entry, source_code, num_runs=num_runs)
        summary = report.summary
        results.append({
            "function": func_name,
            "passed": summary.violated == 0 and summary.unverified == 0,
            "strength": report.strength.rejection_rate,
            "proved": summary.proved,
            "held": summary.held,
            "violated": summary.violated,
            "unverified": summary.unverified,
        })

    return {"results": results}


def handle_check_project(
    project_root: str,
    num_runs: int = 30,
) -> dict:
    """Run the checker across all certified functions in the project.

    Returns a dict with totals and per-file summaries.
    """
    store = SidecarStore(project_root)
    certified_files = store.list_certified_files()

    total_functions = 0
    total_passed = 0
    total_failed = 0
    file_summaries = []

    for sidecar_file in certified_files:
        sf = sidecar_file.source_file
        file_result = handle_check_file(project_root=project_root, source_file=sf, num_runs=num_runs)
        file_passed = sum(1 for r in file_result["results"] if r["passed"])
        file_failed = len(file_result["results"]) - file_passed

        total_functions += len(file_result["results"])
        total_passed += file_passed
        total_failed += file_failed

        file_summaries.append({
            "file": sf,
            "functions": len(file_result["results"]),
            "passed": file_passed,
            "failed": file_failed,
            "results": file_result["results"],
        })

    return {
        "total_functions": total_functions,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "files": file_summaries,
    }


# ---------------------------------------------------------------------------
# MCP server setup (MCP imports are deferred so handler tests work without mcp)
# ---------------------------------------------------------------------------


def create_mcp_server():  # noqa: ANN201
    """Create and configure the MCP Server instance.

    MCP imports are intentionally deferred inside this function so that the
    handler functions above remain importable even when the mcp package is not
    installed. This is required for the test suite to work in minimal envs.
    """
    # Circular-import-free lazy MCP import: mcp is optional at module load time
    from mcp.server import Server  # noqa: PLC0415
    from mcp.types import Resource, TextContent, Tool  # noqa: PLC0415

    server = Server("certus")

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri="certus://spec/format",  # type: ignore[arg-type]
                name="Certificate Format Specification",
                description="JSON format for Certus certificates",
                mimeType="text/plain",
            ),
            Resource(
                uri="certus://spec/safe-expressions",  # type: ignore[arg-type]
                name="Safe Expression Rules",
                description="Rules governing which expressions are allowed in certificates",
                mimeType="text/plain",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri):
        uri_str = str(uri)
        if uri_str == "certus://spec/format":
            return [TextContent(type="text", text=get_format_spec())]
        if uri_str == "certus://spec/safe-expressions":
            return [TextContent(type="text", text=get_safe_expression_context())]
        raise ValueError(f"Unknown resource URI: {uri_str}")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="validate_certificate",
                description=(
                    "Parse and validate a Certus certificate JSON against a function. "
                    "Returns structural_pass, strength, passed, and feedback."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string", "description": "Qualified name of the function"},
                        "source_file": {"type": "string", "description": "Path relative to project root"},
                        "certificate_json": {"type": "string", "description": "Certificate as JSON string"},
                        "strength_threshold": {"type": "number", "default": 0.5},
                        "num_runs": {"type": "integer", "default": 30},
                    },
                    "required": ["function_name", "source_file", "certificate_json"],
                },
            ),
            Tool(
                name="save_certificate",
                description=(
                    "Validate and persist a Certus certificate. "
                    "The certificate is only saved if it passes validation."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string"},
                        "source_file": {"type": "string"},
                        "certificate_json": {"type": "string"},
                        "strength_threshold": {"type": "number", "default": 0.5},
                        "num_runs": {"type": "integer", "default": 30},
                    },
                    "required": ["function_name", "source_file", "certificate_json"],
                },
            ),
            Tool(
                name="list_uncertified",
                description=(
                    "List functions that lack a certificate. "
                    "Optionally restricted to a single source file."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source_file": {
                            "type": "string",
                            "description": "Optional relative path to restrict scan",
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="check_file",
                description="Run the Certus checker on all certified functions in a source file.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source_file": {"type": "string"},
                        "num_runs": {"type": "integer", "default": 30},
                    },
                    "required": ["source_file"],
                },
            ),
            Tool(
                name="check_project",
                description="Run the Certus checker across all certified functions in the project.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "num_runs": {"type": "integer", "default": 30},
                    },
                    "required": [],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        project_root = os.environ.get("CERTUS_PROJECT_ROOT", ".")

        if name == "validate_certificate":
            result = handle_validate_certificate(
                project_root=project_root,
                function_name=arguments["function_name"],
                source_file=arguments["source_file"],
                certificate_json=arguments["certificate_json"],
                strength_threshold=arguments.get("strength_threshold", 0.5),
                num_runs=arguments.get("num_runs", 30),
            )
        elif name == "save_certificate":
            result = handle_save_certificate(
                project_root=project_root,
                function_name=arguments["function_name"],
                source_file=arguments["source_file"],
                certificate_json=arguments["certificate_json"],
                strength_threshold=arguments.get("strength_threshold", 0.5),
                num_runs=arguments.get("num_runs", 30),
            )
        elif name == "list_uncertified":
            result = handle_list_uncertified(
                project_root=project_root,
                source_file=arguments.get("source_file"),
            )
        elif name == "check_file":
            result = handle_check_file(
                project_root=project_root,
                source_file=arguments["source_file"],
                num_runs=arguments.get("num_runs", 30),
            )
        elif name == "check_project":
            result = handle_check_project(
                project_root=project_root,
                num_runs=arguments.get("num_runs", 30),
            )
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return server


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Certus MCP server over stdio."""
    import asyncio  # noqa: PLC0415 (stdlib, safe to defer)
    import mcp.server.stdio  # noqa: PLC0415 (optional mcp dep)

    server = create_mcp_server()

    async def _run() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
