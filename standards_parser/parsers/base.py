"""
Base parser class for standard documents.
Defines the abstract interface that all specific parsers must implement.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Any

from . import regex_rules

logger = logging.getLogger(__name__)


class BaseStandardParser(ABC):
    """
    Abstract base class for standard document parsers.
    
    Defines the interface and common functionality for parsing different document formats
    (PDF, DOCX, etc.). Subclasses must implement the extract_text() method.
    
    Attributes:
        file_path (Path): Path to the document file to be parsed
        logger: Logger instance for this parser
    """
    
    def __init__(self, file_path: str) -> None:
        """
        Initialize the parser with a document file path.
        
        Args:
            file_path: Absolute or relative path to the document file.
        
        Raises:
            FileNotFoundError: If the specified file does not exist.
            ValueError: If the file path is empty or invalid.
        """
        if not file_path:
            raise ValueError("file_path cannot be empty")
        
        self.file_path: Path = Path(file_path)
        
        if not self.file_path.exists():
            raise FileNotFoundError(f"Document file not found: {file_path}")
        
        if not self.file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        self.logger = logger
    
    @abstractmethod
    def extract_text(self) -> str:
        """
        Extract raw text content from the document.
        
        This method must be implemented by subclasses to handle different file formats.
        
        Returns:
            Raw text content extracted from the document.
        
        Raises:
            NotImplementedError: Always. Subclasses must override this method.
            Exception: Any parsing-related errors specific to the document format.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement extract_text() method"
        )
    
    def parse_metadata(self, text: str) -> Dict[str, Optional[Any]]:
        """
        Parse and extract standard metadata from document text.
        
        Utilizes regex patterns from regex_rules module to extract structured information
        about the standard including code, classification, dates, and replacement info.
        
        Args:
            text: Raw text content from the document to parse.
        
        Returns:
            Dictionary containing extracted metadata with the following keys:
                - standard_prefix (str): Standard type prefix (e.g., 'GB/T', 'QB')
                - standard_code (str): Standard number (e.g., '1.1')
                - standard_year (Optional[str]): Year code (e.g., '2020')
                - full_standard_number (str): Complete standard number (e.g., 'GB/T 1.1-2020')
                - ics_code (Optional[str]): ICS classification number
                - ccs_code (Optional[str]): CCS classification number
                - publish_date (Optional[str]): Publication date in YYYY-MM-DD format
                - implement_date (Optional[str]): Implementation date in YYYY-MM-DD format
                - replace_standard (Optional[str]): Previous standard being replaced
        """
        # Clean the text before processing
        cleaned_text = regex_rules.clean_text(text)
        
        # Extract standard code components
        standard_info = regex_rules.extract_standard_code(cleaned_text)
        
        if standard_info:
            prefix, code, year = standard_info
            full_standard = f"{prefix} {code}"
            if year:
                full_standard += f"-{year}"
        else:
            prefix = None
            code = None
            year = None
            full_standard = None
        
        # Extract classification codes
        ics_code = regex_rules.extract_ics_code(cleaned_text)
        ccs_code = regex_rules.extract_ccs_code(cleaned_text)
        
        # Extract dates
        publish_date = regex_rules.extract_publish_date(cleaned_text)
        implement_date = regex_rules.extract_implement_date(cleaned_text)
        
        # Extract replacement standard
        replace_standard = regex_rules.extract_replace_standard(cleaned_text)
        
        # Build metadata dictionary
        metadata: Dict[str, Optional[Any]] = {
            'standard_prefix': prefix,
            'standard_code': code,
            'standard_year': year,
            'full_standard_number': full_standard,
            'ics_code': ics_code,
            'ccs_code': ccs_code,
            'publish_date': publish_date,
            'implement_date': implement_date,
            'replace_standard': replace_standard,
        }
        
        self.logger.debug(f"Extracted metadata: {metadata}")
        
        return metadata
    
    def parse(self) -> Dict[str, Optional[Any]]:
        """
        Main parsing method that orchestrates the complete parsing workflow.
        
        Sequence:
            1. Extract raw text from document
            2. Parse metadata from extracted text
            3. Return parsed results
        
        Returns:
            Dictionary containing:
                - metadata: Extracted standard metadata
                - raw_text: Cleaned text content from document
                - file_info: File information
        
        Raises:
            Exception: If extraction or parsing fails.
        """
        try:
            self.logger.info(f"Starting to parse document: {self.file_path}")
            
            # Extract raw text
            raw_text = self.extract_text()
            if not raw_text:
                raise ValueError("No text content extracted from document")
            
            # Parse metadata
            metadata = self.parse_metadata(raw_text)
            
            # Validate extraction
            if not metadata.get('full_standard_number'):
                self.logger.warning(f"Could not extract standard number from: {self.file_path}")
            
            result = {
                'metadata': metadata,
                'raw_text': raw_text[:5000],   # Store first 5000 chars (for storage/preview)
                'full_text': raw_text,          # Full text for revision extraction (not truncated)
                'file_info': {
                    'file_path': str(self.file_path),
                    'file_name': self.file_path.name,
                    'file_size': self.file_path.stat().st_size,
                },
            }
            
            self.logger.info(f"Successfully parsed document: {self.file_path}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error parsing document {self.file_path}: {str(e)}", exc_info=True)
            raise
    
    def validate_metadata(self, metadata: Dict[str, Optional[Any]]) -> bool:
        """
        Validate extracted metadata to ensure minimum required fields are present.
        
        Args:
            metadata: Dictionary of extracted metadata from parse_metadata().
        
        Returns:
            True if metadata is valid, False otherwise.
        """
        required_fields = ['full_standard_number', 'standard_prefix', 'standard_code']
        
        for field in required_fields:
            if not metadata.get(field):
                self.logger.warning(f"Missing required field in metadata: {field}")
                return False
        
        return True

