# -*- coding: utf-8 -*-
"""
Inspect Django database standard documents and output to utf-8 file.
"""
import os, sys, json
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emis_core.settings')

import django
django.setup()

from standards_parser.models import StandardDocument

docs = StandardDocument.objects.all().order_by('-created_at')

data = []
for doc in docs:
    data.append({
        'id': doc.id,
        'standard_code': doc.standard_code,
        'year_code': doc.year_code,
        'cn_name': doc.cn_name,
        'status': doc.status,
        'replace_standard': doc.replace_standard,
        'extraction_source': doc.extraction_source,
        'revision_changes': doc.revision_changes,
        'error_reason': doc.error_reason[:200] if doc.error_reason else None
    })

# Save to a json file
with open('db_inspect.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Successfully exported {len(data)} records to db_inspect.json")
