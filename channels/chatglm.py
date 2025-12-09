"""
ChatGLM图床上传渠道
"""
import requests
from .base import BaseChannel


class ChatGLMChannel(BaseChannel):
    """ChatGLM图床上传渠道"""
    
    def __init__(self):
        super().__init__()
        self.upload_url = "https://chatglm.cn/chatglm/backend-api/assistant/file_upload"
    
    def get_channel_name(self):
        """获取渠道名称"""
        return "chatglm"
    
    def upload(self, temp_file_path, file):
        """
        上传到ChatGLM图床
        
        参数:
            temp_file_path: str - 临时文件路径
            file: ValidatedFile - 包含filename, content_type, width, height的文件对象
            
        返回:
            dict or None - 成功返回 {'file_url': str, 'width': int, 'height': int}，失败返回None
        """
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
                
                response = requests.request("POST", self.upload_url, headers=headers, data=payload, files=files)
        except Exception as e:
            self.log_error(f"上传请求失败: {str(e)}")
            return None
        
        if response.status_code != 200:
            self.log_error(f"上传失败: {response.text}")
            return None
        
        result = response.json()
        
        if result['status'] != 0:
            self.log_error(f"上传失败: {result['message']}")
            return None
        
        # 如果图床返回的尺寸为0，使用我们验证时获取的尺寸
        width = result['result'].get('width', 0)
        height = result['result'].get('height', 0)
        
        if width == 0 and hasattr(file, 'width'):
            width = file.width
        
        if height == 0 and hasattr(file, 'height'):
            height = file.height
        
        return {
            'file_url': result['result']['file_url'],
            'width': width,
            'height': height
        }

