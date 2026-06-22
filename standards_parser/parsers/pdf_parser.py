"""
PDF document parser using pdfplumber library.
Extracts text and structured data from PDF files.
"""

import os
import logging
from typing import Optional, Dict, Any

from .base import BaseStandardParser

logger = logging.getLogger(__name__)


class PDFParser(BaseStandardParser):
    """
    PDF parser implementation using pdfplumber.
    
    Handles text extraction from PDF documents and delegates metadata
    parsing to the parent class.
    """
    
    def __init__(self, file_path: str) -> None:
        """
        Initialize PDF parser.
        
        Args:
            file_path: Path to the PDF file.
        
        Raises:
            FileNotFoundError: If the PDF file does not exist.
            ImportError: If pdfplumber is not installed.
        """
        super().__init__(file_path)
        
        try:
            import pdfplumber
            self.pdfplumber = pdfplumber
        except ImportError:
            raise ImportError(
                "pdfplumber is required for PDF parsing. "
                "Install it with: pip install pdfplumber"
            )
    
    def extract_text(self) -> str:
        """
        Extract text content from PDF file.
        
        Reads all pages from the PDF and concatenates their text content.
        Handles PDFs with images-only pages gracefully.
        
        Returns:
            Concatenated text from all pages.
        
        Raises:
            Exception: If PDF is corrupted or cannot be read.
        """
        try:
            self.logger.info(f"Opening PDF file: {self.file_path}")
            
            full_text = ""
            
            with self.pdfplumber.open(str(self.file_path)) as pdf:
                total_pages = len(pdf.pages)
                self.logger.info(f"PDF has {total_pages} pages")
                
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        text = page.extract_text()
                        if text:
                            full_text += f"\n--- Page {page_num} ---\n" + text
                            self.logger.debug(f"Extracted {len(text)} chars from page {page_num}")
                        else:
                            self.logger.debug(f"Page {page_num} has no extractable text")
                    except Exception as e:
                        self.logger.warning(f"Error extracting text from page {page_num}: {str(e)}")
                        continue
            
            if not full_text.strip():
                raise ValueError("No text content could be extracted from PDF")
            
            self.logger.info(f"Successfully extracted {len(full_text)} characters from PDF")
            return full_text
            
        except Exception as e:
            self.logger.error(f"PDF extraction error for {self.file_path}: {str(e)}", exc_info=True)
            raise

    def parse(self) -> Dict[str, Optional[Any]]:
        """
        Orchestrate PDF parsing. 
        First, try normal text extraction and regex matching.
        If it yields no standard code or fails, fall back to OCR.
        """
        normal_result = None
        normal_exception = None
        try:
            # 1. 尝试常规文本提取解析
            normal_result = super().parse()
            metadata = normal_result.get('metadata', {})
            
            # 如果成功匹配到了完整的标准号，说明常规解析成功
            if metadata.get('full_standard_number') and metadata.get('standard_code'):
                return normal_result
            else:
                self.logger.warning(
                    f"Normal PDF parsing completed but failed to extract standard code "
                    f"from '{self.file_path}'. Retrying with OCR..."
                )
        except Exception as e:
            normal_exception = e
            self.logger.warning(
                f"Normal PDF parsing failed for '{self.file_path}' due to: {e}. "
                f"Retrying with OCR..."
            )
            
        # 2. 回退到 OCR 识别解析
        try:
            return self.parse_with_ocr()
        except Exception as ocr_err:
            self.logger.warning(
                f"OCR parsing failed for '{self.file_path}' due to: {ocr_err}. "
                f"Falling back to normal parsing result if available."
            )
            if normal_result:
                return normal_result
            if normal_exception:
                raise normal_exception
            raise ocr_err

    def parse_with_ocr(self) -> Dict[str, Optional[Any]]:
        """
        Render PDF pages to images and extract text using Tesseract OCR,
        then parse standard metadata.
        """
        self.logger.info(f"Starting OCR fallback parsing for: {self.file_path}")
        
        # 检查是否配置了 TESSERACT_CMD 路径
        tesseract_cmd = os.environ.get('TESSERACT_CMD')
        if tesseract_cmd:
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            except ImportError:
                pass
                
        try:
            import pytesseract
        except ImportError:
            raise ImportError(
                "pytesseract library is required for OCR parsing fallback. "
                "Install it with: pip install pytesseract"
            )
            
        ocr_text = ""
        try:
            with self.pdfplumber.open(str(self.file_path)) as pdf:
                total_pages = len(pdf.pages)
                # 仅 OCR 前两页，元数据（标准号、日期等）都在这里，以提升处理性能
                pages_to_scan = min(total_pages, 2)
                
                self.logger.info(f"[OCR] Rendering first {pages_to_scan} page(s) of PDF to images...")
                for page_num in range(pages_to_scan):
                    page = pdf.pages[page_num]
                    # 将页面直接在内存中渲染成 PNG 图片，150dpi 在速度和识别率之间非常均衡
                    im = page.to_image(resolution=150)
                    pil_img = im.original
                    
                    self.logger.info(f"[OCR] Running Tesseract OCR on page {page_num + 1}...")
                    # 识别中英文
                    page_text = pytesseract.image_to_string(pil_img, lang='chi_sim+eng')
                    
                    if page_text:
                        ocr_text += f"\n--- OCR Page {page_num + 1} ---\n" + page_text
                        self.logger.info(f"[OCR] Extracted {len(page_text)} chars from page {page_num + 1}")
                    else:
                        self.logger.warning(f"[OCR] Extracted no text from page {page_num + 1}")
                        
        except Exception as e:
            err_msg = str(e)
            if 'chi_sim' in err_msg:
                friendly_tips = (
                    "\n======================================================================\n"
                    "[OCR ERROR] Tesseract OCR 缺少简体中文包 'chi_sim.traineddata'。\n"
                    "请前往 Tesseract 语言库 (https://github.com/tesseract-ocr/tessdata) 下载它，\n"
                    "并将其放入本地 Tesseract-OCR 的 'tessdata' 目录下，然后再重新运行。\n"
                    "======================================================================\n"
                )
                self.logger.error(friendly_tips)
                raise ValueError(f"OCR failed: Missing 'chi_sim' language pack. Details: {err_msg}")
                
            self.logger.error(f"OCR text extraction failed: {e}", exc_info=True)
            raise ValueError(f"OCR text extraction failed: {e}")
            
        if not ocr_text.strip():
            raise ValueError("OCR extracted no text content from the PDF file")
            
        # 调用父类公共的 regex 规则解析器解析 OCR 文本中的元数据
        metadata = self.parse_metadata(ocr_text)
        
        result = {
            'metadata': metadata,
            'raw_text': ocr_text[:5000],  # 储存前 5000 字符
            'file_info': {
                'file_path': str(self.file_path),
                'file_name': self.file_path.name,
                'file_size': self.file_path.stat().st_size,
                'parsed_via': 'ocr'  # 标记解析类型为 OCR
            },
        }
        
        self.logger.info(f"Successfully completed OCR parsing for: {self.file_path}")
        return result


