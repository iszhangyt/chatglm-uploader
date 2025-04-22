from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import os
import json
import requests
from datetime import datetime
import uuid

app = Flask(__name__, static_folder='static')
CORS(app)

# 创建上传历史存储目录
UPLOAD_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
UPLOAD_HISTORY_FILE = os.path.join(UPLOAD_HISTORY_DIR, 'history.json')

if not os.path.exists(UPLOAD_HISTORY_DIR):
    os.makedirs(UPLOAD_HISTORY_DIR)

if not os.path.exists(UPLOAD_HISTORY_FILE):
    with open(UPLOAD_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'status': 1, 'message': '没有文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 1, 'message': '没有选择文件'}), 400
    
    # 检查文件类型
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
        return jsonify({'status': 1, 'message': '不支持的文件类型'}), 400
    
    try:
        # 保存临时文件
        temp_file_name = f"temp_{uuid.uuid4().hex}{os.path.splitext(file.filename)[1]}"
        temp_file_path = os.path.join(UPLOAD_HISTORY_DIR, temp_file_name)
        file.save(temp_file_path)
        
        # 上传到ChatGLM服务器
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
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as remove_error:
                    print(f"删除临时文件失败: {str(remove_error)}")
            return jsonify({'status': 1, 'message': f'上传请求失败: {str(e)}'}), 500
        
        # 清理临时文件
        try:
            os.remove(temp_file_path)
        except Exception as e:
            print(f"删除临时文件失败: {str(e)}")
        
        if response.status_code != 200:
            return jsonify({'status': 1, 'message': f'上传失败: {response.text}'}), 500
        
        result = response.json()
        
        if result['status'] != 0:
            return jsonify({'status': 1, 'message': f'上传失败: {result["message"]}'}), 500
        
        # 保存上传历史
        history = get_upload_history()
        history_item = {
            'id': str(uuid.uuid4()),
            'file_name': file.filename,
            'file_url': result['result']['file_url'],
            'width': result['result']['width'],
            'height': result['result']['height'],
            'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        history.insert(0, history_item)
        save_upload_history(history)
        
        return jsonify({
            'status': 0,
            'message': '上传成功',
            'result': result['result']
        })
    except Exception as e:
        # 确保临时文件被删除
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as remove_error:
                print(f"删除临时文件失败: {str(remove_error)}")
                
        return jsonify({'status': 1, 'message': f'上传失败: {str(e)}'}), 500

@app.route('/history', methods=['GET'])
def get_history():
    history = get_upload_history()
    return jsonify({'status': 0, 'message': 'success', 'result': history})

@app.route('/delete_history/<item_id>', methods=['DELETE'])
def delete_history_item(item_id):
    history = get_upload_history()
    new_history = [item for item in history if item['id'] != item_id]
    
    if len(history) == len(new_history):
        return jsonify({'status': 1, 'message': '找不到指定记录'}), 404
    
    save_upload_history(new_history)
    return jsonify({'status': 0, 'message': '删除成功'})

@app.route('/clear_history', methods=['DELETE'])
def clear_history():
    save_upload_history([])
    return jsonify({'status': 0, 'message': '清除成功'})

if __name__ == '__main__':
    app.run(debug=True, port=5500) 