from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_compress import Compress
import os
import json
import requests
from datetime import datetime
import uuid
import hashlib
import time
import secrets
import tempfile
import mimetypes
from urllib.parse import urlparse
import re
from PIL import Image, UnidentifiedImageError
import random
import logging
from channels import channel_manager
import sqlite3
from contextlib import contextmanager

app = Flask(__name__, static_folder='static')
CORS(app)
Compress(app)  # 启用Gzip压缩

# 创建数据存储目录
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DATABASE_FILE = os.path.join(DATA_DIR, 'app.db')  # SQLite数据库文件
LOG_FILE = os.path.join(DATA_DIR, 'app.log')
# 旧JSON文件路径（用于数据迁移）
OLD_HISTORY_JSON = os.path.join(DATA_DIR, 'history.json')
OLD_VERIFICATION_JSON = os.path.join(DATA_DIR, 'verification.json')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('image_uploader')

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ==================== SQLite 数据库操作 ====================

def init_database():
    """初始化SQLite数据库，创建表和索引"""
    conn = sqlite3.connect(DATABASE_FILE)
    # 启用WAL模式，支持并发读取，提高性能
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')  # 平衡性能和安全性
    conn.execute('PRAGMA cache_size=10000')  # 增加缓存
    
    # 上传历史表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS upload_history (
            id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_url TEXT NOT NULL,
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            channel TEXT,
            upload_time TEXT NOT NULL
        )
    ''')
    # 创建按上传时间降序的索引，加速查询
    conn.execute('CREATE INDEX IF NOT EXISTS idx_upload_time ON upload_history(upload_time DESC)')

    # 数据库迁移：为已存在的表添加 file_size 列（如果不存在）
    cursor = conn.execute('PRAGMA table_info(upload_history)')
    columns = [column[1] for column in cursor.fetchall()]
    if 'file_size' not in columns:
        conn.execute('ALTER TABLE upload_history ADD COLUMN file_size INTEGER DEFAULT 0')

    # 验证配置表（存储验证码哈希和盐值）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS verification_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            code_hash TEXT NOT NULL,
            salt TEXT NOT NULL
        )
    ''')
    
    # 有效token表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS valid_tokens (
            token TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
    ''')
    # 创建过期时间索引，方便清理过期token
    conn.execute('CREATE INDEX IF NOT EXISTS idx_expires_at ON valid_tokens(expires_at)')
    
    conn.commit()
    conn.close()
    
    # 迁移旧的JSON数据
    migrate_from_json()
    migrate_verification_from_json()

def migrate_from_json():
    """从旧的JSON文件迁移数据到SQLite"""
    if not os.path.exists(OLD_HISTORY_JSON):
        return
    
    try:
        with open(OLD_HISTORY_JSON, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        if not history:
            # 空文件，直接备份
            os.rename(OLD_HISTORY_JSON, OLD_HISTORY_JSON + '.bak')
            return
        
        conn = sqlite3.connect(DATABASE_FILE)
        migrated_count = 0
        for item in history:
            try:
                conn.execute('''
                    INSERT OR IGNORE INTO upload_history 
                    (id, file_name, file_url, width, height, channel, upload_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    item['id'], 
                    item['file_name'], 
                    item['file_url'],
                    item.get('width', 0), 
                    item.get('height', 0), 
                    item.get('channel', ''),
                    item['upload_time']
                ))
                migrated_count += 1
            except Exception as e:
                logging.warning(f"迁移记录失败: {item.get('id', 'unknown')}, 错误: {str(e)}")
        
        conn.commit()
        conn.close()
        
        # 备份旧文件
        os.rename(OLD_HISTORY_JSON, OLD_HISTORY_JSON + '.bak')
        logging.info(f"已将 {migrated_count} 条历史记录迁移到SQLite数据库")
    except Exception as e:
        logging.error(f"迁移历史记录失败: {str(e)}")

def migrate_verification_from_json():
    """从旧的JSON文件迁移验证配置到SQLite"""
    if not os.path.exists(OLD_VERIFICATION_JSON):
        return
    
    try:
        with open(OLD_VERIFICATION_JSON, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        conn = sqlite3.connect(DATABASE_FILE)
        
        # 检查是否已有配置
        cursor = conn.execute('SELECT COUNT(*) FROM verification_config')
        if cursor.fetchone()[0] == 0:
            # 迁移验证码配置
            conn.execute(
                'INSERT INTO verification_config (id, code_hash, salt) VALUES (1, ?, ?)',
                (config.get('code_hash', ''), config.get('salt', ''))
            )
        
        # 迁移有效token
        valid_tokens = config.get('valid_tokens', {})
        for token, token_info in valid_tokens.items():
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO valid_tokens (token, created_at, expires_at) VALUES (?, ?, ?)',
                    (token, token_info.get('created_at', 0), token_info.get('expires_at', 0))
                )
            except Exception as e:
                logging.warning(f"迁移token失败: {token[:8]}..., 错误: {str(e)}")
        
        conn.commit()
        conn.close()
        
        # 备份旧文件
        os.rename(OLD_VERIFICATION_JSON, OLD_VERIFICATION_JSON + '.bak')
        logging.info(f"已将验证配置迁移到SQLite数据库，包含 {len(valid_tokens)} 个token")
    except Exception as e:
        logging.error(f"迁移验证配置失败: {str(e)}")

@contextmanager
def get_db_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(DATABASE_FILE, timeout=10)
    conn.row_factory = sqlite3.Row  # 返回字典形式的结果
    try:
        yield conn
    finally:
        conn.close()

def get_upload_history():
    """获取所有上传历史"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            'SELECT id, file_name, file_url, width, height, file_size, channel, upload_time '
            'FROM upload_history ORDER BY upload_time DESC'
        )
        return [dict(row) for row in cursor.fetchall()]

def add_upload_history(item):
    """添加一条上传历史"""
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO upload_history
            (id, file_name, file_url, width, height, file_size, channel, upload_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item['id'],
            item['file_name'],
            item['file_url'],
            item.get('width', 0),
            item.get('height', 0),
            item.get('file_size', 0),
            item.get('channel', ''),
            item['upload_time']
        ))
        conn.commit()

def delete_history_by_id(item_id):
    """删除一条上传历史，返回是否删除成功"""
    with get_db_connection() as conn:
        cursor = conn.execute('DELETE FROM upload_history WHERE id = ?', (item_id,))
        conn.commit()
        return cursor.rowcount > 0

def clear_all_history():
    """清空所有上传历史"""
    with get_db_connection() as conn:
        conn.execute('DELETE FROM upload_history')
        conn.commit()

# 初始化数据库
init_database()

# ==================== 验证配置 ====================

def get_verification_config():
    """获取验证配置（验证码哈希和盐值）"""
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT code_hash, salt FROM verification_config WHERE id = 1')
        row = cursor.fetchone()
        if row:
            return {'code_hash': row['code_hash'], 'salt': row['salt']}
        return None

def init_verification_config():
    """初始化验证配置（如果不存在则创建默认配置）"""
    config = get_verification_config()
    if config:
        return config
    
    # 创建默认验证码和盐值
    default_code = "admin123"
    default_salt = secrets.token_hex(16)
    
    # 计算哈希值
    hash_obj = hashlib.sha256((default_code + default_salt).encode())
    hashed_code = hash_obj.hexdigest()
    
    with get_db_connection() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO verification_config (id, code_hash, salt) VALUES (1, ?, ?)',
            (hashed_code, default_salt)
        )
        conn.commit()
    
    return {'code_hash': hashed_code, 'salt': default_salt}

def generate_token():
    """生成新的验证token"""
    return secrets.token_hex(32)

def add_valid_token(token, created_at, expires_at):
    """添加有效token到数据库"""
    with get_db_connection() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO valid_tokens (token, created_at, expires_at) VALUES (?, ?, ?)',
            (token, created_at, expires_at)
        )
        conn.commit()

def verify_token(token):
    """验证token是否有效"""
    if not token:
        return False
    
    current_time = time.time()
    with get_db_connection() as conn:
        cursor = conn.execute(
            'SELECT expires_at FROM valid_tokens WHERE token = ?',
            (token,)
        )
        row = cursor.fetchone()
        if row:
            # 检查是否过期
            if row['expires_at'] > current_time:
                return True
            else:
                # 已过期，删除该token
                conn.execute('DELETE FROM valid_tokens WHERE token = ?', (token,))
                conn.commit()
    return False

# 初始化验证配置
init_verification_config()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/verify')
def verify_page():
    return render_template('verify.html')

@app.route('/history_page')
def history_page():
    return render_template('history.html')

@app.route('/api/verify', methods=['POST'])
def verify():
    data = request.json
    if not data or 'code' not in data:
        return jsonify({'status': 1, 'message': '无效的请求'}), 400
    
    code = data['code']
    config = get_verification_config()
    
    if not config:
        # 配置不存在，初始化
        config = init_verification_config()
    
    # 验证码验证
    hash_obj = hashlib.sha256((code + config["salt"]).encode())
    hashed_code = hash_obj.hexdigest()
    
    if hashed_code != config["code_hash"]:
        return jsonify({'status': 1, 'message': '验证码错误'}), 401
    
    # 生成新的token
    token = generate_token()
    
    # 保存token到数据库
    current_time = time.time()
    expires_at = current_time + 30 * 24 * 60 * 60  # 30天有效期
    add_valid_token(token, current_time, expires_at)
    
    return jsonify({'status': 0, 'message': '验证成功', 'token': token})

@app.route('/api/check_verification', methods=['POST'])
def check_verification():
    data = request.json
    if not data or 'token' not in data:
        return jsonify({'status': 1, 'message': '无效的请求'}), 400
    
    token = data['token']
    
    if verify_token(token):
        return jsonify({'status': 0, 'message': '验证有效'})
    else:
        return jsonify({'status': 1, 'message': '验证已过期或无效'}), 401

@app.route('/upload', methods=['POST'])
def upload_image():
    # 验证token
    token = request.headers.get('X-Verification-Token')
    if not token or not verify_token(token):
        logger.warning("上传请求验证失败: token无效或已过期")
        return jsonify({'status': 1, 'message': '未验证或验证已过期'}), 401
    
    if 'file' not in request.files:
        logger.warning("上传请求缺少文件")
        return jsonify({'status': 1, 'message': '没有文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        logger.warning("上传请求文件名为空")
        return jsonify({'status': 1, 'message': '没有选择文件'}), 400
    
    # 检查文件类型
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
        logger.warning(f"不支持的文件类型: {file.filename}")
        return jsonify({'status': 1, 'message': '请选择支持的图片格式：JPG, PNG, GIF, BMP, WEBP'}), 400
    
    # 获取上传渠道
    channel = request.form.get('channel', channel_manager.get_default_channel_name())
    logger.info(f"开始上传: 文件={file.filename}, 渠道={channel}")
    
    try:
        # 保存临时文件
        temp_file_name = f"temp_{uuid.uuid4().hex}{os.path.splitext(file.filename)[1]}"
        temp_file_path = os.path.join(DATA_DIR, temp_file_name)
        file.save(temp_file_path)
        
        # 获取文件大小
        file_size = os.path.getsize(temp_file_path)
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"临时文件已保存: {temp_file_path}, 大小: {file_size_mb:.2f}MB")
        
        # 验证图片并获取正确的content_type和尺寸信息
        img_info = validate_image(temp_file_path, file.filename)
        if not img_info:
            # 清理临时文件
            try:
                os.remove(temp_file_path)
            except Exception as e:
                logger.error(f"删除临时文件失败: {str(e)}")
            logger.warning(f"图片验证失败: {file.filename}")
            return jsonify({'status': 1, 'message': '无效的图片文件，请确保提供支持的图片格式：JPG, PNG, GIF, BMP, WEBP'}), 400
        
        logger.info(f"图片验证通过: {file.filename}, 尺寸: {img_info['width']}x{img_info['height']}, 格式: {img_info['format']}")
        
        # 创建包含验证后信息的文件对象
        class ValidatedFile:
            def __init__(self, original_file, img_info):
                self.filename = original_file.filename
                self.content_type = img_info['content_type']
                self.width = img_info['width']
                self.height = img_info['height']
        
        validated_file = ValidatedFile(file, img_info)
        result = None
        
        # 根据不同的渠道进行上传
        uploader = channel_manager.get_channel(channel)
        if not uploader:
            # 如果渠道不存在，使用默认渠道
            uploader = channel_manager.get_default_channel()
            logger.warning(f"渠道 {channel} 不存在，使用默认渠道 {uploader.get_channel_name()}")
        
        # 检查文件大小限制
        size_ok, size_error = uploader.check_file_size(temp_file_path)
        if not size_ok:
            logger.warning(f"文件大小超出限制: {file.filename}, {file_size_mb:.2f}MB, 渠道: {uploader.get_channel_name()}")
            # 清理临时文件
            try:
                os.remove(temp_file_path)
            except Exception as e:
                logger.error(f"删除临时文件失败: {str(e)}")
            return jsonify({'status': 1, 'message': size_error}), 400
        
        logger.info(f"开始上传到渠道: {uploader.get_channel_name()}")
        result = uploader.upload(temp_file_path, validated_file)
        
        # 清理临时文件
        try:
            os.remove(temp_file_path)
        except Exception as e:
            logger.error(f"删除临时文件失败: {str(e)}")
        
        if not result:
            logger.error(f"上传失败: 文件={file.filename}, 渠道={uploader.get_channel_name()}, 原因=渠道返回空结果")
            return jsonify({'status': 1, 'message': f'上传到{uploader.get_channel_name()}失败，请检查渠道配置或稍后重试'}), 500
        
        logger.info(f"上传成功: 文件={file.filename}, 渠道={uploader.get_channel_name()}, URL={result['file_url']}")
        
        # 保存上传历史
        history_item = {
            'id': str(uuid.uuid4()),
            'file_name': file.filename,
            'file_url': result['file_url'],
            'width': result.get('width', validated_file.width),
            'height': result.get('height', validated_file.height),
            'file_size': file_size,
            'channel': channel,
            'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        add_upload_history(history_item)
        
        return jsonify({
            'status': 0,
            'message': '上传成功',
            'result': result
        })
    except Exception as e:
        logger.error(f"上传异常: 文件={file.filename if 'file' in locals() else '未知'}, 错误={str(e)}", exc_info=True)
        # 确保临时文件被删除
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as remove_error:
                logger.error(f"删除临时文件失败: {str(remove_error)}")
                
        return jsonify({'status': 1, 'message': f'上传失败: {str(e)}'}), 500

@app.route('/upload_from_url', methods=['POST'])
def upload_from_url():
    # 临时文件路径，用于在出现异常时清理
    temp_file_path = None
    
    # 验证token
    token = request.headers.get('X-Verification-Token')
    if not token or not verify_token(token):
        logger.warning("URL上传请求验证失败: token无效或已过期")
        return jsonify({'status': 1, 'message': '未验证或验证已过期'}), 401
    
    # 解析请求数据
    data = request.json
    if not data or 'url' not in data:
        logger.warning("URL上传请求缺少URL参数")
        return jsonify({'status': 1, 'message': '无效的请求参数'}), 400
    
    url = data['url'].strip()
    if not url:
        logger.warning("URL上传请求URL为空")
        return jsonify({'status': 1, 'message': '图片URL不能为空'}), 400
    
    # 简单验证URL格式
    if not url.startswith(('http://', 'https://')):
        logger.warning(f"无效的URL格式: {url}")
        return jsonify({'status': 1, 'message': '无效的URL格式，必须以http://或https://开头'}), 400
    
    channel = data.get('channel', channel_manager.get_default_channel_name())
    logger.info(f"开始URL上传: URL={url[:100]}{'...' if len(url) > 100 else ''}, 渠道={channel}")
    
    try:
        # 配置代理（如果需要）
        proxies = None
        # 如果需要使用代理，可以取消下面注释并修改代理地址
        # proxies = {
        #     'http': 'http://your-proxy:port',
        #     'https': 'http://your-proxy:port'
        # }
        
        # 根据域名设置特定的请求头
        headers, domain, base_domain = generate_request_headers(url)
        
        # 一些网站需要Cookie
        cookies = None
        if 'pixiv' in domain:
            # 这里可以添加pixiv的cookies，如果有的话
            # cookies = {'PHPSESSID': 'your_session_id'}
            pass
        
        # 下载图片 - 添加重试机制和指数退避策略
        max_retries = 3
        retry_delay = 1.0  # 初始延迟1秒
        last_error = None
        
        for retry in range(max_retries):
            try:
                if retry > 0:
                    logger.info(f"重试下载 ({retry}/{max_retries}): {url}")
                    # 指数退避，每次重试增加延迟
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    
                    # 重试时可能需要更新请求头
                    if retry > 1:
                        # 为了更好地模拟真实浏览器，重新生成请求头
                        headers, _, _ = generate_request_headers(url)
                
                # 发起请求下载图片
                response = requests.get(url, stream=True, timeout=30, proxies=proxies, headers=headers, cookies=cookies)
                response.raise_for_status()  # 确保请求成功
                
                # 如果成功获取内容，跳出重试循环
                if response.content:
                    logger.info(f"成功下载图片: {url}")
                    break
                    
                # 内容为空，继续重试
                last_error = ValueError("下载的图片内容为空")
                logger.warning(f"下载内容为空，将重试: {url}")
                continue
                
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"下载超时，准备重试: {url}")
                continue
            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(f"连接错误，准备重试: {url}")
                continue
            except requests.exceptions.HTTPError as e:
                # 对于403 Forbidden或401 Unauthorized，可能是防盗链问题
                if e.response.status_code in (403, 401):
                    last_error = e
                    logger.warning(f"访问被拒绝 (HTTP {e.response.status_code})，尝试调整请求头: {url}")
                    
                    # 记录当前的请求头，帮助调试
                    logger.debug(f"当前请求头: {headers}")
                    
                    # 对于被拒绝的请求，尝试使用更通用的请求头或空Referer
                    if retry == 1:
                        headers['Referer'] = url  # 使用自身URL作为Referer
                        logger.debug(f"尝试使用自身URL作为Referer: {url}")
                    elif retry == 2:
                        # 最后一次尝试，删除Referer
                        if 'Referer' in headers:
                            del headers['Referer']
                            logger.debug("尝试删除Referer头")
                    continue
                else:
                    raise  # 其他HTTP错误直接抛出
            except Exception as e:
                last_error = e
                # 其他错误，如果有重试次数就继续
                if retry < max_retries - 1:
                    logger.warning(f"下载出错，准备重试: {url}, 错误: {str(e)}")
                    continue
                raise  # 用完重试次数，重新抛出异常
        
        # 用完所有重试次数仍然失败
        if last_error is not None and 'response' not in locals():
            if isinstance(last_error, requests.exceptions.Timeout):
                return jsonify({'status': 1, 'message': '下载图片超时，请检查URL或稍后重试'}), 400
            elif isinstance(last_error, requests.exceptions.ConnectionError):
                return jsonify({'status': 1, 'message': '连接错误，无法访问图片URL'}), 400
            elif isinstance(last_error, requests.exceptions.HTTPError):
                return jsonify({'status': 1, 'message': f'HTTP错误: {last_error.response.status_code}'}), 400
            else:
                return jsonify({'status': 1, 'message': f'下载图片失败: {str(last_error)}'}), 400
        
        # 检查响应是否为空
        if not response.content:
            return jsonify({'status': 1, 'message': '下载的图片内容为空'}), 400
            
        # 检查内容类型
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            # 如果服务器没有返回正确的content-type，尝试通过URL的扩展名判断
            ext = os.path.splitext(url.split('?')[0])[1].lower()
            if ext and ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                # URL有有效的图片扩展名，我们可以继续处理
                content_type = mimetypes.guess_type(url)[0] or 'image/jpeg'
            else:
                # 尝试通过魔术字节来判断文件类型
                magic_bytes = response.content[:12]
                if (magic_bytes.startswith(b'\xff\xd8\xff') or  # JPEG
                    magic_bytes.startswith(b'\x89PNG\r\n\x1a\n') or  # PNG
                    magic_bytes.startswith(b'GIF8') or  # GIF
                    magic_bytes.startswith(b'RIFF') or  # WEBP
                    magic_bytes.startswith(b'BM')):  # BMP
                    # 推测内容类型
                    if magic_bytes.startswith(b'\xff\xd8\xff'):
                        content_type = 'image/jpeg'
                        ext = '.jpg'
                    elif magic_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                        content_type = 'image/png'
                        ext = '.png'
                    elif magic_bytes.startswith(b'GIF8'):
                        content_type = 'image/gif'
                        ext = '.gif'
                    elif magic_bytes.startswith(b'RIFF'):
                        content_type = 'image/webp'
                        ext = '.webp'
                    elif magic_bytes.startswith(b'BM'):
                        content_type = 'image/bmp'
                        ext = '.bmp'
                else:
                    return jsonify({'status': 1, 'message': '链接内容不是有效的图片'}), 400
        else:
            # 从content_type中提取扩展名
            ext_map = {
                'image/jpeg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'image/bmp': '.bmp'
            }
            ext = ext_map.get(content_type, '.jpg')
        
        try:
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            temp_file_path = temp_file.name
            
            # 将图片内容写入临时文件
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_file.close()
        except Exception as e:
            return jsonify({'status': 1, 'message': f'创建临时文件失败: {str(e)}'}), 400
        
        # 验证图片并获取正确的content_type和尺寸信息
        img_info = validate_image(temp_file_path, "从URL下载")
        if not img_info:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    logger.error(f"删除临时文件失败: {str(e)}")
            return jsonify({'status': 1, 'message': '下载的文件不是支持的图片格式：JPG, PNG, GIF, BMP, WEBP'}), 400
        
        # 处理文件名 - 控制长度
        try:
            # 从URL中提取文件名
            original_name = url.split('/')[-1].split('?')[0]
            
            # 去除文件扩展名以处理基础名称
            base_name = os.path.splitext(original_name)[0]
            
            # 限制基础名称长度，最多保留30个字符
            if len(base_name) > 30:
                base_name = base_name[:30]
            
            # 如果基础名称为空或太短，生成一个随机名称
            if not base_name or len(base_name) < 3:
                base_name = f"img_{uuid.uuid4().hex[:8]}"
                
            # 使用验证后的扩展名构建最终文件名
            file_name = f"{base_name}{img_info['extension']}"
        except Exception:
            # 如果文件名处理出错，使用安全的默认名称
            file_name = f"image_{uuid.uuid4().hex[:8]}{img_info['extension']}"
        
        # 创建包含验证后信息的文件对象
        class ValidatedFile:
            def __init__(self, filename, img_info):
                self.filename = filename
                self.content_type = img_info['content_type']
                self.width = img_info['width'] 
                self.height = img_info['height']
        
        validated_file = ValidatedFile(file_name, img_info)
        
        # 获取文件大小
        file_size = os.path.getsize(temp_file_path)
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"URL图片下载完成: 大小={file_size_mb:.2f}MB, 尺寸={img_info['width']}x{img_info['height']}")
        
        # 传递验证后的文件对象到上传函数
        result = None
        
        # 根据不同的渠道进行上传
        try:
            uploader = channel_manager.get_channel(channel)
            if not uploader:
                # 如果渠道不存在，使用默认渠道
                uploader = channel_manager.get_default_channel()
                logger.warning(f"渠道 {channel} 不存在，使用默认渠道 {uploader.get_channel_name()}")
            
            # 检查文件大小限制
            size_ok, size_error = uploader.check_file_size(temp_file_path)
            if not size_ok:
                logger.warning(f"URL上传文件大小超出限制: {file_size_mb:.2f}MB, 渠道={uploader.get_channel_name()}")
                return jsonify({'status': 1, 'message': size_error}), 400
            
            logger.info(f"开始上传到渠道: {uploader.get_channel_name()}")
            result = uploader.upload(temp_file_path, validated_file)
                
            if not result:
                logger.error(f"URL上传失败: 渠道={uploader.get_channel_name()}, 原因=渠道返回空结果")
                return jsonify({'status': 1, 'message': f'上传到{uploader.get_channel_name()}失败，请检查渠道配置或稍后重试'}), 400
        except Exception as e:
            logger.error(f"URL上传异常: 渠道={channel}, 错误={str(e)}", exc_info=True)
            return jsonify({'status': 1, 'message': f'上传图片时发生错误: {str(e)}'}), 400
        finally:
            # 确保无论如何都清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    logger.error(f"删除临时文件失败: {str(e)}")
        
        logger.info(f"URL上传成功: 渠道={uploader.get_channel_name()}, URL={result['file_url']}")
        
        # 保存上传历史
        try:
            history_item = {
                'id': str(uuid.uuid4()),
                'file_name': file_name,
                'file_url': result['file_url'],
                'width': result.get('width', validated_file.width),
                'height': result.get('height', validated_file.height),
                'file_size': file_size,
                'channel': channel,
                'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            add_upload_history(history_item)
        except Exception as e:
            logger.error(f"保存历史记录失败: {str(e)}")
            # 不阻止返回上传成功的结果
        
        return jsonify({
            'status': 0,
            'message': '上传成功',
            'result': {
                'file_url': result['file_url'],
                'width': result.get('width', 0),
                'height': result.get('height', 0)
            }
        })
    
    except Exception as e:
        logger.error(f"URL上传处理异常: URL={url[:100] if 'url' in locals() else '未知'}, 错误={str(e)}", exc_info=True)
        # 确保临时文件被删除
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        
        return jsonify({'status': 1, 'message': f'处理失败: {str(e)}'}), 400

def validate_image(file_path, original_filename=None):
    """
    验证文件是否为有效图片，并返回正确的content_type和图片信息
    
    参数:
        file_path: 图片文件的路径
        original_filename: 原始文件名，用于记录日志
        
    返回:
        dict: 包含content_type, width, height等信息的字典，如果验证失败则返回None
    """
    try:
        # 使用PIL打开图片以验证是否为有效图片
        img = Image.open(file_path)
        
        # 获取图片格式和尺寸
        img_format = img.format.lower() if img.format else None
        width, height = img.size
        
        # 验证图片格式是否为支持的类型
        supported_formats = {'jpeg': 'image/jpeg', 'jpg': 'image/jpeg', 'png': 'image/png', 
                           'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp'}
        
        if not img_format or img_format.lower() not in supported_formats:
            logger.warning(f"不支持的图片格式: {img_format}, 文件: {original_filename}")
            return None
            
        # 获取正确的content_type
        content_type = supported_formats.get(img_format.lower(), 'image/jpeg')
        
        # 构建图片信息
        img_info = {
            'content_type': content_type,
            'width': width,
            'height': height,
            'format': img_format.lower()
        }
        
        # 确定扩展名
        ext_map = {
            'jpeg': '.jpg',
            'jpg': '.jpg',
            'png': '.png',
            'gif': '.gif',
            'webp': '.webp',
            'bmp': '.bmp'
        }
        img_info['extension'] = ext_map.get(img_format.lower(), '.jpg')
        
        logger.info(f"图片验证成功: {original_filename}, 格式: {img_format}, 尺寸: {width}x{height}")
        return img_info
    except UnidentifiedImageError:
        logger.error(f"无法识别的图片: {original_filename}")
        return None
    except Exception as e:
        logger.error(f"验证图片时出错: {str(e)}, 文件: {original_filename}")
        return None


@app.route('/history', methods=['GET'])
def get_history():
    # 验证token
    token = request.headers.get('X-Verification-Token')
    if not token or not verify_token(token):
        return jsonify({'status': 1, 'message': '未验证或验证已过期'}), 401
    
    history = get_upload_history()
    return jsonify({'status': 0, 'message': 'success', 'result': history})

@app.route('/delete_history/<item_id>', methods=['DELETE'])
def delete_history_item(item_id):
    # 验证token
    token = request.headers.get('X-Verification-Token')
    if not token or not verify_token(token):
        return jsonify({'status': 1, 'message': '未验证或验证已过期'}), 401
    
    if delete_history_by_id(item_id):
        return jsonify({'status': 0, 'message': '删除成功'})
    else:
        return jsonify({'status': 1, 'message': '找不到指定记录'}), 404

@app.route('/clear_history', methods=['DELETE'])
def clear_history():
    # 验证token
    token = request.headers.get('X-Verification-Token')
    if not token or not verify_token(token):
        return jsonify({'status': 1, 'message': '未验证或验证已过期'}), 401
    
    clear_all_history()
    return jsonify({'status': 0, 'message': '清除成功'})

def generate_request_headers(url, use_smart_referer=True):
    """
    生成用于图片下载的请求头，智能处理防盗链
    
    参数:
        url: 请求的URL
        use_smart_referer: 是否使用智能Referer策略
        
    返回:
        dict: 包含所需请求头的字典
    """
    # 解析URL获取域信息
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()
    scheme = parsed_url.scheme
    path = parsed_url.path
    
    # 基础域名 (例如从 image.example.com 得到 example.com)
    base_domain = '.'.join(domain.split('.')[-2:]) if len(domain.split('.')) > 1 else domain
    
    # 现代浏览器的User-Agent列表
    modern_user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Arm Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:133.0) Gecko/20100101 Firefox/133.0',
        'Mozilla/5.0 (Macintosh; Arm Mac OS X 14.4; rv:133.0) Gecko/20100101 Firefox/133.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/618.1.15 (KHTML, like Gecko) Version/17.4 Safari/618.1.15',
        'Mozilla/5.0 (Macintosh; Arm Mac OS X 14_4) AppleWebKit/618.1.15 (KHTML, like Gecko) Version/17.4 Safari/618.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.2550.0'
    ]
    
    # 随机选择一个User-Agent
    user_agent = random.choice(modern_user_agents)
    
    # 基础请求头
    headers = {
        'User-Agent': user_agent,
        'Accept': 'image/png,image/jpeg,image/jpg,image/webp;q=0.9,image/gif;q=0.8,image/bmp;q=0.7,image/*;q=0.6,*/*;q=0.5',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Fetch-Dest': 'image',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'cross-site',
    }
    
    # 特定站点规则 - 常见的有防盗链机制的网站
    # 格式: 'domain': {'referer': 'referer_url', 'origin': 'origin_url', 'extra_headers': {}}
    site_rules = {
        # 像素画/插画网站
        'pixiv.net': {
            'referer': 'https://www.pixiv.net/',
            'origin': 'https://www.pixiv.net',
            'use_id_in_referer': True,
            'id_pattern': r'/(\d+)',  # 可以是任何正则表达式
            'id_template': 'https://www.pixiv.net/artworks/{}'
        },
        'pximg.net': {
            'referer': 'https://www.pixiv.net/',
            'origin': 'https://www.pixiv.net',
            'use_id_in_referer': True,
            'id_pattern': r'/(\d+)',
            'id_template': 'https://www.pixiv.net/artworks/{}'
        },
        
        # Pinterest
        'pinimg.com': {
            'referer': 'https://www.pinterest.com/',
            'origin': 'https://www.pinterest.com'
        },
        
        # Twitter/X图片
        'twimg.com': {
            'referer': 'https://twitter.com/',
            'origin': 'https://twitter.com'
        },
        
        # Instagram
        'cdninstagram.com': {
            'referer': 'https://www.instagram.com/',
            'origin': 'https://www.instagram.com'
        },
        
        # 微博
        'sinaimg.cn': {
            'referer': 'https://weibo.com/',
            'origin': 'https://weibo.com'
        },
        
        # 知乎
        'zhimg.com': {
            'referer': 'https://www.zhihu.com/',
            'origin': 'https://www.zhihu.com'
        }
    }
    
    # 使用智能Referer策略
    if use_smart_referer:
        # 默认使用链接自身的域名作为referer
        smart_referer = f"{scheme}://{domain}/"
        
        # 对于CDN或媒体子域，尝试使用主域作为referer
        if domain.startswith(('img.', 'image.', 'media.', 'assets.', 'static.', 'cdn.')):
            smart_referer = f"{scheme}://{base_domain}/"
        
        headers['Referer'] = smart_referer
    
    # 应用特定站点规则
    for site_domain, rules in site_rules.items():
        if site_domain in domain:
            # 基本referer和origin
            headers['Referer'] = rules.get('referer', smart_referer)
            if 'origin' in rules:
                headers['Origin'] = rules['origin']
                headers['Sec-Fetch-Site'] = 'same-site'
            
            # 如果需要使用ID进行referer处理
            if rules.get('use_id_in_referer', False) and 'id_pattern' in rules:
                id_match = re.search(rules['id_pattern'], path)
                if id_match and 'id_template' in rules:
                    content_id = id_match.group(1)
                    headers['Referer'] = rules['id_template'].format(content_id)
            
            # 添加额外的头部
            if 'extra_headers' in rules:
                headers.update(rules['extra_headers'])
            
            break
    
    return headers, domain, base_domain

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5500) 