from django.core.management.base import BaseCommand
from baclab.models import CustomDatabase, GlobalStrainResource, InhouseStrain, ThemeSettings
import json
import os
from django.conf import settings

class Command(BaseCommand):
    help = 'Sync custom databases from JSON files into the database'
    requires_system_checks = []

    def handle(self, *args, **options):
        tools_map = {
            'blast': settings.BLAST_DATABASE_PATH,
            'cblaster': settings.CBLASTER_DATABASE_PATH,
            'genomemining': '/databases/GenomeMiningDB',
        }

        for tool, db_path in tools_map.items():
            json_file = os.path.join(db_path, 'database_options.json')
            if not os.path.exists(json_file):
                continue
            
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    options = data.get('database_options', [])
                    for opt in options:
                        value = opt.get('value')
                        if value and value != 'default':
                            # Get or create the custom database record
                            db, created = CustomDatabase.objects.get_or_create(
                                db_name=value,
                                tool=tool,
                                defaults={'status': 'ready'}
                            )
                            if created:
                                self.stdout.write(self.style.SUCCESS(f"Added custom DB {value} for {tool}"))
                            elif db.status != 'ready':
                                db.status = 'ready'
                                db.save()
                                self.stdout.write(self.style.SUCCESS(f"Updated status for custom DB {value} for {tool} to ready"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error reading {json_file}: {e}"))

        # Sync GlobalStrainResource
        try:
            tree_dir = os.path.join(settings.MEDIA_ROOT, 'resources', 'trees')
            tax_dir = os.path.join(settings.MEDIA_ROOT, 'resources', 'taxonomy')
            
            tree_file = None
            if os.path.exists(tree_dir):
                trees = [f for f in os.listdir(tree_dir) if f.endswith('.nwk')]
                if trees:
                    tree_file = f'resources/trees/{trees[0]}'
                    
            tax_file = None
            if os.path.exists(tax_dir):
                taxes = [f for f in os.listdir(tax_dir) if f.endswith('.tsv')]
                if taxes:
                    tax_file = f'resources/taxonomy/{taxes[0]}'
                    
            if tree_file or tax_file:
                global_resource, created = GlobalStrainResource.objects.get_or_create(pk=1)
                updated = False
                if tree_file and not global_resource.phylogenetic_tree:
                    global_resource.phylogenetic_tree = tree_file
                    updated = True
                if tax_file and not global_resource.taxonomy_db:
                    global_resource.taxonomy_db = tax_file
                    updated = True
                    
                if updated:
                    global_resource.save()
                    self.stdout.write(self.style.SUCCESS("Synced Global Strain Resources from filesystem"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error syncing Global Strain Resources: {e}"))

        # Sync Inhouse Strains
        try:
            strains_dir = '/databases/StrainsDB/strains'
            if os.path.exists(strains_dir):
                for strain_id in os.listdir(strains_dir):
                    strain_path = os.path.join(strains_dir, strain_id)
                    if os.path.isdir(strain_path):
                        strain, created = InhouseStrain.objects.get_or_create(
                            strain_id=strain_id,
                            defaults={
                                'status': 'completed',
                                'genome_fasta': f'inhouse_uploads/{strain_id}.fasta'
                            }
                        )
                        if created:
                            self.stdout.write(self.style.SUCCESS(f"Synced Inhouse Strain: {strain_id}"))
                        elif strain.status not in ['completed', 'failed']:
                            strain.status = 'completed'
                            strain.save()
                            self.stdout.write(self.style.SUCCESS(f"Updated status for Inhouse Strain {strain_id} to completed"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error syncing Inhouse Strains: {e}"))

        # Sync Theme Settings
        try:
            theme, created = ThemeSettings.objects.get_or_create(
                pk=1,
                defaults={
                    'primary_color': '#6366f1',
                    'secondary_color': '#4f46e5',
                    'background_color': '#f8fafc',
                    'button_color': '#6366f1',
                    'text_color': '#334155'
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS("Created default ThemeSettings"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error creating default ThemeSettings: {e}"))
