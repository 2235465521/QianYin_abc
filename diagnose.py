# -*- coding: utf-8 -*-
"""
最终结论测试：
1. 把 GB 1002-2024 的全文直接发给 DeepSeek，看它能提取什么
2. 这代表"LLM兜底"的真实效果
"""
import os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emis_core.settings')
import django; django.setup()

import pymysql, json
from standards_parser.parsers import get_parser
from standards_parser.parsers.llm_client import get_deepseek_client

files_root = os.environ.get('STANDARD_FILES_ROOT', '')

conn = pymysql.connect(
    host='localhost', port=3306,
    user='root', password='lsj223546',
    database='mydate', charset='gbk',
    cursorclass=pymysql.cursors.DictCursor
)
cursor = conn.cursor()
cursor.execute("""
    SELECT sb.std_id, fp.file_path, fp.file_name
    FROM std_base sb
    INNER JOIN std_filepath fp ON sb.id = fp.base_id
    WHERE fp.file_name LIKE '%1002%2024%'
    LIMIT 1
""")
row = cursor.fetchone()
conn.close()

file_path = row['file_path'].replace('\\', '/')
if not os.path.isabs(file_path):
    file_path = os.path.join(files_root, file_path.strip('/'))

parser = get_parser(file_path)
result = parser.parse()
full_text = result.get('full_text', '')

print(f"文件: {row['file_name']}")
print(f"文本总长: {len(full_text)} 字")
print(f"\n把全文（前3000字）发给 DeepSeek...\n")

client = get_deepseek_client()
llm_result = client.extract_revision_changes(full_text[:3000])

if llm_result:
    print(f"LLM 返回结果:")
    print(json.dumps(llm_result, ensure_ascii=False, indent=2))
else:
    print("LLM 返回 None（无法从当前文本提取修订内容）")
    print("\n结论：该PDF前言页为扫描图像，文字层缺失，任何方法都无法提取修订内容。")
    print("需要使用 OCR 重新识别该 PDF 的前言页。")
