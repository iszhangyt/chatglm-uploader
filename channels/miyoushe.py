"""
米游社图床上传渠道
基于 miyoushe.com 的图片上传 API 实现，支持网页端(web)和App端(app)两种模式
"""
import hashlib
import os
import time
import random
import string
import requests
from .base import BaseChannel


class MiyousheChannel(BaseChannel):
    """米游社图床上传渠道"""
    
    # 最大文件大小限制：20MB
    MAX_FILE_SIZE = 20 * 1024 * 1024
    
    # API 端点
    WEB_API_URL = "https://bbs-api.miyoushe.com/apihub/wapi/getUploadParams"
    APP_API_URL = "https://bbs-api.miyoushe.com/apihub/sapi/getUploadParams"
    
    # App 端 DS 签名盐值
    DS_SALT = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"
    
    # 网页端默认请求头
    WEB_HEADERS = {
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
            cookie: 米游社登录 Cookie，如果不传则从环境变量读取
        
        环境变量:
            MIYOUSHE_COOKIE: 网页端 Cookie
            MIYOUSHE_APP_COOKIE: App 端 Cookie
            MIYOUSHE_API_TYPE: API 类型，"web"(默认) 或 "app"
        
        当 MIYOUSHE_API_TYPE=app 时自动使用 MIYOUSHE_APP_COOKIE，
        否则使用 MIYOUSHE_COOKIE。两个 Cookie 不通用。
        """
        super().__init__()
        self.api_type = os.environ.get('MIYOUSHE_API_TYPE', 'web').lower()
        if self.api_type == "app":
            self.cookie = cookie or os.environ.get('MIYOUSHE_APP_COOKIE', '')
            self._init_device_info()
        else:
            self.cookie = cookie or os.environ.get('MIYOUSHE_COOKIE', '')
    
    def get_channel_name(self):
        """获取渠道名称"""
        return "miyoushe"
    
    def _init_device_info(self):
        """初始化 App 端伪装设备信息"""
        self.device_id = "8324a729-7d71-352a-97af-6b1c6689aba9"
        self.device_fp = "38d8165c1b88a"
    
    def _generate_ds(self, query: str = "", body: str = "") -> str:
        """
        生成 App 端 DS 签名
        
        算法: ds = "{t},{r},{md5(salt={salt}&t={t}&r={r}&b={body}&q={query})}"
        其中 query 需要按 key 字母序排列
        """
        t = int(time.time())
        r = ''.join(random.choices(string.ascii_lowercase, k=6))
        check = hashlib.md5(
            f"salt={self.DS_SALT}&t={t}&r={r}&b={body}&q={query}".encode()
        ).hexdigest()
        return f"{t},{r},{check}"
    
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
        """获取 OSS 上传参数，根据 api_type 分发到对应实现"""
        if self.api_type == "app":
            return self._get_upload_params_app(md5, ext)
        return self._get_upload_params_web(md5, ext)
    
    def _get_upload_params_web(self, md5: str, ext: str):
        """网页端获取 OSS 上传参数 (POST wapi)"""
        headers = {
            **self.WEB_HEADERS,
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
                self.WEB_API_URL,
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
    
    def _get_upload_params_app(self, md5: str, ext: str):
        """App 端获取 OSS 上传参数 (GET sapi)"""
        query_params = {
            "md5": md5,
            "ext": ext,
            "support_content_type": "1",
            "upload_source": "1",
        }
        
        sorted_query = "&".join(
            f"{k}={v}" for k, v in sorted(query_params.items())
        )
        
        headers = {
            "user-agent": "okhttp/4.9.3",
            "referer": "https://app.mihoyo.com",
            "ds": self._generate_ds(sorted_query),
            "x-rpc-client_type": "2",
            "x-rpc-app_version": "2.102.1",
            "x-rpc-sys_version": "12",
            "x-rpc-channel": "ys",
            "x-rpc-device_id": self.device_id,
            "x-rpc-device_fp": self.device_fp,
            "x-rpc-device_name": "OPPO PHY110",
            "x-rpc-device_model": "PHY110",
            "x-rpc-h265_supported": "1",
            "x-rpc-verify_key": "bll8iq97cem8",
            "x-rpc-csm_source": "home",
        }
        
        try:
            response = requests.get(
                self.APP_API_URL,
                headers=headers,
                params=query_params,
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
        
        if self.api_type == "app":
            headers = {
                "ds": self._generate_ds(),
                "x-rpc-csm_source": "home",
                "user-agent": "okhttp/4.9.3",
            }
        else:
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
        
        cookies = self._parse_cookie() if self.api_type == "app" else None
        
        try:
            response = requests.post(
                host,
                headers=headers,
                files=form_data,
                cookies=cookies,
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
            env_var = 'MIYOUSHE_APP_COOKIE' if self.api_type == 'app' else 'MIYOUSHE_COOKIE'
            self.log_error(f"未配置米游社 Cookie，请设置环境变量 {env_var}")
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

