from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for
from flask_cors import CORS
import os
import json
import requests
from datetime import datetime
import uuid
import hashlib
import time
import secrets
import io
import tempfile
import mimetypes
from urllib.parse import urlparse
import re
from PIL import Image, UnidentifiedImageError
import random
import logging
from datetime import timedelta
from channels import channel_manager

app = Flask(__name__, static_folder='static')
CORS(app)

# 创建上传历史存储目录
UPLOAD_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
UPLOAD_HISTORY_FILE = os.path.join(UPLOAD_HISTORY_DIR, 'history.json')
VERIFICATION_CONFIG_FILE = os.path.join(UPLOAD_HISTORY_DIR, 'verification.json')
LOG_FILE = os.path.join(UPLOAD_HISTORY_DIR, 'app.log')

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

if not os.path.exists(UPLOAD_HISTORY_DIR):
    os.makedirs(UPLOAD_HISTORY_DIR)

if not os.path.exists(UPLOAD_HISTORY_FILE):
    with open(UPLOAD_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

# 创建或加载验证配置
def init_verification_config():
    if not os.path.exists(VERIFICATION_CONFIG_FILE):
        # 创建默认验证码和盐值
        default_code = "admin123"
        default_salt = secrets.token_hex(16)
        
        # 计算哈希值
        hash_obj = hashlib.sha256((default_code + default_salt).encode())
        hashed_code = hash_obj.hexdigest()
        
        verification_config = {
            "code_hash": hashed_code,
            "salt": default_salt,
            "valid_tokens": {}
        }
        
        with open(VERIFICATION_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(verification_config, f, ensure_ascii=False, indent=2)
        
        return verification_config
    else:
        try:
            with open(VERIFICATION_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            # 如果文件损坏，重新创建
            os.remove(VERIFICATION_CONFIG_FILE)
            return init_verification_config()

# 保存验证配置
def save_verification_config(config):
    with open(VERIFICATION_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# 读取上传历史
def get_upload_history():
    try:
        with open(UPLOAD_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

# 保存上传历史
def save_upload_history(history):
    with open(UPLOAD_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# 生成token
def generate_token():
    return secrets.token_hex(32)

# 验证token是否有效
def verify_token(token):
    config = init_verification_config()
    if token in config["valid_tokens"]:
        # 检查token是否过期（这里可以设置过期时间，比如30天）
        return True
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
    config = init_verification_config()
    
    # 验证码验证
    hash_obj = hashlib.sha256((code + config["salt"]).encode())
    hashed_code = hash_obj.hexdigest()
    
    if hashed_code != config["code_hash"]:
        return jsonify({'status': 1, 'message': '验证码错误'}), 401
    
    # 生成新的token
    token = generate_token()
    
    # 保存token
    config["valid_tokens"][token] = {
        "created_at": time.time(),
        "expires_at": time.time() + 30 * 24 * 60 * 60  # 30天有效期
    }
    
    save_verification_config(config)
    
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
        temp_file_path = os.path.join(UPLOAD_HISTORY_DIR, temp_file_name)
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
        history = get_upload_history()
        history_item = {
            'id': str(uuid.uuid4()),
            'file_name': file.filename,
            'file_url': result['file_url'],
            'width': result.get('width', validated_file.width),
            'height': result.get('height', validated_file.height),
            'channel': channel,
            'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        history.insert(0, history_item)
        save_upload_history(history)
        
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
            history = get_upload_history()
            history_item = {
                'id': str(uuid.uuid4()),
                'file_name': file_name,
                'file_url': result['file_url'],
                'width': result.get('width', validated_file.width),
                'height': result.get('height', validated_file.height),
                'channel': channel,
                'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            history.insert(0, history_item)
            save_upload_history(history)
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
    
    history = get_upload_history()
    new_history = [item for item in history if item['id'] != item_id]
    
    if len(history) == len(new_history):
        return jsonify({'status': 1, 'message': '找不到指定记录'}), 404
    
    save_upload_history(new_history)
    return jsonify({'status': 0, 'message': '删除成功'})

@app.route('/clear_history', methods=['DELETE'])
def clear_history():
    # 验证token
    token = request.headers.get('X-Verification-Token')
    if not token or not verify_token(token):
        return jsonify({'status': 1, 'message': '未验证或验证已过期'}), 401
    
    save_upload_history([])
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