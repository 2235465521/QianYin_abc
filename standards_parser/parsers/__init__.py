# Parser package for standards document parsing
from .pdf_parser import PDFParser
from .docx_parser import DocxParser
from .base import BaseStandardParser

__all__ = ['PDFParser', 'DocxParser', 'BaseStandardParser', 'get_parser']


def get_parser(file_path: str):
    """
    Factory function to get the appropriate parser for a file.
    
    Args:
        file_path (str): Path to the file
    
    Returns:
        BaseStandardParser: Parser instance for the given file type
    
    Raises:
        ValueError: If file type is not supported
    """
    file_ext = file_path.lower().split('.')[-1] if '.' in file_path else ''
    
    parsers = {
        'pdf': PDFParser,
        'docx': DocxParser,
        'doc': DocxParser,  # Alias for Word documents
    }
    
    if file_ext not in parsers:
        raise ValueError(
            f"Unsupported file type: .{file_ext}. "
            f"Supported formats: {', '.join(parsers.keys())}"
        )
    
    parser_class = parsers[file_ext]
    return parser_class(file_path)
