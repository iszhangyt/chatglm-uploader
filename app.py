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

app = Flask(__name__, static_folder='static')
CORS(app)

# 创建上传历史存储目录
UPLOAD_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
UPLOAD_HISTORY_FILE = os.path.join(UPLOAD_HISTORY_DIR, 'history.json')
VERIFICATION_CONFIG_FILE = os.path.join(UPLOAD_HISTORY_DIR, 'verification.json')

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
        return jsonify({'status': 1, 'message': '未验证或验证已过期'}), 401
    
    if 'file' not in request.files:
        return jsonify({'status': 1, 'message': '没有文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 1, 'message': '没有选择文件'}), 400
    
    # 检查文件类型
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
        return jsonify({'status': 1, 'message': '不支持的文件类型'}), 400
    
    # 获取上传渠道
    channel = request.form.get('channel', 'chatglm')
    
    try:
        # 保存临时文件
        temp_file_name = f"temp_{uuid.uuid4().hex}{os.path.splitext(file.filename)[1]}"
        temp_file_path = os.path.join(UPLOAD_HISTORY_DIR, temp_file_name)
        file.save(temp_file_path)
        
        result = None
        
        # 根据不同的渠道进行上传
        if channel == 'jd':
            # 上传到京东图床
            result = upload_to_jd(temp_file_path, file)
        else:
            # 默认上传到ChatGLM服务器
            result = upload_to_chatglm(temp_file_path, file)
        
        # 清理临时文件
        try:
            os.remove(temp_file_path)
        except Exception as e:
            print(f"删除临时文件失败: {str(e)}")
        
        if not result:
            return jsonify({'status': 1, 'message': '上传失败'}), 500
        
        # 保存上传历史
        history = get_upload_history()
        history_item = {
            'id': str(uuid.uuid4()),
            'file_name': file.filename,
            'file_url': result['file_url'],
            'width': result.get('width', 0),
            'height': result.get('height', 0),
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
        # 确保临时文件被删除
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as remove_error:
                print(f"删除临时文件失败: {str(remove_error)}")
                
        return jsonify({'status': 1, 'message': f'上传失败: {str(e)}'}), 500

def upload_to_chatglm(temp_file_path, file):
    """上传到ChatGLM图床"""
    url = "https://chatglm.cn/chatglm/backend-api/assistant/file_upload"
    
    payload = {}
    response = None
    
    try:
        with open(temp_file_path, 'rb') as file_handle:
            files = [
                ('file', (file.filename, file_handle, file.content_type))
            ]
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'App-Name': 'chatglm',
                'Connection': 'keep-alive',
                'DNT': '1',
                'Origin': 'https://chatglm.cn',
            }
            
            response = requests.request("POST", url, headers=headers, data=payload, files=files)
    except Exception as e:
        print(f"ChatGLM上传请求失败: {str(e)}")
        return None
    
    if response.status_code != 200:
        print(f"ChatGLM上传失败: {response.text}")
        return None
    
    result = response.json()
    
    if result['status'] != 0:
        print(f"ChatGLM上传失败: {result['message']}")
        return None
    
    return {
        'file_url': result['result']['file_url'],
        'width': result['result']['width'],
        'height': result['result']['height']
    }

def upload_to_jd(temp_file_path, file):
    """上传到京东图床"""
    url = "https://pic.jd.com/0/32ac1cd9ca1543e2a9cce60a4c9be94e"
    
    try:
        with open(temp_file_path, 'rb') as file_handle:
            files = {
                'file': (file.filename, file_handle, file.content_type)
            }
            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
                'Origin': 'https://feedback.jd.com',
                'Referer': 'https://feedback.jd.com/',
                'Sec-Ch-Ua-Platform': 'Windows',
                'Sec-Ch-Ua-Mobile': '?0'
            }
            
            response = requests.post(url, headers=headers, files=files)
    except Exception as e:
        print(f"京东上传请求失败: {str(e)}")
        return None
    
    if response.status_code != 200:
        print(f"京东上传失败: {response.text}")
        return None
    
    try:
        result = response.json()
        
        if result['id'] != '1' or not result['msg']:
            print(f"京东上传失败: {result}")
            return None
        
        # 构建完整URL
        # 从响应结果可以看出，返回格式是 jfs/t1/276937/35/26005/100196/68075c62F71bbcbb5/62424d53b2551311.png
        # 需要正确构建完整URL，使用新的前缀
        file_url = f"https://img20.360buyimg.com/openfeedback/{result['msg']}"
        
        # 这里无法获取图片尺寸，设置为默认值
        return {
            'file_url': file_url,
            'width': 0,
            'height': 0
        }
    except Exception as e:
        print(f"解析京东上传响应失败: {str(e)}")
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

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5500) 