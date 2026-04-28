"""Minimal structured-error helpers for ha-mcp-nodered.

A trimmed-down version of the patterns used in the upstream ha-mcp project,
covering only the error codes the Node-RED tools actually raise. The shape
is: every tool failure raises ``ToolError`` carrying a JSON-serialised error
response so MCP clients see ``isError=true`` and can parse the structured
error payload from the message.
"""

import json
from enum import StrEnum
from typing import Any, NoReturn

from fastmcp.exceptions import ToolError


class ErrorCode(StrEnum):
    """Error codes raised by ha-mcp-nodered tools."""

    CONNECTION_FAILED = "CONNECTION_FAILED"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_INVALID_PARAMETER = "VALIDATION_INVALID_PARAMETER"
    VALIDATION_MISSING_PARAMETER = "VALIDATION_MISSING_PARAMETER"
    SERVICE_CALL_FAILED = "SERVICE_CALL_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def create_error_response(
    code: ErrorCode,
    message: str,
    details: str | None = None,
    suggestions: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the structured error envelope expected by MCP clients."""
    error: dict[str, Any] = {"code": code.value, "message": message}
    if details:
        error["details"] = details
    if suggestions:
        error["suggestion"] = suggestions[0]
        if len(suggestions) > 1:
            error["suggestions"] = suggestions
    response: dict[str, Any] = {"success": False, "error": error}
    if context:
        response.update(context)
    return response


def create_resource_not_found_error(
    resource_type: str,
    identifier: str,
    details: str | None = None,
) -> dict[str, Any]:
    return create_error_response(
        ErrorCode.RESOURCE_NOT_FOUND,
        f"{resource_type} '{identifier}' not found",
        details=details,
        context={"resource_type": resource_type, "identifier": identifier},
    )


def raise_tool_error(error_response: dict[str, Any]) -> NoReturn:
    """Raise ToolError carrying the structured error payload as JSON."""
    raise ToolError(json.dumps(error_response, indent=2, default=str))


def exception_to_structured_error(
    error: Exception,
    context: dict[str, Any] | None = None,
    suggestions: list[str] | None = None,
) -> NoReturn:
    """Classify an exception into a structured error and raise ToolError.

    Routes the local NodeRed* exceptions to specific codes. Anything else
    falls through to INTERNAL_ERROR with the original message attached.
    """
    from .client import NodeRedAPIError, NodeRedAuthError, NodeRedConnectionError

    msg = str(error)
    code: ErrorCode
    extra_details: str | None = None

    if isinstance(error, NodeRedAuthError):
        code = ErrorCode.AUTH_INVALID_TOKEN
    elif isinstance(error, NodeRedConnectionError):
        if "timeout" in msg.lower():
            code = ErrorCode.CONNECTION_TIMEOUT
        else:
            code = ErrorCode.CONNECTION_FAILED
    elif isinstance(error, NodeRedAPIError):
        code = ErrorCode.SERVICE_CALL_FAILED
        extra_details = error.response_text
    else:
        code = ErrorCode.INTERNAL_ERROR
        extra_details = type(error).__name__

    response = create_error_response(
        code,
        msg,
        details=extra_details,
        suggestions=suggestions,
        context=context,
    )
    raise_tool_error(response)
