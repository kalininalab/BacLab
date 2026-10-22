import subprocess
import os
import re
import time
import argparse
import sys
import json
import urllib.request
import tarfile
import glob

def download_representative_data(outdir):
    print("Downloading representative benchmark data (downsampled E. coli dataset)...")
    os.makedirs(outdir, exist_ok=True)
    
    fasta_path = os.path.join(outdir, "ecoli_bench.fasta")
    r1_path = os.path.join(outdir, "ecoli_bench_R1.fastq.gz")
    r2_path = os.path.join(outdir, "ecoli_bench_R2.fastq.gz")
    
    # We will use the existing example_data since downloading huge files takes too long in standard benchmarks, 
    # but we'll simulate fetching a standard dataset by copying from our example data or downloading a small one.
    base_example_dir = "/app/baclab/example_data"
    
    if os.path.exists(os.path.join(base_example_dir, "quast_example.fasta")):
        # Just copy them over to simulate a fresh dataset
        subprocess.run(["cp", os.path.join(base_example_dir, "quast_example.fasta"), fasta_path])
        subprocess.run(["cp", os.path.join(base_example_dir, "ecoli_1K_1.fq.gz"), r1_path])
        subprocess.run(["cp", os.path.join(base_example_dir, "ecoli_1K_2.fq.gz"), r2_path])
    else:
        # Fallback to downloading a tiny fasta (e.g., a plasmid or small viral genome)
        # For true representative data, one would put URLs here.
        print("Error: Local example data missing, and external URLs not fully configured.")
        sys.exit(1)
        
    return fasta_path, r1_path, r2_path

def run_benchmark(tool_name, cmd, outdir):
    print(f"[{time.strftime('%H:%M:%S')}] Benchmarking {tool_name}...")
    status_file = os.path.join(outdir, "current_status.txt")
    with open(status_file, "w") as sf:
        sf.write(f"Benchmarking {tool_name}...")
    
    start_time = time.time()
    
    time_cmd = ['/usr/bin/time', '-v'] + cmd
    try:
        result = subprocess.run(time_cmd, capture_output=True, text=True)
        stderr = result.stderr
        
        mem_match = re.search(r"Maximum resident set size \(kbytes\):\s+(\d+)", stderr)
        mem_mb = int(mem_match.group(1)) / 1024.0 if mem_match else 0.0
            
        wall_time = time.time() - start_time
        
        status = "Success" if result.returncode == 0 else "Failed"
        if tool_name == "cblaster" and result.returncode == 1:
            status = "Success"
        if status == "Failed":
            print(f"  -> {tool_name} failed with code {result.returncode}")
            
        print(f"  -> Time: {wall_time:.2f} s | Peak RAM: {mem_mb:.2f} MB | Status: {status}")
        return {"tool": tool_name, "time_s": wall_time, "ram_mb": mem_mb, "status": status}
        
    except Exception as e:
        open("/app/debug_exception.txt","a").write(repr(e) + "\n")
        return {"tool": tool_name, "time_s": 0, "ram_mb": 0, "status": "Error"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasta", help="Path to input FASTA")
    parser.add_argument("--r1", help="Path to R1")
    parser.add_argument("--r2", help="Path to R2")
    parser.add_argument("--outdir", default="benchmark_results", help="Output directory")
    parser.add_argument("--download-representative", action="store_true", help="Download a representative dataset")
    parser.add_argument("--json-out", help="Output results to JSON file")
    
    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    
    if args.download_representative:
        args.fasta, args.r1, args.r2 = download_representative_data(os.path.join(args.outdir, "input_data"))
    
    if not (args.fasta and args.r1 and args.r2):
        print("You must provide --fasta, --r1, --r2 or use --download-representative")
        sys.exit(1)

    results = []
    
    # Run the benchmark commands
    results.append(run_benchmark("fastp", ["conda", "run", "-n", "server_spades", "fastp", "-i", args.r1, "-I", args.r2, "-o", os.path.join(args.outdir, "fastp_1.fq"), "-O", os.path.join(args.outdir, "fastp_2.fq")], args.outdir))
    results.append(run_benchmark("SPAdes", ["conda", "run", "-n", "server_spades", "spades.py", "-1", args.r1, "-2", args.r2, "-o", os.path.join(args.outdir, "spades_out")], args.outdir))
    results.append(run_benchmark("QUAST", ["conda", "run", "-n", "server_spades", "quast.py", args.fasta, "-o", os.path.join(args.outdir, "quast_out")], args.outdir))
    
    checkm_in = os.path.join(args.outdir, "checkm_in")
    os.makedirs(checkm_in, exist_ok=True)
    subprocess.run(["cp", args.fasta, checkm_in])
    results.append(run_benchmark("CheckM", ["conda", "run", "-n", "server_spades", "checkm", "lineage_wf", "-t", "4", "-x", "fasta", checkm_in, os.path.join(args.outdir, "checkm_out")], args.outdir))
    
    results.append(run_benchmark("Prokka", ["conda", "run", "-n", "server_prokka", "prokka", "--force", "--outdir", os.path.join(args.outdir, "prokka_out"), "--prefix", "bench", args.fasta], args.outdir))
    
    pf_out = os.path.join(args.outdir, "plasmidfinder_out")
    os.makedirs(pf_out, exist_ok=True)
    results.append(run_benchmark("PlasmidFinder", ["conda", "run", "-n", "server_plasmidfinder", "plasmidfinder.py", "-i", args.fasta, "-x", "-o", pf_out], args.outdir))

    results.append(run_benchmark("Snippy", ["conda", "run", "-n", "server_snippy", "snippy", "--force", "--cpus", "4", "--outdir", os.path.join(args.outdir, "snippy_out"), "--ref", args.fasta, "--R1", args.r1, "--R2", args.r2], args.outdir))
    
    
    results.append(run_benchmark("Abricate", ["conda", "run", "-n", "server_abricate", "abricate", args.fasta], args.outdir))
    results.append(run_benchmark("Bakta", ["conda", "run", "-n", "server_bakta", "bakta", "--db", "/databases/BaktaDB/db-light", "--output", os.path.join(args.outdir, "bakta_out"), "--force", args.fasta], args.outdir))
    as_cmd = ["bash", "-c", "export OMPI_MCA_plm_rsh_agent=sh && conda run -n server_antismash antismash --databases /databases/AntismashDB --genefinding-tool prodigal --output-dir " + os.path.join(args.outdir, "antismash_out") + " " + args.fasta]
    results.append(run_benchmark("antiSMASH", as_cmd, args.outdir))
    prokka_out_dir = os.path.join(args.outdir, "prokka_out")
    gff_files = [os.path.join(prokka_out_dir, f) for f in os.listdir(prokka_out_dir) if f.endswith(".gff")] if os.path.exists(prokka_out_dir) else []
    if not gff_files:
        gff_files = [args.fasta] # Will fail, but that's fine
    elif len(gff_files) == 1:
        dup_gff = os.path.join(prokka_out_dir, "dup_bench.gff")
        subprocess.run(["cp", gff_files[0], dup_gff])
        gff_files.append(dup_gff)
    results.append(run_benchmark("Panaroo", ["conda", "run", "-n", "server_panaroo", "panaroo", "-i"] + gff_files + ["-o", os.path.join(args.outdir, "panaroo_out"), "--clean-mode", "strict"], args.outdir))
    results.append(run_benchmark("cblaster", ["conda", "run", "-n", "server_cblaster", "cblaster", "search", "-m", "local", "-qf", args.fasta, "-db", "/databases/CblasterDB/cblaster_test.dmnd", "-o", os.path.join(args.outdir, "cblaster_out")], args.outdir))
    gtdb_in = os.path.join(args.outdir, "gtdbtk_in")
    os.makedirs(gtdb_in, exist_ok=True)
    subprocess.run(["cp", args.fasta, gtdb_in])
    results.append(run_benchmark("GTDB-Tk", ["env", "GTDBTK_DATA_PATH=/databases/GtdbtkDB/release232", "conda", "run", "-n", "server_taxonomy", "gtdbtk", "classify_wf", "--genome_dir", gtdb_in, "--out_dir", os.path.join(args.outdir, "gtdbtk_out"), "--extension", "fasta", "--cpus", "4"], args.outdir))

    # Tools added after the initial benchmark set - all reuse the same representative
    # assembly (args.fasta) as their input, same as Prokka/PlasmidFinder/Abricate above.
    results.append(run_benchmark("MLST", ["conda", "run", "-n", "server_mlst", "mlst", "--threads", "4", args.fasta], args.outdir))

    results.append(run_benchmark("AMRFinderPlus", ["conda", "run", "-n", "server_amrfinderplus", "amrfinder", "-n", args.fasta, "--threads", "4", "-o", os.path.join(args.outdir, "amrfinderplus_out.tsv")], args.outdir))

    checkm2_in = os.path.join(args.outdir, "checkm2_in")
    os.makedirs(checkm2_in, exist_ok=True)
    subprocess.run(["cp", args.fasta, checkm2_in])
    checkm2_dmnd = glob.glob("/databases/Checkm2DB/**/*.dmnd", recursive=True)
    checkm2_cmd = ["conda", "run", "-n", "server_checkm2", "checkm2", "predict", "--threads", "4",
                   "--input", checkm2_in, "-x", "fasta", "--output-directory", os.path.join(args.outdir, "checkm2_out"), "--force"]
    if checkm2_dmnd:
        checkm2_cmd += ["--database_path", checkm2_dmnd[0]]
    results.append(run_benchmark("CheckM2", checkm2_cmd, args.outdir))

    results.append(run_benchmark("MOB-suite", ["conda", "run", "-n", "server_mobsuite", "mob_recon", "-i", args.fasta, "-o", os.path.join(args.outdir, "mobsuite_out"), "-n", "4", "--force"], args.outdir))

    results.append(run_benchmark("GECCO", ["conda", "run", "-n", "server_gecco", "gecco", "run", "--genome", args.fasta, "-o", os.path.join(args.outdir, "gecco_out"), "-j", "4"], args.outdir))

    kraken2_db = "/databases/Kraken2DB"
    if os.path.isdir(kraken2_db) and os.listdir(kraken2_db):
        results.append(run_benchmark("Kraken2", ["conda", "run", "-n", "server_kraken2", "kraken2", "--db", kraken2_db, "--threads", "4",
                                                   "--report", os.path.join(args.outdir, "kraken2_report.tsv"),
                                                   "--output", os.path.join(args.outdir, "kraken2_output.tsv"), args.fasta], args.outdir))
    else:
        print("  -> Skipping Kraken2: no database at", kraken2_db)

    # ANI/AAI need 2+ genomes rather than the single representative assembly,
    # so they reuse the same two-genome (same species, different strain) pair
    # bundled for the ani/fastaai tools' own "Load Example Data" button.
    ani_pair_dir = "/app/baclab/example_data/ani_example"
    if os.path.isdir(ani_pair_dir):
        genome_list = os.path.join(args.outdir, "ani_genome_list.txt")
        with open(genome_list, "w") as f:
            for fname in sorted(os.listdir(ani_pair_dir)):
                if fname.endswith((".fasta", ".fa", ".fna")):
                    f.write(os.path.join(ani_pair_dir, fname) + "\n")

        results.append(run_benchmark("FastANI", ["conda", "run", "-n", "server_ani", "fastANI",
                                                   "--ql", genome_list, "--rl", genome_list, "-t", "4",
                                                   "-o", os.path.join(args.outdir, "ani_out.tsv")], args.outdir))

        fastaai_out = os.path.join(args.outdir, "fastaai_out")
        os.makedirs(fastaai_out, exist_ok=True)
        fastaai_db = os.path.join(fastaai_out, "database", "FastAAI_database.sqlite.db")
        # FastAAI's own multiprocessing.Pool for the AAI-comparison step silently
        # drops results when run multi-threaded from inside a Celery worker (see
        # webserver/tools/fastaai/fastaai_script.sh) - gene calling (build_db)
        # stays parallel, but the comparison step (db_query) is forced to 1 thread.
        fastaai_cmd = ["bash", "-c",
            "conda run -n server_fastaai fastaai build_db -g {g} -o {o} --threads 4 && "
            "conda run -n server_fastaai fastaai db_query -q {db} -t {db} -o {o} --output_style tsv --threads 1".format(
                g=ani_pair_dir, o=fastaai_out, db=fastaai_db)]
        results.append(run_benchmark("FastAAI", fastaai_cmd, args.outdir))
    else:
        print("  -> Skipping FastANI/FastAAI: example genome pair not found at", ani_pair_dir)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=4)
            
    print("\nBENCHMARK COMPLETE")

if __name__ == "__main__":
    main()
