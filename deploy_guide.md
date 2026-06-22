# 服务器部署指南 (Deployment Guide)

本项目包含 Django 服务、Celery 异步任务队列以及 Watch Daemon 文件夹监控服务。为了让程序在服务器上**默认执行、开机自启且后台稳定运行**，推荐使用 Linux (如 Ubuntu) 系统下的 `systemd` 服务进行配置。

---

## 🛠 第一步：服务器环境准备

### 1. 安装系统依赖
在服务器上安装 Python3、Git、Redis（用于 Celery 队列）以及 Tesseract OCR（用于图片 PDF 的文字提取）：

```bash
# 更新源
sudo apt update

# 安装 Python3 虚拟环境和开发库
sudo apt install -y python3-pip python3-venv git

# 安装 Redis (Celery 的消息中间件)
sudo apt install -y redis-server

# 安装 Tesseract OCR 及其中文语言包
sudo apt install -y tesseract-ocr tesseract-ocr-chi-sim
```

### 2. 检查 Redis 状态
确保 Redis 服务已启动并正常运行：
```bash
sudo systemctl status redis-server
```

---

## 🚀 第二步：拉取代码与配置虚拟环境

### 1. 克隆代码
```bash
cd /opt
# 克隆你刚刚推送的仓库
sudo git clone git@github.com:2235465521/QianYin_abc.git
cd QianYin_abc
```

### 2. 创建并激活虚拟环境
```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate
```

### 3. 安装依赖包
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 📝 第三步：修改 `.env` 配置文件

在项目根目录下创建并配置 `.env` 文件：
```bash
cp .env.example .env  # 如果有模板，否则直接新建一个 .env 文件
nano .env
```

**示例 `.env` 内容**：
```ini
# ==========================================
# 目标数据库 (Django 连接的数据库)
# ==========================================
DB_NAME=new_zhixiuding
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=127.0.0.1
DB_PORT=3306

# ==========================================
# 源数据库 (Legacy 原始数据读取源)
# ==========================================
SOURCE_DB_NAME=mydate
SOURCE_DB_USER=your_db_user
SOURCE_DB_PASSWORD=your_db_password
SOURCE_DB_HOST=127.0.0.1
SOURCE_DB_PORT=3306
SOURCE_DB_CHARSET=gbk

# ==========================================
# 文件存储与监控路径
# ==========================================
# 标准 PDF 文件在服务器上的物理存储根路径
STANDARD_FILES_ROOT=/data/standards/downloads/
# Watch Daemon 监控的文件夹路径（用户上传/存放新 PDF 的地方）
WATCH_FOLDER=/data/standards/watch/

# ==========================================
# Celery 异步队列
# ==========================================
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

# ==========================================
# OCR (Tesseract) Linux 路径
# ==========================================
TESSERACT_CMD=/usr/bin/tesseract

# ==========================================
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
LLM_FALLBACK_THRESHOLD=0.8
```

*提示：在 Linux 系统中，可以使用 `which tesseract` 命令来查询 tesseract 的绝对路径，通常为 `/usr/bin/tesseract`。*

---

## ⚙ 第四步：配置后台默认执行 (systemd)

在 Linux 中，推荐为 **Celery Worker** 和 **Watch Daemon** 分别配置 systemd 服务，使其能够在后台自启、自动崩溃重启。

### 1. 创建 Celery 队列服务
创建服务文件 `/etc/systemd/system/qianyin-celery.service`：
```bash
sudo nano /etc/systemd/system/qianyin-celery.service
```
写入以下配置内容：
```ini
[Unit]
Description=QianYin Celery Worker Service
After=network.target redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/QianYin_abc
ExecStart=/opt/QianYin_abc/venv/bin/celery -A emis_core worker -l info
Restart=always
RestartSec=5
EnvironmentFile=/opt/QianYin_abc/.env

[Install]
WantedBy=multi-user.target
```

### 2. 创建 文件夹监控守护服务 (Watch Daemon)
创建服务文件 `/etc/systemd/system/qianyin-watch.service`：
```bash
sudo nano /etc/systemd/system/qianyin-watch.service
```
写入以下配置内容：
```ini
[Unit]
Description=QianYin Document Watch Daemon
After=network.target qianyin-celery.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/QianYin_abc
ExecStart=/opt/QianYin_abc/venv/bin/python manage.py watch_daemon
Restart=always
RestartSec=5
EnvironmentFile=/opt/QianYin_abc/.env

[Install]
WantedBy=multi-user.target
```

---

## 🏁 第五步：启动与启用开机自启

配置完成后，重新加载 systemd 配置，并启动两个后台服务：

```bash
# 重新加载配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start qianyin-celery
sudo systemctl start qianyin-watch

# 设置开机默认自启
sudo systemctl enable qianyin-celery
sudo systemctl enable qianyin-watch
```

### 🔍 监控服务运行状态
你可以通过以下命令检查服务是否正常启动：
```bash
# 查看 Celery 运行状态
sudo systemctl status qianyin-celery

# 查看 Watch Daemon 监控状态
sudo systemctl status qianyin-watch

# 查看实时运行日志
sudo journalctl -u qianyin-watch -f
sudo journalctl -u qianyin-celery -f
```

配置完成后，任何放入监视文件夹 (如 `/data/standards/watch/`) 的 PDF/DOCX 文件，都会触发后台的守护服务默认自动处理。
