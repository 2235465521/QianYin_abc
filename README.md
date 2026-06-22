# 标准文档自动化解析系统

## 项目概述

这是一个基于 Django 和 Celery 的标准文档自动化解析系统，用于自动提取 PDF 和 Word 文档中的结构化数据（如标准号、分类号等）。

### 核心功能流程

```
监控目录 → Watchdog 检测新文件 → Django 命令触发 → Celery 异步任务
→ 文件解析器 (PDF/DOCX) → 正则表达式提取 → Django ORM 存储 → MySQL 数据库
```

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境 (Windows)
venv\\Scripts\\activate

# 激活虚拟环境 (Linux/Mac)
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 数据库配置

确保 MySQL 已运行，创建数据库：

```sql
CREATE DATABASE new_zhixiuding CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. 初始化数据库

```bash
python manage.py migrate
```

### 4. 启动 Redis（消息队列）

```bash
# Windows
redis-server

# Linux/Mac
redis-server
```

### 5. 启动 Celery Worker（后台任务处理）

```bash
celery -A emis_core worker -l info
```

### 6. 启动文件监控守护进程

```bash
python manage.py watch_daemon
```

## 模块说明

### 目录结构

```
emis_project/
├── manage.py                          # Django 管理脚本
├── emis_core/                         # 核心配置
│   ├── settings.py                   # Django 设置
│   ├── celery.py                     # Celery 配置
│   └── wsgi.py                       # WSGI 应用
├── standards_parser/                  # 解析应用
│   ├── models.py                     # 数据库模型
│   ├── tasks.py                      # Celery 任务
│   ├── parsers/                      # 解析引擎
│   │   ├── base.py                  # 基类
│   │   ├── pdf_parser.py            # PDF 解析器
│   │   ├── docx_parser.py           # Word 解析器
│   │   └── regex_rules.py           # 正则表达式规则
│   └── management/commands/
│       └── watch_daemon.py           # 文件监控守护程序
└── data/
    ├── watch_folder/                 # 监控目录
    └── archive/                      # 归档目录
```

### 核心组件

#### 1. **BaseParser (基类)**
   - 定义解析器接口
   - 提供通用的文本清理和验证方法

#### 2. **PDFParser / DOCXParser (具体解析器)**
   - 继承 BaseParser
   - 使用 pdfplumber (PDF) 和 python-docx (Word) 库
   - 提取原始文本

#### 3. **regex_rules.py (正则表达式规则)**
   - 集中管理所有正则表达式
   - 提供标准号、分类号、标题等的提取函数
   - 支持多种标准号格式 (GB/T, QB/T, YY 等)

#### 4. **models.py (数据库模型)**
   - `ParsedStandard`: 存储解析结果
   - `ParsingLog`: 记录解析过程和错误

#### 5. **tasks.py (Celery 任务)**
   - `parse_document`: 异步解析文档
   - `archive_document`: 归档已处理的文件

#### 6. **watch_daemon.py (文件监控)**
   - 使用 Watchdog 库监控目录
   - 检测新文件时自动触发解析任务

## 配置说明

在 `emis_core/settings.py` 中可以配置：

```python
# MySQL 数据库
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'new_zhixiuding',
        'USER': 'root',
        'PASSWORD': 'lsj223546',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}

# Redis (消息队列)
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

# 监控文件夹
WATCH_FOLDER = os.path.join(BASE_DIR, 'data', 'watch_folder')
ARCHIVE_FOLDER = os.path.join(BASE_DIR, 'data', 'archive')
```

## 使用示例

### 方式 1: 自动监控（推荐）

```bash
# 启动文件监控守护程序
python manage.py watch_daemon

# 将文件放到 data/watch_folder 目录
# 系统会自动检测并解析
```

### 方式 2: 手动触发任务

```python
from standards_parser.tasks import parse_document

# 触发异步解析任务
parse_document.delay('/path/to/document.pdf', 'pdf')
```

### 方式 3: 通过 Django Shell

```bash
python manage.py shell

# 查询已解析的标准
from standards_parser.models import ParsedStandard
standards = ParsedStandard.objects.filter(status='success')
for standard in standards:
    print(f"{standard.standard_number}: {standard.title}")
```

## 支持的文件格式

- **PDF**: 使用 pdfplumber 库解析
- **DOCX**: 使用 python-docx 库解析

## 提取的字段

- `standard_number`: 标准号 (例: GB/T 12345-2020)
- `classification_number`: 分类号 (例: A101)
- `title`: 文档标题
- `content`: 内容摘要（前 5000 字符）
- `metadata`: 元数据（页数、表格数等）

## 错误处理

系统具有自动重试机制：

- 任务失败时，Celery 会自动重试最多 3 次
- 每次重试间隔为 60 秒 * 2^(重试次数)
- 所有错误日志记录在 `logs/emis.log`

## 日志

日志文件位置: `logs/emis.log`

使用 RotatingFileHandler，当日志文件达到 10MB 时自动分割，保留最近 5 个备份。

## 常见问题

### Q: Redis 连接失败
A: 检查 Redis 是否已启动，默认监听 localhost:6379

### Q: MySQL 连接失败
A: 检查 MySQL 服务是否运行，用户名密码是否正确

### Q: Celery 任务未执行
A: 确保 Celery Worker 已启动，检查 Redis 连接

### Q: 文件未被检测到
A: 确保文件已放到监控目录 (data/watch_folder)，检查文件扩展名是否支持

## 性能优化建议

1. **索引优化**: ParsedStandard 模型已为常用字段创建索引
2. **异步处理**: 所有 I/O 操作都通过 Celery 异步执行
3. **缓存**: 可考虑使用 Redis 缓存高频查询结果
4. **并发控制**: 根据服务器资源调整 Celery Worker 数量

## 开发指南

### 添加新的解析器

```python
# standards_parser/parsers/custom_parser.py
from .base import BaseParser

class CustomParser(BaseParser):
    def parse(self, file_path):
        # 实现解析逻辑
        return {
            'standard_number': '...',
            'classification_number': '...',
            'title': '...',
            'content': '...',
        }
```

### 修改正则表达式规则

编辑 `standards_parser/parsers/regex_rules.py` 中的规则常量。

## 许可证

MIT

## 联系方式

如有问题或建议，请联系项目维护者。
