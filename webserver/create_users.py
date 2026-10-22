import os
import django
from django.contrib.auth import get_user_model

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

User = get_user_model()

import environ
env = environ.Env()
username = env('ADMIN_USER', default='admin')
email = env('ADMIN_EMAIL', default='admin@example.com')
password = env('ADMIN_PASS', default='password')

superuser_list = [{'username': username, 'email': email, 'password': password}]

for superuser in superuser_list:
    username = superuser.get('username')
    email = superuser.get('email')
    password = superuser.get('password')

    if username and email and password:
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, email=email, password=password)
            print(f'Superuser {username} created')
        else:
            print(f'Superuser {username} already exists')

