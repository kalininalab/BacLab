from baclab.tools.registry import register_tool
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from django.conf import settings
from baclab.tools.base import BaseBioinformaticsTool


class AntismashError(Exception):
    """Raised when antiSMASH fails or output validation fails."""
    pass


@register_tool('antismash')
class AntismashTool(BaseBioinformaticsTool):
    """
    antiSMASH secondary metabolite BGC identification pipeline tool wrapper.
    """
    tool_name = "antismash"

    def build_command(self, options: Dict[str, Any]) -> List[str]:
        script_path = getattr(settings, "ANTISMASH_SCRIPT", "/app/tools/annotationPipeline/antismash_script.sh")
        db_path = options.get("db_path") or getattr(settings, "ANTISMASH_DB_PATH", "/databases/AntismashDB")

        cmd = [script_path, self.input_dir, self.output_dir, db_path, str(self.cores)]
        if options.get("local_testing"):
            cmd.append("True")
        return cmd

    def run_single_genome(self, genome_path: str, out_dir: str, strain_id: str) -> Tuple[str, str]:
        db_path = getattr(settings, "ANTISMASH_DB_PATH", "/databases/AntismashDB")
        cmd_str = (
            f"antismash -c {self.cores} --cb-general --cb-knownclusters --cb-subclusters "
            f"--asf --pfam2go --smcog-trees --genefinding-tool prodigal "
            f"--databases '{db_path}' --output-dir '{out_dir}' --output-basename '{strain_id}' '{genome_path}'"
        )
        env_vars = {"OMPI_MCA_plm_rsh_agent": ""}
        stdout, stderr = self.run_in_conda(cmd_str=cmd_str, env_name="server_antismash", env_vars=env_vars)
        self.apply_selinux_fix(out_dir)
        return stdout, stderr

    def apply_selinux_fix(self, antismash_dir: str) -> None:
        if os.path.exists(antismash_dir):
            subprocess.run(f"chcon -R -l 's0' '{antismash_dir}'", shell=True, executable="/bin/bash")

    def validate_output(self, antismash_output_dir: str, file_name: str) -> str:
        target_dir = os.path.join(antismash_output_dir, file_name, "antismash")
        zip_file = os.path.join(target_dir, f"{file_name}.zip")
        if os.path.exists(zip_file):
            os.remove(zip_file)

        if not os.path.exists(target_dir) or not os.listdir(target_dir):
            raise AntismashError("antiSMASH finished but generated an empty output directory.")

        index_html = os.path.join(target_dir, "index.html")
        if not os.path.exists(index_html):
            raise AntismashError("antiSMASH run failed: 'index.html' was not generated in the output directory.")

        json_files = [f for f in os.listdir(target_dir) if f.endswith(".json")]
        if not json_files:
            raise AntismashError("antiSMASH run completed but failed to yield a structural data JSON file.")

        primary_json = os.path.join(target_dir, json_files[0])
        if os.path.getsize(primary_json) == 0:
            raise AntismashError("antiSMASH produced an empty (0 KB) JSON file. Your input sequence sequences might be too short or invalid.")

        return primary_json

    def validate_single_genome_output(self, out_dir: str) -> None:
        """
        Validates antiSMASH output written directly into out_dir (the layout
        produced by run_single_genome), as opposed to validate_output's
        out_dir/<file_name>/antismash/ layout produced by the batch script.
        """
        if not os.path.isdir(out_dir) or not os.listdir(out_dir):
            raise AntismashError(f"antiSMASH finished but generated an empty output directory: {out_dir}")

        index_html = os.path.join(out_dir, "index.html")
        if not os.path.exists(index_html):
            raise AntismashError(f"antiSMASH run failed: 'index.html' was not generated in {out_dir}")

        json_files = [f for f in os.listdir(out_dir) if f.endswith(".json")]
        if not json_files:
            raise AntismashError(f"antiSMASH run completed but failed to yield a structural data JSON file in {out_dir}")

        primary_json = os.path.join(out_dir, json_files[0])
        if os.path.getsize(primary_json) == 0:
            raise AntismashError("antiSMASH produced an empty (0 KB) JSON file. Your input sequence might be too short or invalid.")

    def copy_to_antismash_db(self, antismash_out: str, strain_id: str, global_antismash_dir: Optional[str] = None) -> None:
        self.validate_single_genome_output(antismash_out)
        target_base = global_antismash_dir or getattr(settings, "ANTISMASH_DATA_PATH", "/databases/AntismashDB")
        target_dir = os.path.join(target_base, strain_id)
        if not os.path.exists(target_dir):
            shutil.copytree(antismash_out, target_dir)
