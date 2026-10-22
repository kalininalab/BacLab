"""
webserver/baclab/error_utils.py

Utility functions for structured error formatting and logging across BacLab services.
"""

import datetime
import subprocess
import traceback
from typing import Any, Dict, Optional
from django.utils import timezone


def format_error_log(
    exc: Optional[Exception] = None,
    step: Optional[str] = None,
    tool_name: Optional[str] = None,
    stdout: str = "",
    stderr: str = "",
    returncode: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Formats an exception and execution context into a JSON-serializable dictionary.

    Keys returned:
    - timestamp: ISO 8601 timestamp string
    - tool_name: name of the bioinformatics tool or component
    - step: pipeline/execution step name
    - error_type: string representation of exception class name
    - error_message: string description of the exception
    - traceback: full traceback string
    - stdout: standard output string
    - stderr: standard error string
    - returncode: exit returncode integer or None
    """
    try:
        ts = timezone.now().isoformat()
    except Exception:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if exc is not None:
        error_type = exc.__class__.__name__
        error_message = str(exc)
    else:
        error_type = "UnknownError"
        error_message = ""

    tb_text = ""
    if exc is not None:
        if hasattr(exc, "__traceback__") and exc.__traceback__ is not None:
            tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        else:
            tb_text = traceback.format_exc()
            if tb_text == "NoneType: None\n":
                tb_text = ""

    final_stdout = stdout
    final_stderr = stderr
    final_returncode = returncode

    if exc is not None:
        if isinstance(exc, subprocess.CalledProcessError) or hasattr(exc, "stdout") or hasattr(exc, "output"):
            exc_stdout = getattr(exc, "stdout", None) or getattr(exc, "output", None)
            if not final_stdout and exc_stdout:
                final_stdout = exc_stdout

        if isinstance(exc, subprocess.CalledProcessError) or hasattr(exc, "stderr"):
            exc_stderr = getattr(exc, "stderr", None)
            if not final_stderr and exc_stderr:
                final_stderr = exc_stderr

        if isinstance(exc, subprocess.CalledProcessError) or hasattr(exc, "returncode"):
            exc_rc = getattr(exc, "returncode", None)
            if final_returncode is None and exc_rc is not None:
                final_returncode = exc_rc

    if isinstance(final_stdout, bytes):
        final_stdout = final_stdout.decode("utf-8", errors="replace")
    else:
        final_stdout = str(final_stdout or "")

    if isinstance(final_stderr, bytes):
        final_stderr = final_stderr.decode("utf-8", errors="replace")
    else:
        final_stderr = str(final_stderr or "")

    return {
        "timestamp": ts,
        "tool_name": tool_name or "",
        "step": step or "",
        "error_type": error_type,
        "error_message": error_message,
        "traceback": tb_text,
        "stdout": final_stdout,
        "stderr": final_stderr,
        "returncode": final_returncode,
    }
