"""Fill the site with demonstration users, groups and runs (with mock result files) so every page can be looked at.

    python manage.py create_demo_data            # 3 groups, 10 users, ~40 runs; every demo user's password is printed
    python manage.py create_demo_data --remove   # delete exactly what this command created

Everything it creates is marked by the e-mail domain @demo.baclab.example, so --remove never touches real data.
"""
import os
import random
import shutil
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from baclab.models import JobRecord, LabGroup, Project
from baclab.toolkit.files import zip_folder

DOMAIN = 'demo.baclab.example'
PASSWORD = 'demo-baclab-1'

GROUPS = ['Soil Microbiology Lab', 'Clinical Genomics Lab', 'Natural Products Lab']
USERS = [   # username, first, last, group index
    ('m.schumacher', 'Maria', 'Schumacher', 0), ('m.rossi', 'Marco', 'Rossi', 0), ('l.nguyen', 'Linh', 'Nguyen', 0), ('t.okafor', 'Tunde', 'Okafor', 0),
    ('s.hansen', 'Sofie', 'Hansen', 1), ('d.petrov', 'Dmitri', 'Petrov', 1), ('y.tanaka', 'Yuki', 'Tanaka', 1),
    ('c.silva', 'Carla', 'Silva', 2), ('j.murphy', 'Jack', 'Murphy', 2), ('p.sharma', 'Priya', 'Sharma', 2),
]
GENOMES = ['Ecoli_K12', 'Kpneu_HS11286', 'Saureus_USA300', 'Paeru_PAO1', 'Smela_A3', 'Mxan_DK1622', 'Bsub_168', 'Ecoli_O157']


# ---- mock result files per tool: {relative path: text} ----
def _padloc(rng, genomes):
    systems = ['CBASS_I', 'RM_type_I', 'PD-T4-6', 'Gabija', 'DISARM_type_I', 'Thoeris_I', 'AbiE']
    rows = ['genome,system.number,seqid,system,target.name,protein.name,full.seq.E.value,domain.iE.value,target.coverage,hmm.coverage,start,end,strand']
    for g in genomes:
        for n in range(1, rng.randint(2, 5)):
            rows.append(f'{g},{n},contig_1,{rng.choice(systems)},ORF_{n}_{g},protein_{n},{rng.random() * 1e-5:.2e},{rng.random() * 1e-4:.2e},0.9,0.8,{n * 1000},{n * 1000 + 900},+')
    return {'padloc_results.csv': '\n'.join(rows) + '\n'}


def _defensefinder(rng, genomes):
    types = ['RM', 'Abi', 'CBASS', 'Gabija', 'Wadjet', 'Septu']
    systems = ['genome\tsys_id\ttype\tsubtype\tsys_beg\tsys_end\tprotein_in_syst\tgenes_count\tname_of_profiles_in_sys']
    genes = ['genome\thit_id\tgene_name\thit_i_eval\thit_score\thit_profile_cov\tsys_id\tsys_wholeness']
    for g in genomes:
        for n in range(1, rng.randint(2, 6)):
            kind = rng.choice(types)
            systems.append(f'{g}\t{g}_{n}\t{kind}\t{kind}_I\tORF_{n}\tORF_{n + 3}\tORF_{n},ORF_{n + 1}\t2\t{kind}A,{kind}B')
            genes.append(f'{g}\tORF_{n}\t{kind}A\t1e-30\t120.5\t0.95\t{g}_{n}\t1.0')
    return {'defensefinder_results.tsv': '\n'.join(systems) + '\n', 'defensefinder_genes.tsv': '\n'.join(genes) + '\n'}


def _amr(rng, genomes):
    header = 'Protein identifier\tContig id\tStart\tStop\tStrand\tElement symbol\tElement name\tType\tSubtype\tClass\tSubclass\t% Coverage of reference\t% Identity to reference'
    genes = [('blaTEM-1', 'beta-lactamase TEM-1', 'BETA-LACTAM'), ('sul1', 'sulfonamide-resistant dihydropteroate synthase', 'SULFONAMIDE'),
             ('tet(A)', 'tetracycline efflux MFS transporter', 'TETRACYCLINE'), ('aac(3)-IIa', 'aminoglycoside acetyltransferase', 'AMINOGLYCOSIDE'),
             ('qnrS1', 'quinolone resistance pentapeptide repeat protein', 'QUINOLONE')]
    rows = [header]
    for g in genomes:
        for sym, name, cls in rng.sample(genes, rng.randint(1, 4)):
            rows.append(f'prot_{g}\tcontig_{rng.randint(1, 9)}\t{rng.randint(100, 9000)}\t{rng.randint(9100, 9900)}\t+\t{sym}\t{name}\tAMR\tAMR\t{cls}\t{cls}\t100.00\t{rng.uniform(96, 100):.2f}')
    return {'amrfinderplus_results.tsv': '\n'.join(rows) + '\n'}


def _mlst(rng, genomes):
    schemes = [('ecoli', [10, 131, 69, 73]), ('kpneumoniae', [258, 11, 15]), ('saureus', [8, 5, 22])]
    rows = []
    for g in genomes:
        scheme, sts = rng.choice(schemes)
        rows.append(f'{g}.fasta\t{scheme}\t{rng.choice(sts)}\tadk(1)\tfumC(2)\tgyrB(3)\ticd(4)\tmdh(5)\tpurA(6)\trecA(7)')
    return {'mlst_results.tsv': '\n'.join(rows) + '\n'}


def _checkm2(rng, genomes):
    rows = ['Name\tCompleteness\tContamination\tCompleteness_Model_Used\tTranslation_Table_Used\tCoding_Density\tContig_N50\tAverage_Gene_Length\tGenome_Size\tGC_Content\tTotal_Coding_Sequences\tTotal_Contigs\tMax_Contig_Length']
    for g in genomes:
        rows.append(f'{g}\t{rng.uniform(88, 99.9):.2f}\t{rng.uniform(0.1, 4):.2f}\tNeural Network (Specific Model)\t11\t0.88\t{rng.randint(80000, 400000)}\t320\t{rng.randint(4000000, 5500000)}\t0.5\t4500\t{rng.randint(20, 150)}\t900000')
    return {'checkm2_results.tsv': '\n'.join(rows) + '\n'}


def _kraken2(rng, genomes):
    species = ['Escherichia coli', 'Klebsiella pneumoniae', 'Staphylococcus aureus', 'Pseudomonas aeruginosa']
    top = rng.choice(species)
    others = [s for s in species if s != top]
    return {'kraken2_results.tsv': f'{rng.uniform(90, 99):.2f}\t1500\t1500\tS\t562\t  {top}\n{rng.uniform(0.3, 2):.2f}\t30\t30\tS\t573\t  {others[0]}\n{rng.uniform(0.1, 1):.2f}\t10\t10\tS\t1280\t  {others[1]}\n'}


def _ani(rng, genomes):
    pairs = ['Query\tReference\tANI\tMatched_Fragments\tTotal_Fragments']
    for a in genomes:
        for b in genomes:
            pairs.append(f'{a}.fasta\t{b}.fasta\t{100.0 if a == b else rng.uniform(78, 99.9):.2f}\t{rng.randint(1000, 1800)}\t1800')
    return {'ani_results.tsv': '\n'.join(pairs) + '\n'}


def _gecco(rng, genomes):
    rows = ['sequence_id\tcluster_id\tstart\tend\taverage_p\tmax_p\ttype\tproteins\tdomains']
    for g in genomes:
        for n in range(1, rng.randint(2, 5)):
            rows.append(f'{g}_contig_{n}\t{g}_contig_{n}_cluster_1\t{n * 5000}\t{n * 5000 + 30000}\t0.91\t0.99\t{rng.choice(["Polyketide", "NRP", "RiPP", "Terpene", "Saccharide"])}\tprot_a;prot_b\tPF00109;PF00501')
    return {'gecco_results.tsv': '\n'.join(rows) + '\n'}


def _bigslice(rng, genomes):
    rows = ['bgc_id\tgenome\tbgc\tcontig_edge\tlen_nt\tproduct_classes\tGCF\tdistance_to_GCF']
    for i in range(1, 25):
        rows.append(f'{i}\t{rng.choice(genomes)}\t{rng.choice(genomes)}.region00{i % 9 + 1}\tFalse\t{rng.randint(15000, 90000)}\t{rng.choice(["NRPS", "T1PKS", "RiPP", "terpene"])}\t{rng.randint(1, 8)}\t{rng.uniform(0.05, 0.38):.3f}')
    return {'bigslice_results.tsv': '\n'.join(rows) + '\n'}


def _screen(rng, genomes):
    profile = ['genome\tsize_bp\tcontigs\tN50\tGC_percent\tMLST_scheme\tMLST_ST\tAMR_genes\tcompleteness_percent\tcontamination_percent\tdefence_systems']
    for g in genomes:
        profile.append(f'{g}\t{rng.randint(4000000, 5600000)}\t{rng.randint(20, 150)}\t{rng.randint(80000, 400000)}\t{rng.uniform(50, 66):.2f}\tecoli\t{rng.choice([10, 131, 73])}\t{rng.randint(0, 6)}\t{rng.uniform(90, 99.9):.1f}\t{rng.uniform(0.1, 3):.1f}\t{rng.randint(1, 7)}')
    status = ['step\tanalysis\tstatus\tnote'] + [f'{s}\t{s} analysis\tdone\t' for s in ('mlst', 'amr', 'checkm2', 'defence')]
    files = {'genome_profile.tsv': '\n'.join(profile) + '\n', 'step_status.tsv': '\n'.join(status) + '\n'}
    files.update(_mlst(rng, genomes))
    return {'genome_profile.tsv': files['genome_profile.tsv'], 'step_status.tsv': files['step_status.tsv'], 'mlst/mlst_results.tsv': files['mlst_results.tsv']}


# job type -> (generator, min genomes, max genomes, label of the typical use)
TOOLS = {
    'padloc': (_padloc, 1, 3), 'defensefinder': (_defensefinder, 1, 3), 'amrfinderplus': (_amr, 1, 3), 'mlst': (_mlst, 1, 4),
    'checkm2': (_checkm2, 1, 3), 'kraken2': (_kraken2, 1, 1), 'ani': (_ani, 3, 4), 'gecco': (_gecco, 1, 2), 'bigslice': (_bigslice, 3, 5), 'screen': (_screen, 2, 4),
}
LABELS = ['Reference strains', 'Outbreak isolates batch 1', 'Re-sequenced with new kit', 'Pilot', 'Paper figure 2', '', '', '', '']
PROJECTS = ['Outbreak 2026', 'Soil isolates', 'Thesis chapter 3']


def make_job(rng, user, job_type, status, age_days, project=None, label='', private=False, retention=None):
    generator, low, high = TOOLS[job_type]
    genomes = rng.sample(GENOMES, rng.randint(low, high))
    job_id = f'{job_type}-demo-{rng.getrandbits(48):012x}'
    queued = timezone.now() - timedelta(days=age_days, hours=rng.randint(0, 5))
    started = queued + timedelta(minutes=rng.randint(1, 20)) if status != 'queued' else None
    finished = started + timedelta(minutes=rng.randint(3, 90)) if status in ('finished', 'failed') else None
    summary = None
    record = JobRecord.objects.create(
        job_id=job_id, job_type=job_type, status=status, owner=user, group=user.profile.group, label=label, private=private, project=project,
        retention_days=retention, started_at=started, finished_at=finished, email=user.email,
        error_message='The tool stopped with an error: the input does not look like a nucleotide FASTA file.' if status == 'failed' else '',
        parameters={'inputs': [f'{g}.fasta' for g in genomes], 'settings': {}, 'fields': {'genomes': [f'{g}.fasta' for g in genomes]}})
    JobRecord.objects.filter(pk=job_id).update(queued_at=queued)   # queued_at is auto_now_add
    if status == 'finished':
        base = os.path.join(settings.DOWNLOAD_DIR, job_id)
        os.makedirs(os.path.join(base, 'input'), exist_ok=True)
        for g in genomes:
            with open(os.path.join(base, 'input', f'{g}.fasta'), 'w') as handle:
                handle.write(f'>{g}_contig_1 demo\n' + 'ACGT' * 40 + '\n')
        for relative, text in generator(rng, genomes).items():
            os.makedirs(os.path.dirname(os.path.join(base, relative)), exist_ok=True)
            with open(os.path.join(base, relative), 'w') as handle:
                handle.write(text)
        with open(os.path.join(base, 'CITATION.txt'), 'w') as handle:
            handle.write('Demo data - not a real analysis.\n')
        os.makedirs(settings.RESULTS_DIR, exist_ok=True)
        zip_folder(base, os.path.join(settings.RESULTS_DIR, f'{job_id}.zip'))
        old = (timezone.now() - timedelta(days=age_days)).timestamp()
        os.utime(base, (old, old))
    return record, summary


class Command(BaseCommand):
    help = "Create demonstration groups, users and runs with mock results (all marked @demo.baclab.example); --remove deletes them again."

    def add_arguments(self, parser):
        parser.add_argument('--remove', action='store_true', help='delete the demo users, their runs and result files')
        parser.add_argument('--seed', type=int, default=7, help='random seed, for the same data every time')

    def handle(self, *args, **options):
        User = get_user_model()
        if options['remove']:
            return self.remove(User)
        rng = random.Random(options['seed'])
        if User.objects.filter(email__endswith='@' + DOMAIN).exists():
            self.stdout.write(self.style.WARNING('Demo data exists already. Run with --remove first to recreate it.'))
            return

        groups = [LabGroup.objects.get_or_create(name=name)[0] for name in GROUPS]
        users = []
        for username, first, last, group_index in USERS:
            user = User.objects.create_user(username, f'{username}@{DOMAIN}', PASSWORD, first_name=first, last_name=last)
            user.profile.group = groups[group_index]
            user.profile.save()
            users.append(user)

        tools = list(TOOLS)
        created = 0
        for user in users:
            projects = [Project.objects.create(owner=user, name=name) for name in rng.sample(PROJECTS, 2)]
            for n in range(rng.randint(3, 6)):
                status = rng.choices(['finished', 'failed', 'running', 'queued'], weights=[10, 2, 1, 1])[0]
                age = rng.choice([0, 0, 1, 2, 3, 5, 9, 14, 21, 25, 27])   # all within the default retention, so the clean-up does not remove them
                make_job(rng, user, rng.choice(tools), status, age if status in ('finished', 'failed') else 0,
                         project=rng.choice(projects + [None]), label=rng.choice(LABELS), private=rng.random() < 0.15,
                         retention=90 if rng.random() < 0.1 and status == 'finished' else None)
                created += 1
        self.stdout.write(self.style.SUCCESS(f'Created {len(GROUPS)} groups, {len(users)} users and {created} runs.'))
        self.stdout.write(f'Log in as any of: {", ".join(u[0] for u in USERS)}   password: {PASSWORD}')
        self.stdout.write('Make sure ACCOUNTS_ENABLED=True. Remove everything again with:  python manage.py create_demo_data --remove')

    def remove(self, User):
        users = User.objects.filter(email__endswith='@' + DOMAIN)
        job_ids = list(JobRecord.objects.filter(owner__in=users).values_list('job_id', flat=True))
        for job_id in job_ids:
            shutil.rmtree(os.path.join(settings.DOWNLOAD_DIR, job_id), ignore_errors=True)
            try:
                os.remove(os.path.join(settings.RESULTS_DIR, f'{job_id}.zip'))
            except OSError:
                pass
        JobRecord.objects.filter(job_id__in=job_ids).delete()
        Project.objects.filter(owner__in=users).delete()
        count = users.count()
        users.delete()
        LabGroup.objects.filter(name__in=GROUPS, members__isnull=True).delete()
        self.stdout.write(self.style.SUCCESS(f'Removed {count} demo users and {len(job_ids)} runs.'))
