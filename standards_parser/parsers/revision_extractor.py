"""
Revision change extractor for standard documents.

Uses a hybrid approach:
  1. Regex engine  - fast, free, covers ~70% of well-formatted documents
  2. DeepSeek LLM  - fallback for complex/poorly-formatted documents

Confidence scoring determines which path is taken.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# 正则：定位前言中"修订变化"区域
# ============================================================================

# 匹配引导句：与XX相比，主要技术变化如下
REVISION_INTRO_PATTERN = re.compile(
    r'(?:与\s*.{2,60}?\s*相比[，,、].*?(?:主要技术变化如下|主要变化如下|变化如下)|'
    r'本(?:文件|标准)在.*?基础上.*?修订)',
    re.DOTALL
)

# 匹配"被代替"标准号：本文件代替 GB/T 1.1—2009
# 支持多个标准号，用顿号/逗号分隔
REPLACED_STANDARD_PATTERN = re.compile(
    r'本(?:文件|标准)\s*代替\s*'
    r'((?:GB(?:/[TZ])?|QB(?:/T)?|JB(?:/T)?|YY(?:/T)?|NY|HG|SH|JT|YD|SL|CJ|GA)'
    r'\s*[\d./]+'                          # 标准号主体
    r'(?:\s*[—\-–]\s*\d{4})?'             # 年份
    r'(?:\s*[、，,]\s*'                    # 多个标准号分隔
    r'(?:GB(?:/[TZ])?|QB(?:/T)?|JB(?:/T)?|YY(?:/T)?|NY|HG|SH|JT|YD|SL|CJ|GA)'
    r'\s*[\d./]+(?:\s*[—\-–]\s*\d{4})?)*)',
    re.IGNORECASE
)

# 匹配条目行：a） b) a、 等格式
REVISION_ITEM_PATTERN = re.compile(
    r'^\s*([a-z])\s*[）)、]\s*(.+)',
    re.IGNORECASE | re.MULTILINE
)

# 匹配前言结束的边界词（用于截断提取范围）
PREFACE_END_KEYWORDS = re.compile(
    r'(?:本(?:文件|标准)(?:由|参考|按照|依据)|起草单位|主要起草人|归口单位)',
    re.MULTILINE
)

# 变化类型关键词
CHANGE_TYPE_MAP = [
    (re.compile(r'^增加了|^新增了|^增设了'), '增加'),
    (re.compile(r'^删除了|^取消了|^去掉了'), '删除'),
    (re.compile(r'^更改了|^修改了|^将.{1,30}更改为|^把.{1,30}改为'), '更改'),
    (re.compile(r'^合并了|^整合了'), '合并'),
]


# ============================================================================
# 正则提取引擎
# ============================================================================

def _locate_preface_revision_block(text: str) -> Optional[str]:
    """
    定位前言中"修订变化"区域的文本块。
    
    Returns:
        修订变化区域的文本，或 None（未找到）
    """
    intro_match = REVISION_INTRO_PATTERN.search(text)
    if not intro_match:
        return None

    start = intro_match.start()

    # 找到结束边界
    end_match = PREFACE_END_KEYWORDS.search(text, intro_match.end())
    end = end_match.start() if end_match else min(len(text), start + 3000)

    block = text[start:end]
    logger.debug(f"Revision block located: {len(block)} chars")
    return block


def _extract_replaced_standard(text: str) -> Optional[str]:
    """从文本中提取被代替的标准号。"""
    match = REPLACED_STANDARD_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None


def _detect_change_type(content: str) -> str:
    """根据条目内容首句判断变化类型。"""
    content_stripped = content.strip()
    for pattern, change_type in CHANGE_TYPE_MAP:
        if pattern.search(content_stripped):
            return change_type
    return '其他'


def _merge_wrapped_lines(block: str) -> str:
    """
    合并被换行切断的条目内容。
    
    PDF 提取的文本常出现行内换行，识别规律：
    - 下一行以小写字母/数字/中文（非条目起始字符）开头 → 合并
    - 下一行以 a-z） 开头 → 新条目，不合并
    """
    lines = block.split('\n')
    merged = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            merged.append('')
            continue
        # 判断是否是新条目行
        is_new_item = bool(re.match(r'^[a-z]\s*[）)、]', stripped, re.IGNORECASE))
        if merged and not is_new_item and not merged[-1] == '':
            # 与上一行合并
            merged[-1] = merged[-1].rstrip() + stripped
        else:
            merged.append(stripped)
    return '\n'.join(merged)


def extract_by_regex(text: str) -> dict:
    """
    正则引擎：从标准文本中提取修订变化条目。

    Returns:
        {
            "replaced_standard": str or None,
            "is_first_issue": bool,
            "changes": [{"index": str, "type": str, "content": str}],
            "confidence": float  # 0.0 ~ 1.0
        }
    """
    result = {
        "replaced_standard": None,
        "is_first_issue": False,
        "changes": [],
        "confidence": 0.0,
    }

    # 1. 提取被代替标准
    replaced = _extract_replaced_standard(text)
    if replaced:
        result["replaced_standard"] = replaced

    # 2. 检测是否首次发布
    # 规则：必须是"本文件/本标准 为/是 首次发布"这样的主语明确的表述
    # 排除历史性提及，如"本标准于1985年首次发布"（此为修订版描述修订历史）
    # 同时：如果已发现"代替"标准号，则一定不是首次发布
    FIRST_ISSUE_PATTERN = re.compile(
        r'本(?:文件|标准|规范)\s*(?:为|是|属于|系)\s*首次(?:发布|制定|颁布)|'
        r'首次(?:发布|制定|颁布)(?:的国家标准|的行业标准|的标准)',
        re.IGNORECASE
    )
    is_first = bool(FIRST_ISSUE_PATTERN.search(text)) and not replaced
    if is_first:
        result["is_first_issue"] = True
        result["confidence"] = 0.9
        logger.info("Detected as first-issue document, skipping revision extraction")
        return result

    # 3. 定位修订区块
    block = _locate_preface_revision_block(text)
    if not block:
        logger.debug("Regex: revision block not found")
        result["confidence"] = 0.1
        return result

    # 4. 合并跨行内容
    merged_block = _merge_wrapped_lines(block)

    # 5. 逐条提取
    items = REVISION_ITEM_PATTERN.findall(merged_block)
    changes = []
    for idx, content in items:
        content_clean = content.strip().rstrip('；;')
        change_type = _detect_change_type(content_clean)
        changes.append({
            "index": idx.lower(),
            "type": change_type,
            "content": content_clean,
        })

    result["changes"] = changes

    # 6. 置信度评分
    confidence = _calc_confidence(changes, block)
    result["confidence"] = confidence

    logger.info(
        f"Regex extraction: {len(changes)} items, confidence={confidence:.2f}, "
        f"replaced={replaced}"
    )
    return result


# ============================================================================
# 修订动词关键词（用于语义验证）
# ============================================================================

# 核心修订动词：这些词出现在条目开头，是修订条目的语义特征
REVISION_VERB_PATTERN = re.compile(
    r'(?:增加了|新增了|增设了|补充了|'         # 增加类
    r'更改了|修改了|将.{1,30}更改为|'          # 更改类
    r'把.{1,30}改为|调整了|重新规定了|'        # 更改类
    r'删除了|取消了|去掉了|删去了|去除了)',     # 删除类
    re.DOTALL
)


def _calc_confidence(changes: list, block: str) -> float:
    """
    三重防御置信度评分。

    防御1 - 语义验证（最重要）：
        条目内容必须包含修订动词（增加了/更改了/删除了...）
        如果没有任何条目含修订动词 → 判定为误提，强制低分

    防御2 - 上下文锚定验证：
        条目必须出现在标准前言修订引导句之后的文本块中
        通过 block 是否包含引导句关键词来验证

    防御3 - 结构一致性评分：
        条目数量、序号连续性、平均长度（加分项，非必要条件）
    """
    if not changes:
        return 0.1

    # ----------------------------------------------------------------
    # 防御1：语义验证 - 检查修订动词命中率
    # ----------------------------------------------------------------
    verb_hit_count = sum(
        1 for c in changes
        if REVISION_VERB_PATTERN.search(c.get('content', ''))
    )
    verb_ratio = verb_hit_count / len(changes)

    # 没有任何条目命中修订动词 → 极可能是误提，强制打低分触发 LLM
    if verb_hit_count == 0:
        logger.warning(
            f"Confidence FORCED LOW: 0 out of {len(changes)} items contain "
            f"revision verbs. Likely false positive extraction."
        )
        return 0.15

    # 命中率低于 30% → 可疑，打低分
    if verb_ratio < 0.30:
        logger.warning(
            f"Confidence PENALIZED: only {verb_hit_count}/{len(changes)} "
            f"items ({verb_ratio:.0%}) contain revision verbs."
        )
        return 0.30

    # ----------------------------------------------------------------
    # 防御2：上下文锚定 - 确认 block 是前言修订区域而非正文
    # ----------------------------------------------------------------
    context_anchor = bool(re.search(
        r'主要技术变化如下|主要变化如下|变化如下|与.{2,30}相比',
        block
    ))
    if not context_anchor:
        logger.warning(
            "Confidence PENALIZED: revision block lacks intro sentence anchor. "
            "Items may be extracted from wrong section."
        )
        # 即使有内容也打低分，因为没有引导句就不能确认是修订区域
        return 0.25

    # ----------------------------------------------------------------
    # 防御3：结构一致性加分（在通过前两关之后）
    # ----------------------------------------------------------------
    # 基础分：已通过语义验证的条目贡献
    score = 0.50 + (verb_ratio * 0.20)  # 最多 +0.20

    # 条目数量
    if len(changes) >= 3:
        score += 0.10
    if len(changes) >= 6:
        score += 0.05

    # 序号连续性（a,b,c,...）
    expected = [chr(ord('a') + i) for i in range(len(changes))]
    actual = [c['index'] for c in changes]
    if actual == expected:
        score += 0.10

    # 平均内容长度 > 15 字
    avg_len = sum(len(c['content']) for c in changes) / len(changes)
    if avg_len > 15:
        score += 0.05

    final_score = min(score, 1.0)
    logger.debug(
        f"Confidence: {final_score:.2f} | "
        f"verb_ratio={verb_ratio:.0%} | "
        f"context_anchor={context_anchor} | "
        f"items={len(changes)}"
    )
    return final_score


# ============================================================================
# 混合引擎（对外接口）
# ============================================================================

def extract_revision_changes(text: str, threshold: float = 0.75) -> dict:
    """
    主入口：混合引擎提取修订变化条目。
    
    优先使用正则，置信度低于 threshold 时自动调用 DeepSeek 兜底。

    Args:
        text:      标准文档的完整文本（或前言文本）
        threshold: 置信度阈值，低于此值时调用 LLM（默认 0.75）

    Returns:
        {
            "replaced_standard": str or None,
            "is_first_issue": bool,
            "changes": [{"index": str, "type": str, "content": str}],
            "source": "regex" or "llm" or "failed",
            "confidence": float,
        }
    """
    # --- Step 1: 正则提取 ---
    regex_result = extract_by_regex(text)
    regex_result["source"] = "regex"

    if regex_result["confidence"] >= threshold:
        logger.info(f"Regex confidence {regex_result['confidence']:.2f} >= {threshold}, skipping LLM")
        return regex_result

    # --- Step 2: 置信度不足，调用 LLM 兜底 ---
    logger.info(
        f"Regex confidence {regex_result['confidence']:.2f} < {threshold}, "
        f"falling back to DeepSeek LLM..."
    )

    try:
        from .llm_client import get_deepseek_client

        client = get_deepseek_client()
        if not client.is_available():
            logger.warning("LLM not available (API key not set), returning regex result")
            regex_result["source"] = "regex_only"
            return regex_result

        # 只传前言区域（节省 Token）
        preface_text = _extract_preface_section(text)
        llm_result = client.extract_revision_changes(preface_text)

        if llm_result:
            llm_result["source"] = "llm"
            llm_result["confidence"] = 0.95  # LLM 结果默认高置信
            logger.info(
                f"LLM extraction success: {len(llm_result.get('changes', []))} items"
            )
            return llm_result
        else:
            logger.warning("LLM returned None, falling back to regex result")

    except Exception as e:
        logger.error(f"LLM fallback failed: {e}", exc_info=True)

    # --- Step 3: 两者均失败，返回正则结果（不管置信度）---
    regex_result["source"] = "regex_fallback"
    return regex_result


def _extract_preface_section(text: str, max_chars: int = 4000) -> str:
    """
    从完整文档文本中截取真正的前言部分（跳过目录页中的"前言"）。

    目录页中"前言"的特征：后面紧跟着页码数字（如"前言 ....... 1"）
    真正的前言页特征：后面紧跟着实质性中文段落文字

    策略：
    1. 找到所有"前言"出现位置
    2. 跳过后面紧跟页码的（目录中的）
    3. 取第一个后面跟着正式段落内容的位置
    4. 截取到正文第一章开始（"1 范围" 或 "第1章"）
    """
    # 找所有"前言"出现位置
    preface_positions = [m.start() for m in re.finditer(r'前\s*言', text)]

    # 目录中"前言"的特征：后面50字内出现"...数字" 或纯数字（页码）
    TOC_ENTRY_PATTERN = re.compile(r'[.。·\s]{2,}\d+\s*$|^\s*\d+\s*$', re.MULTILINE)

    real_preface_start = None
    for pos in preface_positions:
        # 取"前言"之后的100个字符，检查是否是目录条目
        after = text[pos:pos + 100]
        next_line = after.split('\n')[1] if '\n' in after else after[10:]

        # 目录特征：后面一行是页码（纯数字或带省略号的）
        is_toc_entry = bool(TOC_ENTRY_PATTERN.search(next_line.strip()))

        # 正文特征：后面有中文句子（含"本文件""本标准""与""代替"等词）
        has_substantive = bool(re.search(r'[\u4e00-\u9fff]{5,}', after[5:]))

        if not is_toc_entry and has_substantive:
            real_preface_start = pos
            break

    # 如果找不到真实前言，退回到第一个"前言"位置
    if real_preface_start is None:
        start_match = re.search(r'前\s*言', text)
        real_preface_start = start_match.start() if start_match else 0

    # 确定前言结束位置（正文第一章开始）
    end_match = re.search(
        r'\n\s*1\s+范\s*围|\n\s*第\s*[一1]\s*章|\n\s*1\s*\.\s*范围',
        text[real_preface_start:]
    )
    if end_match:
        end = real_preface_start + end_match.start()
    else:
        end = real_preface_start + max_chars

    section = text[real_preface_start:end]
    return section[:max_chars]  # 兜底截断
