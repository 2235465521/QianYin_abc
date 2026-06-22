"""
Django management command for monitoring a directory and automatically processing documents.
Uses Watchdog library to detect new PDF and DOCX files and triggers async parsing tasks.

Usage:
    python manage.py watch_daemon
    python manage.py watch_daemon --watch-dir /path/to/documents
    python manage.py watch_daemon --watch-dir /path/to/documents --extensions pdf,docx
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, List

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    raise CommandError(
        "watchdog library is required. Install it with: pip install watchdog"
    )

from standards_parser.models import StandardDocument
from standards_parser.tasks import process_standard_document

logger = logging.getLogger(__name__)


class DocumentEventHandler(FileSystemEventHandler):
    """
    File system event handler for monitoring document creation.
    
    Detects when new PDF or DOCX files are created in the monitored directory,
    creates database records, and triggers async parsing tasks.
    """
    
    def __init__(self, command_instance, allowed_extensions: List[str]):
        """
        Initialize the event handler with cache batch configurations.
        
        Args:
            command_instance: The management command instance (for output)
            allowed_extensions: List of allowed file extensions (lowercase, without dot)
        """
        super().__init__()
        self.command = command_instance
        self.allowed_extensions = [ext.lower() for ext in allowed_extensions]
        
        # Batch write configurations
        self.batch_limit = getattr(settings, 'BATCH_WRITE_LIMIT', 10)
        self.batch_timeout = getattr(settings, 'BATCH_WRITE_TIMEOUT', 5)
        
        # Memory queue
        self.pending_files = []
        self.last_flush_time = time.time()
        
        logger.info(
            f"DocumentEventHandler initialized with extensions: {self.allowed_extensions}, "
            f"limit={self.batch_limit}, timeout={self.batch_timeout}s"
        )
    
    def on_created(self, event) -> None:
        """
        Handle file creation events.
        
        When a new file is created in the monitored directory:
        1. Check if it's a supported file type
        2. Put it in the queue instead of processing immediately
        3. Flush queue if limit is reached
        
        Args:
            event: watchdog FileCreatedEvent
        """
        # Ignore directory creation
        if event.is_directory:
            return
        
        file_path = event.src_path
        file_name = os.path.basename(file_path)
        file_ext = Path(file_path).suffix.lower().lstrip('.')
        
        # Check if file extension is allowed
        if file_ext not in self.allowed_extensions:
            logger.debug(
                f"Ignoring file with unsupported extension: {file_name} (.{file_ext})"
            )
            return
        
        # Log detection
        self.command.stdout.write(
            self.command.style.SUCCESS(
                f"✓ Detected new document: {file_name}"
            )
        )
        logger.info(f"New document detected: {file_path}")
        
        # Add small delay to ensure file is fully written
        time.sleep(1)
        
        # Verify file still exists and is readable
        if not os.path.exists(file_path):
            self.command.stdout.write(
                self.command.style.WARNING(
                    f"⚠ File disappeared before processing: {file_name}"
                )
            )
            logger.warning(f"File disappeared: {file_path}")
            return
        
        if not os.path.isfile(file_path):
            self.command.stdout.write(
                self.command.style.WARNING(
                    f"⚠ Path is not a regular file: {file_name}"
                )
            )
            logger.warning(f"Path is not a file: {file_path}")
            return
        
        # Check if file is readable
        if not os.access(file_path, os.R_OK):
            self.command.stdout.write(
                self.command.style.WARNING(
                    f"⚠ File is not readable: {file_name}"
                )
            )
            logger.warning(f"File not readable: {file_path}")
            return
        
        # Get file size
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            self.command.stdout.write(
                self.command.style.WARNING(
                    f"⚠ File is empty: {file_name}"
                )
            )
            logger.warning(f"File is empty: {file_path}")
            return
        
        logger.info(
            f"File validation passed: {file_name} ({file_size} bytes)"
        )
        
        # Cache file path and trigger limit check
        self.pending_files.append({
            'file_path': file_path,
            'file_name': file_name
        })
        
        self.command.stdout.write(
            self.command.style.WARNING(
                f"  → Added to queue (Current size: {len(self.pending_files)}/{self.batch_limit})"
            )
        )
        
        if len(self.pending_files) >= self.batch_limit:
            logger.info(f"Batch limit reached ({len(self.pending_files)}), flushing...")
            self.flush_pending_files()
            
    def flush_pending_files(self) -> None:
        """
        Flush the pending queue and trigger the batch processing task.
        """
        if not self.pending_files:
            return
            
        files_to_process = list(self.pending_files)
        self.pending_files.clear()
        self.last_flush_time = time.time()
        
        self.command.stdout.write(
            self.command.style.SUCCESS(
                f"🚀 Flushing {len(files_to_process)} documents for batch processing..."
            )
        )
        logger.info(f"Flushing batch of {len(files_to_process)} files.")
        
        from standards_parser.tasks import process_standard_documents_batch
        
        try:
            task = process_standard_documents_batch.delay(files_to_process)
            logger.info(f"Batch task queued: task_id={task.id}, size={len(files_to_process)}")
            self.command.stdout.write(
                self.command.style.SUCCESS(
                    f"  → Batch parsing task queued (Task ID: {task.id})"
                )
            )
        except Exception as task_error:
            error_msg = f"Failed to queue batch Celery task: {str(task_error)}"
            logger.error(error_msg, exc_info=True)
            self.command.stdout.write(
                self.command.style.ERROR(f"  ✗ {error_msg}")
            )
            
    def check_timeout_and_flush(self) -> None:
        """
        Check if pending queue has exceeded the timeout and flush if necessary.
        """
        if not self.pending_files:
            return
            
        elapsed = time.time() - self.last_flush_time
        if elapsed >= self.batch_timeout:
            logger.info(f"Batch timeout reached ({elapsed:.1f}s), flushing...")
            self.command.stdout.write(
                self.command.style.WARNING(
                    f"⚠ Timeout reached ({elapsed:.1f}s), forcing flush..."
                )
            )
            self.flush_pending_files()


class Command(BaseCommand):
    """
    Django management command to run the document watching daemon.
    
    Monitors a specified directory for new PDF and DOCX files,
    creates database records, and triggers async parsing tasks.
    """
    
    help = (
        'Watch a directory for new standard documents (PDF/DOCX) '
        'and automatically trigger parsing tasks'
    )
    
    def add_arguments(self, parser) -> None:
        """
        Add command-line arguments.
        
        Args:
            parser: Django ArgumentParser instance
        """
        parser.add_argument(
            '--watch-dir',
            type=str,
            default=None,
            help=(
                'Directory to monitor for new documents. '
                'Default: WATCH_FOLDER from Django settings'
            ),
        )
        
        parser.add_argument(
            '--extensions',
            type=str,
            default='pdf,docx',
            help=(
                'Comma-separated list of file extensions to monitor '
                '(default: pdf,docx)'
            ),
        )
        
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=1,
            help=(
                'Poll interval for the file system observer in seconds '
                '(default: 1)'
            ),
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose logging output',
        )
    
    def handle(self, *args, **options) -> None:
        """
        Main command handler.
        
        Args:
            *args: Positional arguments (unused)
            **options: Command options from argparse
        """
        # Get configuration
        watch_dir = options.get('watch_dir') or getattr(
            settings, 'WATCH_FOLDER', None
        )
        
        if not watch_dir:
            raise CommandError(
                "No watch directory specified. Use --watch-dir argument "
                "or set WATCH_FOLDER in Django settings"
            )
        
        # Parse extensions
        extensions_str = options.get('extensions', 'pdf,docx')
        allowed_extensions = [
            ext.strip().lower() for ext in extensions_str.split(',')
        ]
        
        poll_interval = options.get('poll_interval', 1)
        verbose = options.get('verbose', False)
        
        # Setup logging
        if verbose:
            logging.getLogger('standards_parser').setLevel(logging.DEBUG)
            logging.getLogger('watchdog').setLevel(logging.DEBUG)
        else:
            logging.getLogger('standards_parser').setLevel(logging.INFO)
            logging.getLogger('watchdog').setLevel(logging.WARNING)
        
        # Validate and create watch directory
        watch_path = Path(watch_dir)
        try:
            watch_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Watch directory ready: {watch_path.absolute()}")
        except Exception as e:
            raise CommandError(
                f"Failed to create/access watch directory '{watch_dir}': {str(e)}"
            )
        
        # Validate file extensions
        if not allowed_extensions:
            raise CommandError("At least one file extension must be specified")
        
        # Display startup information
        self.stdout.write(
            self.style.SUCCESS(
                "=" * 70
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "📂 Document Watching Daemon Started"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "=" * 70
            )
        )
        self.stdout.write(f"Watch directory: {watch_path.absolute()}")
        self.stdout.write(f"File extensions: {', '.join(allowed_extensions)}")
        self.stdout.write(f"Poll interval: {poll_interval}s")
        self.stdout.write(
            "Status: Listening for new files... (Press Ctrl+C to stop)"
        )
        self.stdout.write(
            self.style.SUCCESS(
                "=" * 70
            )
        )
        
        logger.info(
            f"Starting document watching daemon: "
            f"dir={watch_path.absolute()}, "
            f"extensions={allowed_extensions}, "
            f"poll_interval={poll_interval}s"
        )
        
        # Create event handler and observer
        event_handler = DocumentEventHandler(self, allowed_extensions)
        observer = Observer()
        observer.schedule(
            event_handler,
            str(watch_path),
            recursive=False
        )
        
        # Start observer
        observer.start()
        logger.info("File system observer started")
        
        try:
            # Keep the daemon running
            while True:
                time.sleep(1)
                event_handler.check_timeout_and_flush()
        
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING(
                    "\n🛑 Shutdown signal received (Ctrl+C)"
                )
            )
            logger.info("Shutdown signal received")
        
        except Exception as e:
            error_msg = f"Unexpected error in watch daemon: {str(e)}"
            self.stdout.write(self.style.ERROR(f"✗ {error_msg}"))
            logger.error(error_msg, exc_info=True)
        
        finally:
            # Cleanup
            observer.stop()
            observer.join()
            
            self.stdout.write(
                self.style.SUCCESS(
                    "✓ Document watching daemon stopped cleanly"
                )
            )
            logger.info("Document watching daemon stopped")
