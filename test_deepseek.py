"""
DeepSeek API 快速测试脚本。

直接运行此脚本验证 API Key 是否正确，以及接口是否能正常返回。
用法：
    python test_deepseek.py
"""

import os
import sys
import json

# 加载 .env 文件（从项目根目录运行时自动找到）
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env 文件加载成功")
except ImportError:
    print("⚠️  python-dotenv 未安装，将直接读取系统环境变量")


def test_basic_call():
    """测试最基础的 DeepSeek 调用（一问一答）"""
    api_key = os.environ.get('DEEPSEEK_API_KEY', '')

    if not api_key or api_key == 'your_api_key_here':
        print("\n❌ 错误：请先在 .env 文件中填写你的 DEEPSEEK_API_KEY")
        print("   打开 .env 文件，将 your_api_key_here 替换为真实的 Key")
        sys.exit(1)

    print(f"\n🔑 API Key: {api_key[:8]}...（已隐藏后续字符）")
    print(f"🌐 Base URL: {os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')}")
    print(f"🤖 模型: {os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')}")

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
        )

        print("\n⏳ 正在测试 API 连接...")

        response = client.chat.completions.create(
            model=os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat'),
            messages=[{"role": "user", "content": "你好，请用一句话介绍你自己。"}],
            max_tokens=100,
        )

        reply = response.choices[0].message.content
        print(f"\n✅ API 连接成功！DeepSeek 回复：\n{reply}")
        return True

    except Exception as e:
        print(f"\n❌ API 调用失败: {e}")
        return False


def test_revision_extraction():
    """测试修订变化提取功能（使用真实的标准前言样本）"""

    # 使用用户提供的真实前言文本片段作为测试样本
    sample_preface = """
本文件代替GB/T 1.1—2009《标准化工作导则 第1部分:标准的结构和编写》，与GB/T 1.1—2009相比，
除结构调整和编辑性改动外，主要技术变化如下:
a）增加了"文件的类别"一章（见第4章）；
b）将"总则"更改为"目标、原则和要求"，细分了原则，并将2009年版的有关内容更改后纳入（见第5章，
   2009年版的第4章、5.1.1、5.1.2.1、5.1.2.2、6.3.1.1和6.3.4）；
c）在"文件名称"中增加了表示标准功能类型的词语及其英文译名（见6.1.4.2）；
d）更改了要素的类别、构成以及表述形式（见6.2.2，2009年版的5.1.3）；
e）更改了"列项"的具体形式及编写规则（见7.5，2009年版的5.2.6）；
j）删除了性能原则（见2009年版的6.3.1.2）、可证实性原则（见2009年版的6.3.1.3）；

本文件参考"ISO/IEC导则，第2部分，2018"起草。
"""

    print("\n" + "=" * 60)
    print("测试修订变化提取功能")
    print("=" * 60)

    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if not api_key or api_key == 'your_api_key_here':
        print("⚠️  跳过（API Key 未配置）")
        return

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
        )

        prompt = f"""请从以下标准文档前言文本中提取修订变化条目，输出严格 JSON 格式：
{{
  "replaced_standard": "被代替的标准号或null",
  "is_first_issue": false,
  "changes": [
    {{"index": "a", "type": "增加|更改|删除|其他", "content": "完整条目内容"}}
  ]
}}

前言文本：
---
{sample_preface}
---

只输出 JSON，不要有任何其他内容。"""

        print("⏳ 正在提取修订变化条目...")

        response = client.chat.completions.create(
            model=os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat'),
            messages=[
                {"role": "system", "content": "你是专业标准文档解析助手，只输出 JSON。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        print("\n✅ 提取成功！结果如下：")
        print(f"   被代替标准：{result.get('replaced_standard', '未提取到')}")
        print(f"   是否首次发布：{result.get('is_first_issue', False)}")
        print(f"   修订条目数量：{len(result.get('changes', []))}")
        print("\n   各条目：")
        for item in result.get('changes', []):
            type_emoji = {"增加": "➕", "更改": "✏️", "删除": "❌"}.get(item['type'], "📌")
            print(f"   {type_emoji} [{item['index']}] {item['type']}：{item['content'][:60]}...")

        print("\n   完整 JSON 输出：")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        print(f"   原始输出: {raw}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")


if __name__ == '__main__':
    print("=" * 60)
    print("DeepSeek API 连接测试")
    print("=" * 60)

    ok = test_basic_call()
    if ok:
        test_revision_extraction()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
