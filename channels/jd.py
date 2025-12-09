"""
京东图床上传渠道
"""
import requests
from .base import BaseChannel


class JDChannel(BaseChannel):
    """京东图床上传渠道"""
    
    def __init__(self):
        super().__init__()
        self.upload_url = "https://pic.jd.com/0/32ac1cd9ca1543e2a9cce60a4c9be94e"
    
    def get_channel_name(self):
        """获取渠道名称"""
        return "jd"
    
    def upload(self, temp_file_path, file):
        """
        上传到京东图床
        
        参数:
            temp_file_path: str - 临时文件路径
            file: ValidatedFile - 包含filename, content_type, width, height的文件对象
            
        返回:
            dict or None - 成功返回 {'file_url': str, 'width': int, 'height': int}，失败返回None
        """
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
                
                response = requests.post(self.upload_url, headers=headers, files=files)
        except Exception as e:
            self.log_error(f"上传请求失败: {str(e)}")
            return None
        
        if response.status_code != 200:
            self.log_error(f"上传失败: {response.text}")
            return None
        
        try:
            result = response.json()
            
            if result['id'] != '1' or not result['msg']:
                self.log_error(f"上传失败: {result}")
                return None
            
            # 构建完整URL
            # 从响应结果可以看出，返回格式是 jfs/t1/276937/35/26005/100196/68075c62F71bbcbb5/62424d53b2551311.png
            # 需要正确构建完整URL，使用新的前缀
            file_url = f"https://img20.360buyimg.com/openfeedback/{result['msg']}"
            
            # 获取图片尺寸，京东不返回，使用我们验证时获取的
            width = 0
            height = 0
            
            if hasattr(file, 'width'):
                width = file.width
            
            if hasattr(file, 'height'):
                height = file.height
            
            return {
                'file_url': file_url,
                'width': width,
                'height': height
            }
        except Exception as e:
            self.log_error(f"解析上传响应失败: {str(e)}")
            return None

