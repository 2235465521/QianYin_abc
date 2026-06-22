import os
import sys
import logging
import traceback
import pymysql
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from standards_parser.models import StandardDocument
from standards_parser.parsers import get_parser
from standards_parser.parsers.revision_extractor import extract_revision_changes

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Django management command to import standards from the mydate database.
    Performs batch processing, document parsing, and imports into new_zhixiuding.
    """
    
    help = 'Import and parse standards from the legacy mydate database'
    
    def add_arguments(self, parser) -> None:
        """Add command arguments."""
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Max number of records to process (useful for quick testing)'
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip records that are already successfully imported'
        )

    def handle(self, *args, **options) -> None:
        """Main command handler."""
        limit = options.get('limit')
        skip_existing = options.get('skip_existing')
        
        # Load environment settings
        source_db_name = os.environ.get('SOURCE_DB_NAME', 'mydate')
        source_db_user = os.environ.get('SOURCE_DB_USER', 'root')
        source_db_password = os.environ.get('SOURCE_DB_PASSWORD', 'lsj223546')
        source_db_host = os.environ.get('SOURCE_DB_HOST', 'localhost')
        source_db_port = int(os.environ.get('SOURCE_DB_PORT', '3306'))
        source_db_charset = os.environ.get('SOURCE_DB_CHARSET', 'gbk')
        
        files_root = os.environ.get('STANDARD_FILES_ROOT', 'E:/标准文件库')
        batch_limit = int(os.environ.get('BATCH_WRITE_LIMIT', '10'))
        
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("[Sync] Starting Legacy Standards Import Tool"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(f"Source Database: {source_db_name} at {source_db_host}:{source_db_port}")
        self.stdout.write(f"Source Charset:  {source_db_charset}")
        self.stdout.write(f"File Root Path:  {files_root}")
        self.stdout.write(f"Batch Size:      {batch_limit}")
        self.stdout.write(self.style.SUCCESS("=" * 70))
        
        # Connect to legacy database mydate
        try:
            conn = pymysql.connect(
                host=source_db_host,
                port=source_db_port,
                user=source_db_user,
                password=source_db_password,
                database=source_db_name,
                charset=source_db_charset,
                cursorclass=pymysql.cursors.DictCursor
            )
            self.stdout.write(self.style.SUCCESS("[OK] Connected to mydate database successfully."))
        except Exception as e:
            raise CommandError(f"Failed to connect to source database: {e}")
            
        try:
            cursor = conn.cursor()
            
            # Fetch target records
            sql = """
                SELECT 
                    sb.id as base_id, 
                    sb.std_id, 
                    sb.std_chinesename, 
                    sb.std_englishname, 
                    sb.release_date,
                    sb.implement_date,
                    fp.file_path, 
                    fp.file_name
                FROM 
                    std_base sb
                INNER JOIN 
                    std_filepath fp ON sb.id = fp.base_id
            """
            
            if limit:
                sql += f" LIMIT {limit}"
                
            self.stdout.write("Fetching records from mydate...")
            cursor.execute(sql)
            records = cursor.fetchall()
            self.stdout.write(self.style.SUCCESS(f"[OK] Fetched {len(records)} mapping records from source DB."))
            
            if not records:
                self.stdout.write(self.style.WARNING("No records to import. Exiting."))
                return
                
            # Process mapping records
            batch_list = []
            processed_count = 0
            missing_files_count = 0
            
            for row in records:
                base_id = row['base_id']
                std_id = row['std_id']
                file_path = row['file_path']
                file_name = row['file_name']
                
                # Check if we should skip existing
                if skip_existing:
                    exists = StandardDocument.objects.filter(source_base_id=base_id, status='success').exists()
                    if exists:
                        logger.debug(f"Skipping already processed base_id: {base_id}")
                        continue
                
                # Clean up paths (compatible with both absolute and relative path formats)
                file_path_clean = file_path.replace('\\', '/')
                if os.path.isabs(file_path_clean) or (len(file_path_clean) > 1 and file_path_clean[1] == ':'):
                    full_path = file_path_clean
                else:
                    rel_path = file_path_clean.strip('/')
                    full_path = os.path.join(files_root, rel_path)
                
                # Check if physical file exists
                if not os.path.exists(full_path):
                    missing_files_count += 1
                    logger.warning(f"Physical file missing for base_id {base_id}: {full_path}")
                    # Skip if the file doesn't exist (you cannot parse a non-existent file)
                    continue
                    
                row['full_path'] = full_path
                batch_list.append(row)
                
                # Trigger batch import if BATCH_WRITE_LIMIT is reached
                if len(batch_list) >= batch_limit:
                    self.import_batch(batch_list)
                    processed_count += len(batch_list)
                    self.stdout.write(f"Processed {processed_count} files...")
                    batch_list.clear()
            
            # Flush any remaining items in queue
            if batch_list:
                self.import_batch(batch_list)
                processed_count += len(batch_list)
                
            self.stdout.write(self.style.SUCCESS("=" * 70))
            self.stdout.write(self.style.SUCCESS(f"[DONE] Import Completed!"))
            self.stdout.write(self.style.SUCCESS(f"  Total processed files: {processed_count}"))
            self.stdout.write(self.style.WARNING(f"  Physical missing files (skipped): {missing_files_count}"))
            self.stdout.write(self.style.SUCCESS("=" * 70))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error occurred during execution: {e}"))
            logger.error("Import command failed", exc_info=True)
            
        finally:
            cursor.close()
            conn.close()

    def import_batch(self, batch_list: list) -> None:
        """
        Process a batch of records, parse files, and perform bulk upsert.
        """
        base_ids = [item['base_id'] for item in batch_list]
        
        # Load existing documents for mapping to update them instead of duplicating
        existing_docs = {
            doc.source_base_id: doc 
            for doc in StandardDocument.objects.filter(source_base_id__in=base_ids)
        }
        
        docs_to_create = []
        docs_to_update = []
        current_time = timezone.now().date()
        
        for item in batch_list:
            base_id = item['base_id']
            full_path = item['full_path']
            std_id = item['std_id']
            
            # Reuse or create instance
            if base_id in existing_docs:
                doc = existing_docs[base_id]
                is_new = False
            else:
                doc = StandardDocument(source_base_id=base_id)
                is_new = True
            
            # Base field updates
            doc.source_file = item['file_path']
            doc.cn_name = item['std_chinesename'] or ""
            doc.en_name = item['std_englishname'] or ""
            
            # Extract standard dates from mydate as baseline fallback
            fallback_pub = item['release_date'] if item['release_date'] else current_time
            fallback_imp = item['implement_date'] if item['implement_date'] else current_time
            
            # Default placeholders for new objects (to satisfy NOT NULL requirements)
            if is_new:
                doc.standard_code = std_id or ""
                doc.year_code = ""
                doc.publish_date = fallback_pub
                doc.implement_date = fallback_imp
            
            # Run parser and update details
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
                    standard_code_str = full_standard_number or std_id or ""
                    
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
                        doc.publish_date = fallback_pub
                else:
                    doc.publish_date = fallback_pub
                    
                if imp_date_str:
                    try:
                        doc.implement_date = datetime.strptime(imp_date_str, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        doc.implement_date = fallback_imp
                else:
                    doc.implement_date = fallback_imp
                    
                # Replace standard
                replace_std = metadata.get('replace_standard')
                if replace_std:
                    doc.replace_standard = replace_std

                # --- Extract revision changes (hybrid engine) ---
                raw_text = parse_result.get('full_text', parse_result.get('raw_text', ''))
                revision_result = extract_revision_changes(raw_text)
                doc.revision_changes = revision_result.get('changes') or []
                doc.extraction_source = revision_result.get('source', 'failed')
                # Use revision extractor's replaced_standard if metadata didn't find one
                if not replace_std and revision_result.get('replaced_standard'):
                    doc.replace_standard = revision_result['replaced_standard']

                doc.status = 'success'
                doc.error_reason = None
                
            except Exception as parse_error:
                # Log parsing failure but save document using legacy info
                doc.status = 'failed'
                doc.error_reason = traceback.format_exc()[:2000]
                
                # Reset to fallback values on error
                doc.standard_code = std_id or ""
                doc.publish_date = fallback_pub
                doc.implement_date = fallback_imp
                
            if is_new:
                docs_to_create.append(doc)
            else:
                docs_to_update.append(doc)
                
        # Perform Database Sync Transactions
        try:
            with transaction.atomic():
                # 1. Bulk Create
                if docs_to_create:
                    StandardDocument.objects.bulk_create(docs_to_create)
                    
                # 2. Bulk Update
                if docs_to_update:
                    fields_to_update = [
                    'source_file', 'standard_code', 'year_code', 'cn_name', 'en_name',
                    'ics_code', 'ccs_code', 'status', 'error_reason',
                    'publish_date', 'implement_date', 'replace_standard',
                    'revision_changes', 'extraction_source'
                ]
                    StandardDocument.objects.bulk_update(docs_to_update, fields_to_update)
                    
            logger.info(f"Successfully sync batch: created={len(docs_to_create)}, updated={len(docs_to_update)}")
        except Exception as db_sync_err:
            logger.error("Failed to commit database batch sync", exc_info=True)
            # Fallback to individual saves
            for doc in (docs_to_create + docs_to_update):
                try:
                    doc.save()
                except Exception as se:
                    logger.error(f"Fallback save failed for source_base_id {doc.source_base_id}: {se}")
