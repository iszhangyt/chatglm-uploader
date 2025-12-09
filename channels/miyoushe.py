"""
米游社图床上传渠道
基于 miyoushe.com 的图片上传 API 实现
"""
import hashlib
import os
import requests
from .base import BaseChannel


class MiyousheChannel(BaseChannel):
    """米游社图床上传渠道"""
    
    # API 端点
    GET_UPLOAD_PARAMS_URL = "https://bbs-api.miyoushe.com/apihub/wapi/getUploadParams"
    
    # 默认请求头
    DEFAULT_HEADERS = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "x-rpc-app_version": "2.96.0"
    }
    
    # 图片格式对应 MIME 类型映射
    MIME_TYPES = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
    }
    
    def __init__(self, cookie: str = None):
        """
        初始化上传器
        
        Args:
            cookie: 米游社登录 Cookie，如果不传则从环境变量 MIYOUSHE_COOKIE 读取
        """
        super().__init__()
        self.cookie = cookie or os.environ.get('MIYOUSHE_COOKIE', '')
    
    def get_channel_name(self):
        """获取渠道名称"""
        return "miyoushe"
    
    @staticmethod
    def _calculate_md5(file_path: str) -> str:
        """计算文件的 MD5 哈希值"""
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    
    @staticmethod
    def _get_file_extension(file_path: str) -> str:
        """获取文件扩展名（小写，不带点）"""
        _, ext = os.path.splitext(file_path)
        return ext.lower().lstrip(".")
    
    def _parse_cookie(self) -> dict:
        """解析 Cookie 字符串为字典"""
        cookies = {}
        if self.cookie:
            for item in self.cookie.split(";"):
                item = item.strip()
                if "=" in item:
                    key, value = item.split("=", 1)
                    cookies[key.strip()] = value.strip()
        return cookies
    
    def _get_upload_params(self, md5: str, ext: str):
        """获取 OSS 上传参数"""
        headers = {
            **self.DEFAULT_HEADERS,
            "content-type": "application/json",
            "referer": "https://www.miyoushe.com/",
        }
        
        payload = {
            "md5": md5,
            "ext": ext,
            "biz": "community",
            "support_content_type": True,
            "support_extra_form_data": True,
            "extra": {
                "upload_source": "UPLOAD_SOURCE_COMMUNITY"
            }
        }
        
        try:
            response = requests.post(
                self.GET_UPLOAD_PARAMS_URL,
                headers=headers,
                json=payload,
                cookies=self._parse_cookie(),
                timeout=30
            )
            result = response.json()
            
            if result.get("retcode") == 0:
                return result.get("data")
            else:
                self.log_error(f"获取上传参数失败: {result.get('message', '未知错误')}")
                return None
                
        except Exception as e:
            self.log_error(f"请求上传参数异常: {e}")
            return None
    
    def _upload_to_oss(self, file_path: str, params: dict):
        """上传文件到阿里云 OSS"""
        oss_params = params.get("params", params.get("oss", {}))
        host = oss_params.get("host")
        
        if not host:
            self.log_error("未获取到 OSS Host")
            return None
        
        # 获取文件名和扩展名
        file_name = os.path.basename(file_path)
        ext = self._get_file_extension(file_path)
        content_type = self.MIME_TYPES.get(ext, f"image/{ext}")
        
        # 构建表单数据
        form_data = {
            "name": (None, oss_params.get("name")),
            "key": (None, params.get("file_name")),
            "callback": (None, oss_params.get("callback")),
            "success_action_status": (None, "200"),
            "x:extra": (None, oss_params.get("callback_var", {}).get("x:extra", "")),
            "x-oss-content-type": (None, oss_params.get("x_oss_content_type", content_type)),
            "OSSAccessKeyId": (None, oss_params.get("accessid")),
            "policy": (None, oss_params.get("policy")),
            "signature": (None, oss_params.get("signature")),
        }
        
        # 添加额外的表单数据
        extra_form_data = oss_params.get("extra_form_data", [])
        for item in extra_form_data:
            key = item.get("key")
            value = item.get("value")
            if key and value is not None:
                form_data[key] = (None, value)
        
        # 读取文件内容
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        form_data["file"] = (file_name, file_content, content_type)
        
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "referer": "https://www.miyoushe.com/",
        }
        
        try:
            response = requests.post(
                host,
                headers=headers,
                files=form_data,
                timeout=60
            )
            result = response.json()
            
            if result.get("retcode") == 0:
                return result.get("data")
            else:
                self.log_error(f"OSS 上传失败: {result.get('msg', '未知错误')}")
                return None
                
        except Exception as e:
            self.log_error(f"OSS 上传异常: {e}")
            return None
    
    def upload(self, temp_file_path, file):
        """
        上传到米游社图床
        
        参数:
            temp_file_path: str - 临时文件路径
            file: ValidatedFile - 包含filename, content_type, width, height的文件对象
            
        返回:
            dict or None - 成功返回 {'file_url': str, 'width': int, 'height': int}，失败返回None
        """
        if not self.cookie:
            self.log_error("未配置米游社 Cookie，请设置环境变量 MIYOUSHE_COOKIE")
            return None
        
        ext = self._get_file_extension(temp_file_path)
        
        # 计算 MD5
        md5 = self._calculate_md5(temp_file_path)
        self.log_info(f"文件 MD5: {md5}")
        
        # 第一步：获取上传参数
        params = self._get_upload_params(md5, ext)
        if not params:
            return None
        
        self.log_info(f"上传目标: {params.get('file_name')}")
        
        # 第二步：上传到 OSS
        result = self._upload_to_oss(temp_file_path, params)
        if not result:
            return None
        
        self.log_info("上传成功")
        
        # 获取图片尺寸
        width = file.width if hasattr(file, 'width') else 0
        height = file.height if hasattr(file, 'height') else 0
        
        return {
            'file_url': result.get("url", ""),
            'width': width,
            'height': height
        }

