# -*- coding: utf-8 -*-
import os, sys, json
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emis_core.settings')

import django
django.setup()

from standards_parser.models import StandardDocument

docs = StandardDocument.objects.order_by('-created_at')[:5]

total = docs.count()
print(f"最近处理的 {total} 篇文档结果：\n")

for i, doc in enumerate(docs, 1):
    changes = doc.revision_changes or []
    print(f"{'='*60}")
    print(f"[{i}] {doc.standard_code}-{doc.year_code}")
    print(f"  状态        : {doc.status}")
    print(f"  中文名      : {(doc.cn_name or '')[:35]}")
    print(f"  代替标准    : {doc.replace_standard or '无/未提取到'}")
    print(f"  提取来源    : {doc.extraction_source or '未知'}")
    print(f"  修订条目数  : {len(changes)}")
    if changes:
        for item in changes[:4]:
            content_preview = item.get('content', '')[:45]
            print(f"    [{item['index']}]({item['type']}) {content_preview}...")
        if len(changes) > 4:
            print(f"    ...还有 {len(changes)-4} 条未显示")
    else:
        print(f"    (无修订条目 - 可能是首次发布或提取失败)")
    print()

# 统计
all_docs = StandardDocument.objects.all()
total_all = all_docs.count()
success = all_docs.filter(status='success').count()
has_revision = all_docs.exclude(revision_changes=None).exclude(revision_changes=[]).count()
via_regex = all_docs.filter(extraction_source='regex').count()
via_llm = all_docs.filter(extraction_source='llm').count()

print(f"{'='*60}")
print(f"数据库整体统计：")
print(f"  总记录数      : {total_all}")
print(f"  解析成功      : {success}")
print(f"  有修订条目    : {has_revision}")
print(f"  正则提取      : {via_regex} 篇")
print(f"  LLM提取       : {via_llm} 篇")
print(f"{'='*60}")
