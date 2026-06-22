# -*- coding: utf-8 -*-
"""
Reprocess all failed standard documents using the updated parser.
"""
import os, sys, traceback
from datetime import datetime
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emis_core.settings')

import django
django.setup()

from django.db import transaction
from django.utils import timezone
from standards_parser.models import StandardDocument
from standards_parser.parsers import get_parser
from standards_parser.parsers.revision_extractor import extract_revision_changes

def main():
    failed_docs = StandardDocument.objects.filter(status='failed')
    total_failed = failed_docs.count()
    print(f"Found {total_failed} failed documents in database.")
    
    if total_failed == 0:
        print("No failed documents to process.")
        return
        
    files_root = os.environ.get('STANDARD_FILES_ROOT', 'Y:/磁盘阵列/标准文件下载/')
    current_time = timezone.now().date()
    
    success_count = 0
    fixed_count = 0
    
    for i, doc in enumerate(failed_docs, 1):
        print(f"[{i}/{total_failed}] Processing ID {doc.id}: {doc.standard_code}")
        
        file_path_clean = str(doc.source_file).replace('\\', '/')
        if os.path.isabs(file_path_clean) or (len(file_path_clean) > 1 and file_path_clean[1] == ':'):
            full_path = file_path_clean
        else:
            rel_path = file_path_clean.strip('/')
            full_path = os.path.join(files_root, rel_path)
            
        if not os.path.exists(full_path):
            print(f"  -> Physical file missing: {full_path}")
            continue
            
        try:
            parser = get_parser(full_path)
            parse_result = parser.parse()
            metadata = parse_result.get('metadata', {})
            
            # Extracted standard code components
            standard_prefix = metadata.get('standard_prefix')
            standard_code = metadata.get('standard_code')
            standard_year = metadata.get('standard_year')
            full_standard_number = metadata.get('full_standard_number')
            
            if standard_prefix and standard_code:
                standard_code_str = f"{standard_prefix} {standard_code}"
            else:
                standard_code_str = full_standard_number or doc.standard_code or ""
                
            doc.standard_code = standard_code_str
            doc.year_code = standard_year or ""
            doc.ics_code = metadata.get('ics_code') or ""
            doc.ccs_code = metadata.get('ccs_code') or ""
            
            # Publish/Implement dates
            pub_date_str = metadata.get('publish_date')
            imp_date_str = metadata.get('implement_date')
            
            if pub_date_str:
                try:
                    doc.publish_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
                
            if imp_date_str:
                try:
                    doc.implement_date = datetime.strptime(imp_date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
                
            # Replace standard
            replace_std = metadata.get('replace_standard')
            if replace_std:
                doc.replace_standard = replace_std

            # Extract revision changes
            raw_text = parse_result.get('full_text', parse_result.get('raw_text', ''))
            revision_result = extract_revision_changes(raw_text)
            doc.revision_changes = revision_result.get('changes') or []
            doc.extraction_source = revision_result.get('source', 'failed')
            if not replace_std and revision_result.get('replaced_standard'):
                doc.replace_standard = revision_result['replaced_standard']

            doc.status = 'success'
            doc.error_reason = None
            doc.save()
            print(f"  -> Successfully parsed! Extracted {len(doc.revision_changes)} revisions via {doc.extraction_source}")
            success_count += 1
            
        except Exception as e:
            print(f"  -> Parsing still failed: {e}")
            doc.error_reason = traceback.format_exc()[:2000]
            doc.save()

    print("=" * 60)
    print(f"Reprocessing completed. Successfully recovered: {success_count}/{total_failed}")
    print("=" * 60)

if __name__ == '__main__':
    main()
