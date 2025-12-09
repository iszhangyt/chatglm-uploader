"""
上传渠道管理器
负责注册和管理所有上传渠道
"""
from .base import BaseChannel
from .chatglm import ChatGLMChannel
from .jd import JDChannel


class ChannelManager:
    """上传渠道管理器"""
    
    def __init__(self):
        self.channels = {}
        self._register_default_channels()
    
    def _register_default_channels(self):
        """注册默认的上传渠道"""
        self.register(ChatGLMChannel())
        self.register(JDChannel())
    
    def register(self, channel):
        """
        注册一个上传渠道
        
        参数:
            channel: BaseChannel - 上传渠道实例
        """
        if not isinstance(channel, BaseChannel):
            raise ValueError(f"渠道必须继承自BaseChannel")
        
        channel_name = channel.get_channel_name()
        self.channels[channel_name] = channel
    
    def get_channel(self, channel_name):
        """
        获取指定的上传渠道
        
        参数:
            channel_name: str - 渠道名称
            
        返回:
            BaseChannel or None - 渠道实例，如果不存在返回None
        """
        return self.channels.get(channel_name)
    
    def get_all_channels(self):
        """
        获取所有已注册的渠道
        
        返回:
            dict - 所有渠道的字典 {渠道名: 渠道实例}
        """
        return self.channels.copy()
    
    def has_channel(self, channel_name):
        """
        检查渠道是否存在
        
        参数:
            channel_name: str - 渠道名称
            
        返回:
            bool - 存在返回True，否则返回False
        """
        return channel_name in self.channels


# 创建全局渠道管理器实例
channel_manager = ChannelManager()

