from baclab.tools.registry import register_tool
from typing import Any, Dict, List
from django.conf import settings
from baclab.tools.base import BaseBioinformaticsTool


@register_tool('bakta')
class BaktaTool(BaseBioinformaticsTool):
    """
    Bakta bacterial genome annotation pipeline tool wrapper.
    """
    tool_name = "bakta"

    def build_command(self, options: Dict[str, Any]) -> List[str]:
        script_path = getattr(settings, "BAKTA_SCRIPT", "/app/tools/annotationPipeline/bakta_script.sh")
        db_path = options.get("db_path") or getattr(settings, "BAKTA_DB_PATH", "/databases/BaktaDB")
        return [script_path, self.input_dir, self.output_dir, db_path, str(self.cores)]
