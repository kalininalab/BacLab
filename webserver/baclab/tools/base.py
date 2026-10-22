import abc
import glob
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from django.conf import settings
from baclab.error_utils import format_error_log


class BaseBioinformaticsTool(abc.ABC):
    """
    Abstract base class for all bioinformatics tools in BacLab.
    """
    tool_name: str = "base_tool"

    # Glob patterns (relative to output_dir, ** allowed) for internal working
    # files a tool leaves behind - called proteins, HMM/BLAST databases, raw
    # per-feature dumps, scratch file lists - that aren't meant for end users.
    # The results archive users download is built directly from output_dir,
    # so post_process() should call self.prune_output_dir() before returning
    # to actually keep these out of it (not just out of the results page).
    EXCLUDE_FROM_RESULTS: List[str] = []

    def __init__(
        self,
        job_id: str,
        input_dir: str,
        output_dir: str,
        cores: Optional[int] = None,
        **kwargs: Any
    ) -> None:
        self.job_id = job_id
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.cores = cores if cores is not None else getattr(settings, "CORES_PER_JOB", 4)
        self.extra_args = kwargs

        if self.input_dir:
            os.makedirs(self.input_dir, exist_ok=True)
        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)

    def prune_output_dir(self) -> None:
        """Delete files/directories matching EXCLUDE_FROM_RESULTS from
        output_dir, so the results zip built from it doesn't ship them."""
        if not self.output_dir or not self.EXCLUDE_FROM_RESULTS:
            return
        for pattern in self.EXCLUDE_FROM_RESULTS:
            for path in glob.glob(os.path.join(self.output_dir, pattern), recursive=True):
                if os.path.islink(path) or os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                elif os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)

    def validate_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates and sanitizes the input options before building the command.
        Tools should override this to provide strict schema validation.
        Raises ValueError if validation fails.
        """
        return options

    def build_command(self, options: Dict[str, Any]) -> List[str]:
        """
        Constructs the shell command array or argument list required to run the tool.
        """
        return []

    def run_command(self, command: List[str], cwd: Optional[str] = None) -> Tuple[str, str]:
        """
        Executes a command vector using subprocess.run, returning stdout and stderr.
        Raises subprocess.CalledProcessError on non-zero exit.
        """
        effective_cwd = cwd or self.output_dir
        proc = subprocess.run(
            command,
            cwd=effective_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                returncode=proc.returncode,
                cmd=command,
                output=proc.stdout,
                stderr=proc.stderr
            )
        return proc.stdout, proc.stderr

    def run_in_conda(
        self,
        cmd_str: str,
        env_name: str,
        cwd: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None
    ) -> Tuple[str, str]:
        """
        Executes a shell string within a specified Conda environment using bash.
        """
        effective_cwd = cwd or self.output_dir
        env_prefix = ""
        if env_vars:
            env_prefix = " ".join([f"export {k}='{v}' &&" for k, v in env_vars.items()]) + " "

        full_cmd = (
            f"{env_prefix}source /opt/conda/etc/profile.d/conda.sh && "
            f"conda activate {env_name} && "
            f"{cmd_str}"
        )

        proc = subprocess.run(
            full_cmd,
            shell=True,
            executable="/bin/bash",
            cwd=effective_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                returncode=proc.returncode,
                cmd=full_cmd,
                output=proc.stdout,
                stderr=proc.stderr
            )
        return proc.stdout, proc.stderr

    def execute(self, options: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """
        Main execution workflow: validates options, builds command and runs tool execution.
        """
        if options is None:
            options = {}
        options = self.validate_options(options)
        command = self.build_command(options)
        return self.run_command(command, cwd=self.output_dir)

    def post_process(self, downloads_dir: Optional[str] = None) -> None:
        """
        Optional post-processing step (copying files to downloads directory, cleanup).
        """
        pass

    def handle_error(self, exc: Exception, step: Optional[str] = None) -> Dict[str, Any]:
        """
        Formats exception details into standard structured JSON log using format_error_log.
        """
        step_name = step or f"{self.tool_name}_execution"
        stdout = getattr(exc, "output", "") or getattr(exc, "stdout", "") or ""
        stderr = getattr(exc, "stderr", "") or ""
        returncode = getattr(exc, "returncode", None)
        return format_error_log(
            exc=exc,
            step=step_name,
            tool_name=self.tool_name,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode
        )


BaseTool = BaseBioinformaticsTool

