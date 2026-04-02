"""
4399 图床上传渠道
基于 4399 论坛的图片上传 API 实现

上传流程：
1. 使用 form-data 格式 POST 图片到上传接口
2. 从响应中获取图片路径
3. 拼接 CDN 前缀得到最终图片 URL
"""
import os

import requests
from .base import BaseChannel
from config import get_config


class Si399Channel(BaseChannel):
    """4399 图床上传渠道"""

    # 最大文件大小限制：10MB
    MAX_FILE_SIZE = 10 * 1024 * 1024

    # 上传 API 地址
    UPLOAD_URL = "https://mapi.yxhapi2.com/forums/box/android/v2.1/upload-image.html"

    # 图片 CDN 基础地址
    CDN_BASE = "https://fs.img4399.com/bbs/"

    def __init__(self):
        """
        初始化 4399 上传器

        配置项从 config.yaml 的 si399 节读取:
            user_agent: User-Agent 请求头
            mauth: mauth 请求头
            mauthcode: mauthcode 请求头
            pauth: pauth 请求头
        """
        super().__init__()
        cfg = get_config().get('si399', {})
        self.user_agent = cfg.get('user_agent', '')
        self.mauth = cfg.get('mauth', '')
        self.mauthcode = cfg.get('mauthcode', '')
        self.pauth = cfg.get('pauth', '')

    def get_channel_name(self):
        """获取渠道名称"""
        return "4399"

    def get_display_name(self):
        """获取渠道显示名称"""
        return "4399"

    def _check_config(self):
        """
        检查必要的配置项是否已填写

        返回:
            tuple - (是否通过, 缺失的配置项列表)
        """
        missing = []
        if not self.user_agent:
            missing.append('user_agent')
        if not self.mauth:
            missing.append('mauth')
        if not self.mauthcode:
            missing.append('mauthcode')
        if not self.pauth:
            missing.append('pauth')

        if missing:
            return False, missing
        return True, []

    def upload(self, temp_file_path, file):
        """
        上传到 4399 图床

        参数:
            temp_file_path: str - 临时文件路径
            file: ValidatedFile - 包含 filename, content_type, width, height 的文件对象

        返回:
            dict or None - 成功返回 {'file_url': str, 'width': int, 'height': int}，失败返回 None
        """
        # 检查配置
        config_ok, missing = self._check_config()
        if not config_ok:
            self.log_error(f"未配置必要的请求头，缺失: {', '.join(missing)}，请在 config.yaml 中设置 si399 配置项")
            return None

        # 构建请求头
        headers = {
            'User-Agent': self.user_agent,
            'mauth': self.mauth,
            'mauthcode': self.mauthcode,
            'pauth': self.pauth,
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        }

        try:
            with open(temp_file_path, 'rb') as file_handle:
                files = {
                    'image': (file.filename, file_handle, file.content_type)
                }
                data = {
                    'thread_type': '2'
                }

                self.log_info(f"开始上传: {file.filename}")

                response = requests.post(
                    self.UPLOAD_URL,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=60,
                )
        except Exception as e:
            self.log_error(f"上传请求失败: {str(e)}")
            return None

        if response.status_code != 200:
            self.log_error(f"上传失败: HTTP {response.status_code}, {response.text}")
            return None

        try:
            result = response.json()

            # 检查响应状态码，code=100 表示成功
            if result.get('code') != 100:
                self.log_error(f"上传失败: code={result.get('code')}, message={result.get('message')}")
                return None

            # 从响应中获取图片路径
            image_data = result.get('result', {}).get('data')
            if not image_data:
                self.log_error(f"响应中缺少图片路径: {result}")
                return None

            # 拼接最终图片 URL
            file_url = f"{self.CDN_BASE}{image_data}"

            # 获取图片尺寸（API 不返回尺寸，使用验证时获取的）
            width = file.width if hasattr(file, 'width') else 0
            height = file.height if hasattr(file, 'height') else 0

            self.log_info(f"上传完成: {file_url}")

            return {
                'file_url': file_url,
                'width': width,
                'height': height,
            }
        except Exception as e:
            self.log_error(f"解析上传响应失败: {str(e)}")
            return None
