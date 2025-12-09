"""
上传渠道基类
定义所有上传渠道需要实现的接口
"""
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger('image_uploader')


class BaseChannel(ABC):
    """上传渠道基类"""
    
    # 默认最大文件大小限制（字节），None 表示无限制
    MAX_FILE_SIZE = None
    
    def __init__(self):
        self.name = self.__class__.__name__
    
    def get_max_file_size(self):
        """
        获取最大文件大小限制（字节）
        
        返回:
            int or None - 最大文件大小（字节），None表示无限制
        """
        return self.MAX_FILE_SIZE
    
    def check_file_size(self, file_path):
        """
        检查文件大小是否超出限制
        
        参数:
            file_path: str - 文件路径
            
        返回:
            tuple - (是否通过, 错误信息或None)
        """
        import os
        max_size = self.get_max_file_size()
        if max_size is None:
            return True, None
        
        file_size = os.path.getsize(file_path)
        if file_size > max_size:
            max_size_mb = max_size / (1024 * 1024)
            file_size_mb = file_size / (1024 * 1024)
            return False, f"文件大小 {file_size_mb:.2f}MB 超出限制 {max_size_mb:.0f}MB"
        
        return True, None
    
    @abstractmethod
    def upload(self, temp_file_path, file):
        """
        上传文件到图床
        
        参数:
            temp_file_path: str - 临时文件路径
            file: ValidatedFile - 包含filename, content_type, width, height的文件对象
            
        返回:
            dict or None - 成功返回 {'file_url': str, 'width': int, 'height': int}，失败返回None
        """
        pass
    
    @abstractmethod
    def get_channel_name(self):
        """
        获取渠道名称
        
        返回:
            str - 渠道的唯一标识符
        """
        pass
    
    def log_error(self, message):
        """记录错误日志"""
        logger.error(f"[{self.get_channel_name()}] {message}")
    
    def log_info(self, message):
        """记录信息日志"""
        logger.info(f"[{self.get_channel_name()}] {message}")

