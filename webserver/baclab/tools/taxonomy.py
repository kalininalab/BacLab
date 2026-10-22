from baclab.tools.registry import register_tool
import glob
import os
from typing import Optional
import pandas as pd
from django.conf import settings
from baclab.tools.base import BaseBioinformaticsTool


@register_tool('taxonomy')
class TaxonomyTool(BaseBioinformaticsTool):
    """
    GTDB-Tk for the in-house strains (the Taxonomy Finder tool page itself is tools/taxonomyFinder/tool.py).
    """
    tool_name = "taxonomy"

    def run_gtdbtk_inhouse(self, strain_dir: str, db_path: Optional[str] = None) -> Optional[str]:
        gtdbtk_out = self.output_dir
        os.makedirs(gtdbtk_out, exist_ok=True)
        db_path_val = db_path or getattr(settings, "GTDBTK_DB_PATH", "/databases/GTDBTkDB")

        cmd_str = (
            f"export GTDBTK_DATA_PATH='{db_path_val}' && "
            f"source /opt/conda/etc/profile.d/conda.sh && "
            f"conda activate server_taxonomy && "
            f"gtdbtk classify_wf --genome_dir '{strain_dir}' --out_dir '{gtdbtk_out}' --extension fasta --cpus {self.cores} --force"
        )
        self.run_in_conda(cmd_str=cmd_str, env_name="server_taxonomy")

        summary_files = glob.glob(os.path.join(gtdbtk_out, "gtdbtk.*.summary.tsv"))
        if not summary_files:
            raise RuntimeError(f"GTDB-Tk produced no summary.tsv in {gtdbtk_out}")

        df = pd.read_csv(summary_files[0], sep="\t")
        if "user_genome" in df.columns:
            df.rename(columns={"user_genome": "Strain"}, inplace=True)

        classification = None
        if not df.empty and "classification" in df.columns:
            classification = df["classification"].iloc[0]
        if not classification:
            raise RuntimeError(f"GTDB-Tk summary.tsv in {gtdbtk_out} contained no classification")

        tax_tsv_path = getattr(settings, "INHOUSE_TAXONOMY_PATH", "/databases/StrainsDB/Inhouse_taxonomy.tsv")
        if os.path.exists(tax_tsv_path):
            df.to_csv(tax_tsv_path, sep="\t", mode="a", header=False, index=False)
        else:
            os.makedirs(os.path.dirname(tax_tsv_path), exist_ok=True)
            df.to_csv(tax_tsv_path, sep="\t", mode="w", header=True, index=False)

        return classification
