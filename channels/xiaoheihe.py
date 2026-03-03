"""
小黑盒图床上传渠道
基于小黑盒 (xiaoheihe.cn) 的图片上传 API 实现，使用腾讯云 COS 作为存储后端

上传流程：
1. 调用 upload/info/v2 获取 COS 上传路径（key、region、bucket、host）
2. 调用 upload/token/v2 获取 COS 临时凭证
3. 使用临时凭证将文件 PUT 到腾讯云 COS
4. 调用 upload/callback/v2 确认上传完成，获取最终图片 URL
"""
import hashlib
import hmac
import json
import os
import time
import uuid

import requests
from .base import BaseChannel
from config import get_config


# ==================== hkey 签名算法 ====================
# 移植自小黑盒前端 Hkey.js

_CHARSET = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"


def _vm(e: int) -> int:
    """AES GF(2^8) 乘法辅助函数"""
    return (((e << 1) ^ 0x1B) & 0xFF) if (e & 0x80) else ((e << 1) & 0xFF)


def _qm(e: int) -> int:
    return (_vm(e) ^ e) & 0xFF


def _dollar_m(e: int) -> int:
    return _qm(_vm(e)) & 0xFF


def _ym(e: int) -> int:
    return _dollar_m(_qm(_vm(e))) & 0xFF


def _gm(e: int) -> int:
    return (_ym(e) ^ _dollar_m(e) ^ _qm(e)) & 0xFF


def _km_full(e_arr: list) -> list:
    """MixColumns 变换"""
    e = list(e_arr)
    t0 = (_gm(e[0]) ^ _ym(e[1]) ^ _dollar_m(e[2]) ^ _qm(e[3])) & 0xFF
    t1 = (_qm(e[0]) ^ _gm(e[1]) ^ _ym(e[2]) ^ _dollar_m(e[3])) & 0xFF
    t2 = (_dollar_m(e[0]) ^ _qm(e[1]) ^ _gm(e[2]) ^ _ym(e[3])) & 0xFF
    t3 = (_ym(e[0]) ^ _dollar_m(e[1]) ^ _qm(e[2]) ^ _gm(e[3])) & 0xFF
    e[0], e[1], e[2], e[3] = t0, t1, t2, t3
    return e


def _av(s: str, charset: str, n: int) -> str:
    cs = charset[:n]
    out = []
    length = len(cs)
    for ch in s:
        out.append(cs[ord(ch) % length])
    return "".join(out)


def _sv(s: str, charset: str) -> str:
    out = []
    length = len(charset)
    for ch in s:
        out.append(charset[ord(ch) % length])
    return "".join(out)


def _generate_hkey(url_path: str, timestamp: int, nonce: str) -> str:
    """
    生成 hkey 签名

    参数:
        url_path: API 路径
        timestamp: 请求时间戳
        nonce: 随机 nonce 值

    返回:
        str: 7 字符的 hkey（5字符前缀 + 2位校验码）
    """
    # 路径标准化
    parts = [p for p in str(url_path).split("/") if p]
    normalized_path = "/" + "/".join(parts) + "/"

    comp1 = _av(str(timestamp), _CHARSET, -2)
    comp2 = _sv(normalized_path, _CHARSET)
    comp3 = _sv(str(nonce), _CHARSET)

    comps = [comp1, comp2, comp3]
    max_len = max(len(c) for c in comps)
    interleaved = []
    for k in range(max_len):
        for c in comps:
            if k < len(c):
                interleaved.append(c[k])
    i_str = "".join(interleaved)[:20]

    md5_hash = hashlib.md5(i_str.encode("utf-8")).hexdigest()

    o_prefix = md5_hash[:5]
    hkey_prefix = _av(o_prefix, _CHARSET, -4)

    suffix_part = md5_hash[-6:]
    suffix_input = [ord(c) for c in suffix_part]
    km_output = _km_full(suffix_input)

    checksum_val = sum(km_output) % 100
    return f"{hkey_prefix}{checksum_val:02d}"


def _generate_nonce() -> str:
    """生成 32 字符大写十六进制 nonce"""
    return uuid.uuid4().hex.upper()


class XiaoheiheChannel(BaseChannel):
    """小黑盒图床上传渠道"""

    # 最大文件大小限制：20MB
    MAX_FILE_SIZE = 20 * 1024 * 1024

    # 小黑盒 API 基础 URL
    API_BASE = "https://api.xiaoheihe.cn/bbs/app/api/qcloud/cos"

    # 请求公共查询参数
    COMMON_PARAMS = {
        "app": "heybox",
        "os_type": "web",
        "x_app": "heybox",
        "x_client_type": "web",
        "x_os_type": "Mac",
        "x_client_version": "999.999.999",
        "x_request_default": "true",
        "version": "999.0.4",
    }

    # 请求头
    HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": "https://www.xiaoheihe.cn",
        "Pragma": "no-cache",
        "Referer": "https://www.xiaoheihe.cn/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    }


    def __init__(self):
        """
        初始化小黑盒上传器

        配置项从 config.yaml 的 xiaoheihe 节读取:
            cookie: 从浏览器抓取的完整 Cookie 字符串
        """
        super().__init__()
        cfg = get_config().get('xiaoheihe', {})
        self.cookie = cfg.get('cookie', '')

    def get_channel_name(self):
        """获取渠道名称"""
        return "xiaoheihe"

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

    def _build_api_params(self, url_path: str) -> dict:
        """
        构建带 hkey 签名的 API 查询参数

        参数:
            url_path: API 路径（不含域名）

        返回:
            dict: 包含公共参数 + hkey + _time + nonce 的完整查询参数
        """
        timestamp = int(time.time())
        nonce = _generate_nonce()
        hkey_val = _generate_hkey(url_path, timestamp, nonce)

        params = dict(self.COMMON_PARAMS)
        params["hkey"] = hkey_val
        params["_time"] = str(timestamp)
        params["nonce"] = nonce
        return params

    @staticmethod
    def _get_file_extension(filename: str) -> str:
        """获取文件扩展名（小写，不带点）"""
        _, ext = os.path.splitext(filename)
        return ext.lower().lstrip(".")

    @staticmethod
    def _get_mimetype(ext: str) -> str:
        """根据扩展名获取 MIME 类型"""
        mime_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "bmp": "image/bmp",
        }
        return mime_map.get(ext, f"image/{ext}")

    def _cos_sign(self, secret_id: str, secret_key: str,
                  method: str, path: str,
                  start_time: int, end_time: int,
                  headers_to_sign: dict = None) -> str:
        """
        生成腾讯云 COS 请求签名

        参考文档: https://cloud.tencent.com/document/product/436/7778

        参数:
            secret_id: 临时 SecretId
            secret_key: 临时 SecretKey
            method: HTTP 方法（小写，如 "put"）
            path: 请求路径（如 "/web/bbs/2026/03/03/xxx.jpeg"）
            start_time: 签名起始时间戳
            end_time: 签名过期时间戳
            headers_to_sign: 需要签名的请求头字典

        返回:
            str: 完整的 Authorization 签名字符串
        """
        # 步骤1：生成 KeyTime
        key_time = f"{start_time};{end_time}"

        # 步骤2：生成 SignKey = HMAC-SHA1(SecretKey, KeyTime)
        sign_key = hmac.new(
            secret_key.encode("utf-8"),
            key_time.encode("utf-8"),
            hashlib.sha1
        ).hexdigest()

        # 步骤3：生成 HttpString
        http_string = f"{method}\n{path}\n\n"

        # 处理需要签名的 headers
        header_list = ""
        if headers_to_sign:
            # 按 key 排序，全部小写
            sorted_headers = sorted(
                [(k.lower(), v) for k, v in headers_to_sign.items()],
                key=lambda x: x[0]
            )
            http_string = (
                f"{method}\n{path}\n\n"
                + "&".join(f"{k}={v}" for k, v in sorted_headers)
                + "\n"
            )
            header_list = ";".join(k for k, _ in sorted_headers)
        else:
            http_string += "\n"

        # 步骤4：生成 StringToSign
        sha1_of_http_string = hashlib.sha1(http_string.encode("utf-8")).hexdigest()
        string_to_sign = f"sha1\n{key_time}\n{sha1_of_http_string}\n"

        # 步骤5：生成 Signature
        signature = hmac.new(
            sign_key.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1
        ).hexdigest()

        # 步骤6：组装 Authorization
        authorization = (
            f"q-sign-algorithm=sha1"
            f"&q-ak={secret_id}"
            f"&q-sign-time={key_time}"
            f"&q-key-time={key_time}"
            f"&q-header-list={header_list}"
            f"&q-url-param-list="
            f"&q-signature={signature}"
        )

        return authorization

    def _get_upload_info(self, filename: str, mimetype: str,
                         file_size: int, width: int, height: int) -> dict:
        """
        第一步：获取上传路径信息

        调用 upload/info/v2 接口，获取 COS 存储路径。

        参数:
            filename: 文件名
            mimetype: MIME 类型
            file_size: 文件大小（字节）
            width: 图片宽度
            height: 图片高度

        返回:
            dict: 包含 keys, region, bucket, host 的字典，失败返回 None
        """
        url_path = "/bbs/app/api/qcloud/cos/upload/info/v2"
        params = self._build_api_params(url_path)

        file_infos = [{
            "name": filename,
            "mimetype": mimetype,
            "fsize": file_size,
            "width": width,
            "height": height,
        }]

        data = {
            "file_infos": json.dumps(file_infos),
            "scope": "bbs",
            "need_cache": "0",
        }

        try:
            response = requests.post(
                f"{self.API_BASE}/upload/info/v2",
                params=params,
                headers=self.HEADERS,
                cookies=self._parse_cookie(),
                data=data,
                timeout=30,
            )
            result = response.json()

            if result.get("status") == "ok":
                return result.get("result")
            else:
                self.log_error(f"获取上传信息失败: {result.get('msg', '未知错误')}")
                return None
        except Exception as e:
            self.log_error(f"请求上传信息异常: {e}")
            return None

    def _get_upload_token(self, bucket: str, keys: list, mimetypes: list) -> dict:
        """
        第二步：获取 COS 临时凭证

        调用 upload/token/v2 接口，获取临时 SecretKey/SecretId/SessionToken。

        参数:
            bucket: COS Bucket 名称
            keys: 文件 key 列表
            mimetypes: MIME 类型列表

        返回:
            dict: 包含 credentials 和 expiredTime 的字典，失败返回 None
        """
        url_path = "/bbs/app/api/qcloud/cos/upload/token/v2"
        params = self._build_api_params(url_path)

        data = {
            "bucket": bucket,
            "keys": json.dumps(keys),
            "mimetypes": json.dumps(mimetypes),
            "is_multipart_upload": "0",
        }

        try:
            response = requests.post(
                f"{self.API_BASE}/upload/token/v2",
                params=params,
                headers=self.HEADERS,
                cookies=self._parse_cookie(),
                data=data,
                timeout=30,
            )
            result = response.json()

            if result.get("status") == "ok":
                return result.get("result")
            else:
                self.log_error(f"获取上传凭证失败: {result.get('msg', '未知错误')}")
                return None
        except Exception as e:
            self.log_error(f"请求上传凭证异常: {e}")
            return None

    def _upload_to_cos(self, file_path: str, key: str, region: str, bucket: str,
                        credentials: dict,
                        start_time: int, end_time: int,
                        mimetype: str) -> bool:
        """
        第三步：上传文件到腾讯云 COS

        使用 PUT 方法将文件上传到 COS，需要自行生成 COS 签名。

        参数:
            file_path: 本地文件路径
            key: COS 对象键
            region: COS 地域
            bucket: COS Bucket 名称
            credentials: 临时凭证（包含 tmpSecretKey, tmpSecretId, sessionToken）
            start_time: 凭证起始时间戳
            end_time: 凭证过期时间戳
            mimetype: 文件 MIME 类型

        返回:
            bool: 上传是否成功
        """
        # 读取文件
        with open(file_path, "rb") as f:
            file_content = f.read()

        file_size = len(file_content)

        # COS 上传 URL
        cos_url = f"https://{bucket}.cos.{region}.myqcloud.com{key}"

        # 需要签名的请求头
        headers_to_sign = {
            "content-length": str(file_size),
            "host": f"{bucket}.cos.{region}.myqcloud.com",
        }

        # 生成 COS 签名
        authorization = self._cos_sign(
            secret_id=credentials["tmpSecretId"],
            secret_key=credentials["tmpSecretKey"],
            method="put",
            path=key,
            start_time=start_time,
            end_time=end_time,
            headers_to_sign=headers_to_sign,
        )

        # 构建请求头
        put_headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Authorization": authorization,
            "Connection": "keep-alive",
            "Content-Length": str(file_size),
            "Content-Type": mimetype,
            "Origin": "https://www.xiaoheihe.cn",
            "Referer": "https://www.xiaoheihe.cn/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": self.HEADERS["User-Agent"],
            "x-cos-security-token": credentials["sessionToken"],
        }

        try:
            response = requests.put(
                cos_url,
                headers=put_headers,
                data=file_content,
                timeout=120,
            )

            if response.status_code == 200:
                self.log_info(f"COS 上传成功，ETag: {response.headers.get('ETag', 'N/A')}")
                return True
            else:
                self.log_error(f"COS 上传失败: HTTP {response.status_code}, {response.text}")
                return False
        except Exception as e:
            self.log_error(f"COS 上传异常: {e}")
            return False

    def _upload_callback(self, keys: list) -> dict:
        """
        第四步：上传回调确认

        调用 upload/callback/v2 接口通知服务端上传完成，获取最终图片 URL。

        参数:
            keys: 文件 key 列表

        返回:
            dict: 包含 preview_urls 和 thumbs 的字典，失败返回 None
        """
        url_path = "/bbs/app/api/qcloud/cos/upload/callback/v2"
        params = self._build_api_params(url_path)
        params["is_finished"] = "true"

        data = {
            "keys": json.dumps(keys),
        }

        try:
            response = requests.post(
                f"{self.API_BASE}/upload/callback/v2",
                params=params,
                headers=self.HEADERS,
                cookies=self._parse_cookie(),
                data=data,
                timeout=30,
            )
            result = response.json()

            if result.get("status") == "ok":
                return result.get("result")
            else:
                self.log_error(f"上传回调失败: {result.get('msg', '未知错误')}")
                return None
        except Exception as e:
            self.log_error(f"上传回调异常: {e}")
            return None

    def upload(self, temp_file_path, file):
        """
        上传到小黑盒图床

        参数:
            temp_file_path: str - 临时文件路径
            file: ValidatedFile - 包含 filename, content_type, width, height 的文件对象

        返回:
            dict or None - 成功返回 {'file_url': str, 'width': int, 'height': int}，失败返回 None
        """
        if not self.cookie:
            self.log_error("未配置小黑盒 Cookie，请在 config.yaml 中设置 xiaoheihe.cookie")
            return None

        # 获取文件信息
        ext = self._get_file_extension(file.filename)
        mimetype = self._get_mimetype(ext)
        file_size = os.path.getsize(temp_file_path)
        width = file.width if hasattr(file, 'width') else 0
        height = file.height if hasattr(file, 'height') else 0

        self.log_info(f"开始上传: {file.filename}, 大小={file_size}, 尺寸={width}x{height}")

        # 第一步：获取上传信息
        upload_info = self._get_upload_info(file.filename, mimetype, file_size, width, height)
        if not upload_info:
            return None

        keys = upload_info.get("keys", [])
        region = upload_info.get("region")
        bucket = upload_info.get("bucket")
        host = upload_info.get("host")

        if not keys or not region or not bucket:
            self.log_error(f"上传信息不完整: {upload_info}")
            return None

        key = keys[0]
        self.log_info(f"上传目标: key={key}, region={region}, bucket={bucket}")

        # 第二步：获取临时凭证
        token_result = self._get_upload_token(bucket, keys, [mimetype])
        if not token_result:
            return None

        credentials = token_result.get("credentials", {})
        start_time = token_result.get("startTime")
        end_time = token_result.get("expiredTime")

        if not credentials.get("tmpSecretKey") or not credentials.get("tmpSecretId"):
            self.log_error(f"凭证信息不完整: {credentials}")
            return None

        self.log_info("已获取临时凭证")

        # 第三步：上传文件到 COS
        cos_success = self._upload_to_cos(
            file_path=temp_file_path,
            key=key,
            region=region,
            bucket=bucket,
            credentials=credentials,
            start_time=start_time,
            end_time=end_time,
            mimetype=mimetype,
        )
        if not cos_success:
            return None

        # 第四步：回调确认
        callback_result = self._upload_callback(keys)
        if not callback_result:
            return None

        # 获取最终图片 URL
        preview_urls = callback_result.get("preview_urls", [])
        if not preview_urls:
            self.log_error(f"回调结果中缺少 preview_urls: {callback_result}")
            return None

        file_url = preview_urls[0]
        self.log_info(f"上传完成: {file_url}")

        return {
            'file_url': file_url,
            'width': width,
            'height': height,
        }
