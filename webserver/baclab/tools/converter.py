from baclab.tools.registry import register_tool
import os
from typing import Any, Dict, List, Tuple
from django.conf import settings
from baclab.tools.base import BaseBioinformaticsTool


@register_tool('converter')
class GbkConverterTool(BaseBioinformaticsTool):
    """
    GenBank <-> FASTA converter tool wrapper.
    """
    tool_name = "converter"

    def build_command(self, options: Dict[str, Any]) -> List[str]:
        script_path = getattr(settings, "GBK_CONVERTER_SCRIPT", "/app/tools/annotationPipeline/gbk_converter_script.sh")
        input_file = options.get("input_file", "")
        output_file = options.get("output_file", "")
        return [script_path, input_file, output_file]

    def convert_genbank_to_fasta(self, input_file: str, output_file: str) -> Tuple[str, str]:
        script_path = getattr(settings, "GBK_CONVERTER_SCRIPT", "/app/tools/annotationPipeline/gbk_converter_script.sh")
        command = [script_path, input_file, output_file]
        return self.run_command(command, cwd=os.path.dirname(output_file))

    def convert_if_needed(self) -> bool:
        converted = False
        if not os.path.exists(self.input_dir):
            return False

        for file_name in os.listdir(self.input_dir):
            if file_name.lower().endswith((".gbk", ".gbff", ".gb")):
                input_file = os.path.join(self.input_dir, file_name)
                output_file = os.path.join(self.input_dir, "user_input.fasta")
                self.convert_genbank_to_fasta(input_file, output_file)
                converted = True
        return converted
