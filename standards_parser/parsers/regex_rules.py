"""
Regular expression rules for extracting standard metadata.
Centralized management of all regex patterns for standard code parsing.
"""

import re
from typing import Optional, List, Tuple, Dict

# ============================================================================
# 标准编号相关正则表达式
# ============================================================================

# GB/T 标准编号匹配 (支持年份)
# 匹配格式: GB/T 1.1, GB/T 1.1-2020, GB 1.1-2020, QB/T 等
STANDARD_CODE_PATTERN = re.compile(
    r'(GB|GB/T|GB/Z|GB/TZ|QB|QB/T|JB|JB/T|YY|YY/T|JY|JG|LY|NY|QC|TB|HB|BB|DL|MT|SY|WH|WM|TC|EJ|SL|CJ|GA|JR|GY|SC|XB|ZB|CH|JT|YD|WJ|GM|SN|LJ|YB|HG|SH|TJ|HS|GH|BS|CS)\s*'
    r'(\d+(?:\.\d+)*)'  # 标准号主体 (如 1.1 或 1.1.1)
    r'(?:\s*[-–—]\s*(\d{4}))?',  # 可选的年份部分 (如 -2020)
    re.IGNORECASE | re.VERBOSE
)

# ICS 分类号匹配
# 国际标准分类号格式: 类.子类.子组，如 03.220.10
ICS_CODE_PATTERN = re.compile(
    r'ICS\s*[:\s：]*(\d{2}\.\d{3}(?:\.\d{2})?)',
    re.IGNORECASE
)

# CCS 分类号匹配
# 中国标准分类号格式: X00.YZ.ZZ，如 A10.10.20
CCS_CODE_PATTERN = re.compile(
    r'CCS\s*[:\s：]*([A-Z]\d{2}\.\d{2}(?:\.\d{2})?)',
    re.IGNORECASE
)

# ============================================================================
# 时间相关正则表达式
# ============================================================================

# 发布日期、实施日期匹配
# 支持 2020-01-01 或 2020/01/01 或 2020年01月01日 格式
DATE_PATTERN = re.compile(
    r'(\d{4}[-/年](?:0?[1-9]|1[0-2])[-/月](?:0?[1-9]|[12][0-9]|3[01])日?)',
    re.IGNORECASE
)

# 发布日期标签
PUBLISH_DATE_PATTERN = re.compile(
    r'(?:发布日期|发布时间|发布于)[:\s：]*(\d{4}[-/年](?:0?[1-9]|1[0-2])[-/月](?:0?[1-9]|[12][0-9]|3[01])日?)',
    re.IGNORECASE
)

# 实施日期标签
IMPLEMENT_DATE_PATTERN = re.compile(
    r'(?:实施日期|实施时间|自|自.*起)[:\s：]*(\d{4}[-/年](?:0?[1-9]|1[0-2])[-/月](?:0?[1-9]|[12][0-9]|3[01])日?)',
    re.IGNORECASE
)

# ============================================================================
# 其他元数据相关正则表达式
# ============================================================================

# 代替标准号匹配
REPLACE_STANDARD_PATTERN = re.compile(
    r'(?:代替|代替标准|替代|替代标准)[:\s：]*([A-Z].*?(?:\d{4})?)',
    re.IGNORECASE
)

# 标准名称 (中文和英文)
CN_NAME_PATTERN = re.compile(
    r'^([\u4e00-\u9fff]+(?:\s+[\u4e00-\u9fff]+)*)',
    re.MULTILINE
)

EN_NAME_PATTERN = re.compile(
    r'([A-Z][A-Za-z0-9\s\-,\'&]*(?:[A-Z][A-Za-z0-9\s\-,\'&]*)*)',
    re.MULTILINE
)


# ============================================================================
# 提取函数
# ============================================================================

def extract_standard_code(text: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """
    从文本中提取标准编号。
    
    Args:
        text: 输入文本
    
    Returns:
        返回元组 (前缀, 编号, 年份) 或 None
        例如: ('GB/T', '1.1', '2020')
    """
    match = STANDARD_CODE_PATTERN.search(text)
    if match:
        prefix = match.group(1).upper()
        code = match.group(2).strip()
        year = match.group(3) if match.group(3) else None
        return (prefix, code, year)
    return None


def extract_ics_code(text: str) -> Optional[str]:
    """
    从文本中提取 ICS 分类号。
    
    Args:
        text: 输入文本
    
    Returns:
        ICS 分类号字符串或 None，例如 '03.220.10'
    """
    match = ICS_CODE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def extract_ccs_code(text: str) -> Optional[str]:
    """
    从文本中提取 CCS 分类号。
    
    Args:
        text: 输入文本
    
    Returns:
        CCS 分类号字符串或 None，例如 'A10.10.20'
    """
    match = CCS_CODE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def extract_publish_date(text: str) -> Optional[str]:
    """
    从文本中提取发布日期。
    
    Args:
        text: 输入文本
    
    Returns:
        日期字符串或 None
    """
    match = PUBLISH_DATE_PATTERN.search(text)
    if match:
        return _normalize_date(match.group(1))
    
    # 如果没找到带标签的日期，尝试第一个日期
    date_match = DATE_PATTERN.search(text)
    if date_match:
        return _normalize_date(date_match.group(1))
    
    return None


def extract_implement_date(text: str) -> Optional[str]:
    """
    从文本中提取实施日期。
    
    Args:
        text: 输入文本
    
    Returns:
        日期字符串或 None
    """
    match = IMPLEMENT_DATE_PATTERN.search(text)
    if match:
        return _normalize_date(match.group(1))
    return None


def extract_replace_standard(text: str) -> Optional[str]:
    """
    从文本中提取代替标准号。
    
    Args:
        text: 输入文本
    
    Returns:
        代替标准号字符串或 None
    """
    match = REPLACE_STANDARD_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None


def _normalize_date(date_str: str) -> str:
    """
    规范化日期格式为 YYYY-MM-DD。
    
    Args:
        date_str: 原始日期字符串
    
    Returns:
        规范化后的日期字符串
    """
    # 替换各种日期分隔符
    normalized = date_str.replace('年', '-').replace('月', '-').replace('日', '')
    normalized = normalized.replace('/', '-')
    
    # 确保是 YYYY-MM-DD 格式
    parts = normalized.split('-')
    if len(parts) >= 3:
        year = parts[0]
        month = parts[1].zfill(2)
        day = parts[2].zfill(2)
        return f"{year}-{month}-{day}"
    
    return date_str


def clean_text(text: str) -> str:
    """
    清理文本，移除特殊字符和多余空白。
    
    Args:
        text: 原始文本
    
    Returns:
        清理后的文本
    """
    # 移除换页符
    text = text.replace('\x0c', '\n')
    
    # 规范化换行符
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\r', '\n', text)
    
    # 移除过度空白
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

