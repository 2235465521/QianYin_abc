"""
Celery async tasks for standards_parser application.
Orchestrates document parsing workflow and database updates.
"""

import logging
import traceback
from datetime import datetime
from typing import Dict, Optional, Any

from celery import shared_task
from django.db import transaction

from .models import StandardDocument
from .parsers import get_parser
from .parsers.revision_extractor import extract_revision_changes

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def process_standard_document(self, file_path: str, doc_id: int) -> Dict[str, Any]:
    """
    Async task to parse a standard document and update database records.
    
    This task orchestrates the complete parsing workflow:
    1. Retrieve the StandardDocument record from database
    2. Instantiate the appropriate parser based on file extension
    3. Extract text and parse metadata from the document
    4. Update the database record with parsed metadata
    5. Handle errors and update status accordingly
    
    Args:
        file_path (str): Absolute path to the document file (PDF or DOCX)
        doc_id (int): Primary key of the StandardDocument record to update
    
    Returns:
        Dict containing task result:
            - status: 'success' or 'failed'
            - doc_id: Document ID
            - standard_number: Extracted standard number (if successful)
            - error: Error message (if failed)
            - task_id: Celery task ID
    
    Raises:
        Exception: Will be caught and logged, not raised
    """
    task_id = self.request.id
    
    try:
        logger.info(
            f"[Task {task_id}] Starting to process document: {file_path} "
            f"(doc_id: {doc_id})"
        )
        
        # ===================================================================
        # Step 1: Retrieve the StandardDocument record
        # ===================================================================
        try:
            standard_doc = StandardDocument.objects.get(id=doc_id)
        except StandardDocument.DoesNotExist:
            error_msg = f"StandardDocument with id={doc_id} not found"
            logger.error(f"[Task {task_id}] {error_msg}")
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'error': error_msg,
                'task_id': task_id,
            }
        
        # Update status to "processing"
        standard_doc.status = 'processing'
        standard_doc.save(update_fields=['status'])
        logger.info(f"[Task {task_id}] Updated document status to: processing")
        
        # ===================================================================
        # Step 2: Validate file and instantiate parser
        # ===================================================================
        try:
            parser = get_parser(file_path)
            logger.info(
                f"[Task {task_id}] Parser instantiated: {parser.__class__.__name__}"
            )
        except FileNotFoundError as e:
            error_msg = f"Document file not found: {file_path}"
            logger.error(f"[Task {task_id}] {error_msg}")
            _update_document_failed(standard_doc, error_msg, task_id)
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'error': error_msg,
                'task_id': task_id,
            }
        except ImportError as e:
            error_msg = f"Missing required library: {str(e)}"
            logger.error(f"[Task {task_id}] {error_msg}")
            _update_document_failed(standard_doc, error_msg, task_id)
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'error': error_msg,
                'task_id': task_id,
            }
        except ValueError as e:
            error_msg = f"Unsupported file format: {str(e)}"
            logger.error(f"[Task {task_id}] {error_msg}")
            _update_document_failed(standard_doc, error_msg, task_id)
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'error': error_msg,
                'task_id': task_id,
            }
        
        # ===================================================================
        # Step 3: Extract text and parse metadata
        # ===================================================================
        try:
            logger.info(f"[Task {task_id}] Extracting text from document...")
            parse_result = parser.parse()
            
            metadata = parse_result.get('metadata', {})
            logger.info(
                f"[Task {task_id}] Successfully parsed document. "
                f"Extracted standard: {metadata.get('full_standard_number', 'N/A')}"
            )
        
        except ValueError as e:
            # File is damaged or has no readable content
            error_msg = f"No readable content in document: {str(e)}"
            logger.warning(f"[Task {task_id}] {error_msg}")
            _update_document_failed(standard_doc, error_msg, task_id)
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'error': error_msg,
                'task_id': task_id,
            }
        
        except Exception as e:
            # Corrupted file or parsing error
            error_msg = f"Document parsing failed: {str(e)}"
            error_traceback = traceback.format_exc()
            logger.error(
                f"[Task {task_id}] {error_msg}\n{error_traceback}"
            )
            _update_document_failed(standard_doc, error_traceback, task_id)
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'error': error_msg,
                'task_id': task_id,
            }
        
        # ===================================================================
        # Step 4: Update database with parsed metadata
        # ===================================================================
        try:
            with transaction.atomic():
                # Extract components from metadata
                standard_prefix = metadata.get('standard_prefix')
                standard_code = metadata.get('standard_code')
                standard_year = metadata.get('standard_year')
                full_standard_number = metadata.get('full_standard_number')
                
                # Build standard code with prefix and number
                if standard_prefix and standard_code:
                    standard_code_str = f"{standard_prefix} {standard_code}"
                else:
                    standard_code_str = full_standard_number or ""
                
                # Parse dates (YYYY-MM-DD format)
                publish_date_str = metadata.get('publish_date')
                implement_date_str = metadata.get('implement_date')
                
                publish_date = None
                if publish_date_str:
                    try:
                        publish_date = datetime.strptime(
                            publish_date_str, '%Y-%m-%d'
                        ).date()
                    except (ValueError, TypeError):
                        logger.warning(
                            f"[Task {task_id}] Could not parse publish_date: "
                            f"{publish_date_str}"
                        )
                
                implement_date = None
                if implement_date_str:
                    try:
                        implement_date = datetime.strptime(
                            implement_date_str, '%Y-%m-%d'
                        ).date()
                    except (ValueError, TypeError):
                        logger.warning(
                            f"[Task {task_id}] Could not parse implement_date: "
                            f"{implement_date_str}"
                        )
                
                # Update StandardDocument record
                standard_doc.standard_code = standard_code_str
                standard_doc.year_code = standard_year or ""
                standard_doc.ics_code = metadata.get('ics_code') or ""
                standard_doc.ccs_code = metadata.get('ccs_code') or ""
                standard_doc.status = 'success'
                standard_doc.error_reason = None
                
                if publish_date:
                    standard_doc.publish_date = publish_date
                if implement_date:
                    standard_doc.implement_date = implement_date
                
                replace_standard = metadata.get('replace_standard')
                if replace_standard:
                    standard_doc.replace_standard = replace_standard
                
                # --- Extract revision changes (hybrid: regex + LLM fallback) ---
                raw_text_full = parse_result.get('full_text', parse_result.get('raw_text', ''))
                revision_result = extract_revision_changes(raw_text_full)
                standard_doc.revision_changes = revision_result.get('changes') or []
                standard_doc.extraction_source = revision_result.get('source', 'failed')
                # Override replace_standard if revision extractor found a better value
                if not replace_standard and revision_result.get('replaced_standard'):
                    standard_doc.replace_standard = revision_result['replaced_standard']
                logger.info(
                    f"[Task {task_id}] Revision changes extracted: "
                    f"{len(standard_doc.revision_changes)} items "
                    f"via {standard_doc.extraction_source}"
                )
                
                standard_doc.save()
                
                logger.info(
                    f"[Task {task_id}] Successfully updated database record. "
                    f"Standard: {standard_code_str}, Year: {standard_year}"
                )
        
        except Exception as e:
            error_msg = f"Database update failed: {str(e)}"
            error_traceback = traceback.format_exc()
            logger.error(
                f"[Task {task_id}] {error_msg}\n{error_traceback}"
            )
            _update_document_failed(standard_doc, error_traceback, task_id)
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'error': error_msg,
                'task_id': task_id,
            }
        
        # ===================================================================
        # Success
        # ===================================================================
        return {
            'status': 'success',
            'doc_id': doc_id,
            'standard_number': full_standard_number,
            'task_id': task_id,
        }
    
    except Exception as e:
        # Catch-all for unexpected errors
        error_msg = f"Unexpected error in process_standard_document: {str(e)}"
        error_traceback = traceback.format_exc()
        logger.error(f"[Task {task_id}] {error_msg}\n{error_traceback}")
        
        try:
            standard_doc = StandardDocument.objects.get(id=doc_id)
            _update_document_failed(standard_doc, error_traceback, task_id)
        except:
            pass
        
        return {
            'status': 'failed',
            'doc_id': doc_id,
            'error': error_msg,
            'task_id': task_id,
        }


def _update_document_failed(
    standard_doc: StandardDocument,
    error_reason: str,
    task_id: str
) -> None:
    """
    Helper function to update document status to failed.
    
    Args:
        standard_doc: StandardDocument instance to update
        error_reason: Error message or traceback
        task_id: Celery task ID for logging
    """
    try:
        standard_doc.status = 'failed'
        standard_doc.error_reason = error_reason[:2000]  # Truncate to 2000 chars
        standard_doc.save(update_fields=['status', 'error_reason'])
        logger.info(f"[Task {task_id}] Document marked as failed")
    except Exception as e:
        logger.error(
            f"[Task {task_id}] Failed to update document status: {str(e)}"
        )


@shared_task(bind=True)
def process_standard_documents_batch(self, files_info: list) -> dict:
    """
    批量解析标准文档并在处理完后统一更新到数据库中。
    
    Args:
        files_info: 包含文件路径信息的字典列表，例如：
                    [{'file_path': '/path/to/file1.pdf', 'file_name': 'file1.pdf'}, ...]
                    
    Returns:
        Dict: 包含处理统计信息的字典
    """
    task_id = self.request.id
    logger.info(f"[Batch Task {task_id}] Starting to process {len(files_info)} documents.")
    
    # 1. 批量在数据库中创建记录，并设定状态为 'processing'
    db_docs = []
    import uuid
    from django.utils import timezone
    current_date = timezone.now().date()
    temp_codes = []
    for info in files_info:
        temp_code = f"TEMP_{uuid.uuid4().hex[:30]}"
        temp_codes.append(temp_code)
        db_docs.append(StandardDocument(
            source_file=info['file_path'],
            status='processing',
            standard_code=temp_code,
            year_code="",
            publish_date=current_date,
            implement_date=current_date,
        ))
        
    try:
        # 批量创建
        StandardDocument.objects.bulk_create(db_docs)
        # 重新查出刚创建的对象以回填自增 ID 保证跨驱动/平台兼容性
        fresh_docs = {
            doc.standard_code: doc 
            for doc in StandardDocument.objects.filter(standard_code__in=temp_codes)
        }
        
        created_docs = []
        for doc in db_docs:
            db_doc = fresh_docs.get(doc.standard_code)
            if db_doc:
                doc.id = db_doc.id
                created_docs.append(doc)
                
        logger.info(f"[Batch Task {task_id}] Successfully bulk created {len(created_docs)} records and retrieved IDs.")
    except Exception as e:
        logger.error(f"[Batch Task {task_id}] Bulk create failed: {str(e)}")
        return {
            'status': 'failed',
            'error': f"Bulk create failed: {str(e)}"
        }
    
    # 建立映射以根据文件路径找到对应的数据库模型对象
    doc_map = {}
    for info, doc in zip(files_info, created_docs):
        doc_map[info['file_path']] = doc
        
    success_count = 0
    failed_count = 0
    
    # 2. 循环解析文件，但不调用单条记录的 save() 方法，而是把数据暂存在内存对象中
    for file_path, doc in doc_map.items():
        logger.info(f"[Batch Task {task_id}] Processing: {file_path} (ID: {doc.id})")
        
        try:
            parser = get_parser(file_path)
            parse_result = parser.parse()
            metadata = parse_result.get('metadata', {})
            
            # 解析标准编号
            standard_prefix = metadata.get('standard_prefix')
            standard_code = metadata.get('standard_code')
            standard_year = metadata.get('standard_year')
            full_standard_number = metadata.get('full_standard_number')
            
            if standard_prefix and standard_code:
                standard_code_str = f"{standard_prefix} {standard_code}"
            else:
                standard_code_str = full_standard_number or ""
                
            # 解析日期
            publish_date_str = metadata.get('publish_date')
            implement_date_str = metadata.get('implement_date')
            
            publish_date = None
            if publish_date_str:
                try:
                    publish_date = datetime.strptime(publish_date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    logger.warning(f"[Batch Task {task_id}] Could not parse publish_date: {publish_date_str}")
                    
            implement_date = None
            if implement_date_str:
                try:
                    implement_date = datetime.strptime(implement_date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    logger.warning(f"[Batch Task {task_id}] Could not parse implement_date: {implement_date_str}")
            
            # 更新实例的字段
            doc.standard_code = standard_code_str
            doc.year_code = standard_year or ""
            doc.ics_code = metadata.get('ics_code') or ""
            doc.ccs_code = metadata.get('ccs_code') or ""
            doc.status = 'success'
            doc.error_reason = None
            
            if publish_date:
                doc.publish_date = publish_date
            if implement_date:
                doc.implement_date = implement_date
                
            replace_standard = metadata.get('replace_standard')
            if replace_standard:
                doc.replace_standard = replace_standard
            
            # --- Extract revision changes (hybrid: regex + LLM fallback) ---
            raw_text_full = parse_result.get('full_text', parse_result.get('raw_text', ''))
            revision_result = extract_revision_changes(raw_text_full)
            doc.revision_changes = revision_result.get('changes') or []
            doc.extraction_source = revision_result.get('source', 'failed')
            if not replace_standard and revision_result.get('replaced_standard'):
                doc.replace_standard = revision_result['replaced_standard']
            logger.info(
                f"[Batch Task {task_id}] {file_path}: "
                f"{len(doc.revision_changes)} revision items "
                f"via {doc.extraction_source}"
            )
                
            success_count += 1
            
        except Exception as e:
            failed_count += 1
            error_traceback = traceback.format_exc()
            logger.warning(f"[Batch Task {task_id}] Failed parsing {file_path}: {str(e)}")
            doc.status = 'failed'
            doc.error_reason = error_traceback[:2000]
            
    # 3. 统一 bulk_update 一次性写入数据库！
    try:
        fields_to_update = [
            'standard_code', 'year_code', 'ics_code', 'ccs_code',
            'status', 'error_reason', 'publish_date', 'implement_date',
            'replace_standard', 'revision_changes', 'extraction_source'
        ]
        StandardDocument.objects.bulk_update(created_docs, fields_to_update)
        logger.info(
            f"[Batch Task {task_id}] Successfully bulk updated {len(created_docs)} records. "
            f"Success: {success_count}, Failed: {failed_count}"
        )
    except Exception as e:
        logger.error(f"[Batch Task {task_id}] Bulk update failed: {str(e)}")
        # 降级：如果批量更新报错，尝试逐个保存以保存成功解析的部分
        logger.info(f"[Batch Task {task_id}] Falling back to individual saves.")
        for doc in created_docs:
            try:
                doc.save()
            except Exception as se:
                logger.error(f"[Batch Task {task_id}] Save fallback failed for ID {doc.id}: {str(se)}")
                
    return {
        'status': 'success',
        'processed': len(files_info),
        'success_count': success_count,
        'failed_count': failed_count
    }


