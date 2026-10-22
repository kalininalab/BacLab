from baclab.tools.registry import register_tool
import glob
import os
import shutil
from typing import Any, Dict, List, Tuple
from django.conf import settings
from baclab.tools.base import BaseBioinformaticsTool


@register_tool('prokka')
class ProkkaTool(BaseBioinformaticsTool):
    """
    Prokka bacterial genome annotation tool wrapper.
    """
    tool_name = "prokka"

    def build_command(self, options: Dict[str, Any]) -> List[str]:
        script_path = getattr(settings, "PROKKA_SCRIPT", "/app/tools/annotationPipeline/prokka_script.sh")
        return [script_path, self.input_dir, self.output_dir, str(self.cores)]

    def run_single_genome(self, genome_path: str, out_dir: str) -> Tuple[str, str]:
        cmd_str = f"prokka --outdir '{out_dir}' --cpus {self.cores} '{genome_path}' --force"
        return self.run_in_conda(cmd_str=cmd_str, env_name="server_prokka")

    def post_process_strain(self, prokka_out: str, strain_id: str) -> None:
        annotation_db_dir = getattr(settings, "ANNOTATION_DB_PATH", "/databases/AnnotationDB")
        os.makedirs(annotation_db_dir, exist_ok=True)

        faa_files = glob.glob(os.path.join(prokka_out, "*.faa"))
        if not faa_files:
            raise RuntimeError(f"Prokka produced no .faa output in {prokka_out}")
        shutil.copy2(faa_files[0], os.path.join(annotation_db_dir, f"{strain_id}.faa"))

        gbk_files = glob.glob(os.path.join(prokka_out, "*.gbk"))
        if not gbk_files:
            raise RuntimeError(f"Prokka produced no .gbk output in {prokka_out}")
        shutil.copy2(gbk_files[0], os.path.join(annotation_db_dir, f"{strain_id}.gbk"))
