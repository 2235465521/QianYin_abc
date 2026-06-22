"""
WSGI config for emis_core project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emis_core.settings')

application = get_wsgi_application()
