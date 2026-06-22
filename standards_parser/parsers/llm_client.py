"""
DeepSeek LLM Client for standard document revision extraction.

Uses the OpenAI-compatible API to call DeepSeek-V3 as a fallback
when regex-based extraction has low confidence.
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# Prompt 模板
# ============================================================================

REVISION_EXTRACTION_PROMPT = """你是一个专业的中国国家标准文档解析助手。

请从下面提供的标准文档【前言】文本中，精确提取"与上一版本相比的修订变化条目"。

## 提取规则
1. 找到类似"与XXX相比，主要技术变化如下："的引导句
2. 提取引导句之后的所有条目（以 a) b) c) 或 a） b） 或 a、 等形式编号）
3. 每个条目完整提取，不要截断
4. 识别每条变化的类型：增加 / 更改 / 删除 / 其他
5. 同时提取"本文件代替"或"本标准代替"的被代替标准号

## 输出格式（严格 JSON，不要有任何额外文字）
{{
  "replaced_standard": "被代替的标准号，如 GB/T 1.1-2009，若没有则为 null",
  "is_first_issue": false,
  "changes": [
    {{
      "index": "a",
      "type": "增加|更改|删除|其他",
      "content": "完整的条目内容文本"
    }}
  ]
}}

若该标准是首次发布（没有被代替标准），则 is_first_issue 为 true，changes 为空数组。

## 前言文本如下：
---
{preface_text}
---

请直接输出 JSON，不要有任何解释或 markdown 代码块标记。"""


# ============================================================================
# DeepSeek 客户端
# ============================================================================

class DeepSeekClient:
    """
    DeepSeek-V3 API 客户端。
    
    使用 OpenAI 兼容接口调用 DeepSeek，无需额外 SDK。
    通过环境变量配置，适合生产环境使用。
    """

    def __init__(self):
        """
        从环境变量初始化客户端配置。
        
        需要在 .env 中设置：
            DEEPSEEK_API_KEY   - 你的 DeepSeek API Key
            DEEPSEEK_BASE_URL  - API 地址（默认 https://api.deepseek.com）
            DEEPSEEK_MODEL     - 模型名称（默认 deepseek-chat 即 V3）
            DEEPSEEK_TIMEOUT   - 超时秒数（默认 60）
        """
        self.api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        self.base_url = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
        self.model = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
        self.timeout = int(os.environ.get('DEEPSEEK_TIMEOUT', '60'))

        if not self.api_key or self.api_key == 'your_api_key_here':
            logger.warning(
                "DeepSeek API Key 未配置！请在 .env 文件中设置 DEEPSEEK_API_KEY"
            )

    def is_available(self) -> bool:
        """检查客户端是否已正确配置。"""
        return bool(self.api_key and self.api_key != 'your_api_key_here')

    def extract_revision_changes(self, preface_text: str) -> Optional[dict]:
        """
        调用 DeepSeek-V3 从前言文本中提取修订变化条目。

        Args:
            preface_text: 标准文档前言的原始文本（建议传入前言区域，不超过 4000 字）

        Returns:
            解析后的字典，格式：
            {
                "replaced_standard": "GB/T 1.1-2009" 或 None,
                "is_first_issue": False,
                "changes": [
                    {"index": "a", "type": "增加", "content": "..."}
                ]
            }
            失败时返回 None。
        """
        if not self.is_available():
            logger.error("DeepSeek API Key 未配置，无法调用 LLM")
            return None

        # 限制文本长度，避免超出 Token 限制（前言一般不超过 3000 字）
        truncated_text = preface_text[:4000] if len(preface_text) > 4000 else preface_text

        prompt = REVISION_EXTRACTION_PROMPT.format(preface_text=truncated_text)

        try:
            # 使用 OpenAI 兼容接口（DeepSeek 完全兼容 OpenAI SDK）
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )

            logger.info(f"调用 DeepSeek [{self.model}] 提取修订变化条目...")

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的标准文档解析助手，只输出规定格式的 JSON，不输出任何其他内容。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.0,       # 设为 0 保证输出稳定可复现
                max_tokens=2000,
                response_format={"type": "json_object"},  # 强制 JSON 输出
            )

            raw_output = response.choices[0].message.content.strip()
            logger.debug(f"DeepSeek 原始输出: {raw_output[:200]}...")

            # 解析 JSON
            result = json.loads(raw_output)

            # 基本校验
            if 'changes' not in result:
                logger.warning("DeepSeek 返回的 JSON 缺少 'changes' 字段")
                return None

            logger.info(
                f"DeepSeek 提取成功：{len(result.get('changes', []))} 条修订变化，"
                f"被代替标准：{result.get('replaced_standard', '无')}"
            )
            return result

        except json.JSONDecodeError as e:
            logger.error(f"DeepSeek 返回的内容无法解析为 JSON: {e}")
            return None

        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}", exc_info=True)
            return None


# ============================================================================
# 模块级单例（避免重复实例化）
# ============================================================================

_client_instance: Optional[DeepSeekClient] = None


def get_deepseek_client() -> DeepSeekClient:
    """
    获取 DeepSeek 客户端的全局单例。
    
    Returns:
        DeepSeekClient 实例
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = DeepSeekClient()
    return _client_instance
