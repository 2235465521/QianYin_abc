# -*- coding: utf-8 -*-
"""
验证三重防御机制：
场景A - 正常修订前言（应该高置信度，直接用正则）
场景B - 正文中碰巧有 a) b) c) 格式（应该低置信度，触发LLM）
"""
import sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from standards_parser.parsers.revision_extractor import extract_by_regex

# ====== 场景A：正常修订前言 ======
normal_preface = """
本文件代替GB/T 1.1-2009，与GB/T 1.1-2009相比，主要技术变化如下:
a）增加了文件的类别一章（见第4章）；
b）将总则更改为目标、原则和要求；
c）更改了列项的具体形式及编写规则；
d）删除了性能原则（见2009年版的6.3.1.2）；
本文件由国家标准化管理委员会提出。
"""

# ====== 场景B：正文中碰巧有 a) b) c)（误提风险） ======
false_positive_text = """
前言
本文件按照GB/T 1.1-2020起草。
本文件代替GB/T 9999-2010。

1 范围
本文件规定了以下内容：
a）铝合金材质应符合要求；
b）表面处理工艺分为以下几类；
c）检验方法按照附录A执行；
d）包装储存应满足条件；
"""

print("=" * 60)
print("场景A：正常修订前言（期望：高置信度）")
print("=" * 60)
result_a = extract_by_regex(normal_preface)
conf_a = result_a['confidence']
count_a = len(result_a['changes'])
print(f"置信度: {conf_a:.2f}  ->  {'直接使用正则' if conf_a >= 0.75 else '触发LLM兜底'}")
print(f"条目数: {count_a}")
for item in result_a['changes']:
    print(f"  [{item['index']}] ({item['type']}) {item['content'][:50]}")

print()
print("=" * 60)
print("场景B：正文中的 a)b)c) 列项（期望：低置信度触发LLM）")
print("=" * 60)
result_b = extract_by_regex(false_positive_text)
conf_b = result_b['confidence']
count_b = len(result_b['changes'])
print(f"置信度: {conf_b:.2f}  ->  {'直接使用正则（错误！）' if conf_b >= 0.75 else 'LLM兜底（正确防御）'}")
print(f"条目数: {count_b}")
for item in result_b['changes']:
    print(f"  [{item['index']}] ({item['type']}) {item['content'][:50]}")

print()
print("=" * 60)
verdict = "防御成功" if conf_b < 0.75 and conf_a >= 0.75 else "防御失败，需要调整"
print(f"验证结果: {verdict}")
print("=" * 60)
