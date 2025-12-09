# 上传渠道系统

## 概述

本项目采用模块化的渠道系统设计，将各个图床上传渠道分离成独立的模块，方便维护和扩展。

## 目录结构

```
channels/
├── __init__.py      # 渠道管理器
├── base.py          # 基类定义
├── chatglm.py       # ChatGLM渠道
├── jd.py            # 京东渠道
└── README.md        # 本文档
```

## 如何添加新的上传渠道

### 1. 创建新的渠道模块

在 `channels` 目录下创建一个新的 Python 文件，例如 `example.py`：

```python
"""
示例图床上传渠道
"""
import requests
from .base import BaseChannel


class ExampleChannel(BaseChannel):
    """示例图床上传渠道"""
    
    def __init__(self):
        super().__init__()
        self.upload_url = "https://example.com/upload"  # 上传API地址
    
    def get_channel_name(self):
        """
        获取渠道名称（唯一标识符）
        这个名称将用于API调用时指定渠道
        """
        return "example"
    
    def upload(self, temp_file_path, file):
        """
        上传文件到图床
        
        参数:
            temp_file_path: str - 临时文件路径（已保存到磁盘）
            file: ValidatedFile - 包含以下属性的文件对象：
                - filename: 文件名
                - content_type: MIME类型（如 'image/jpeg'）
                - width: 图片宽度
                - height: 图片高度
            
        返回:
            dict or None - 成功返回字典，失败返回None
            返回格式: {
                'file_url': str,   # 图片URL（必需）
                'width': int,      # 图片宽度（必需）
                'height': int      # 图片高度（必需）
            }
        """
        try:
            # 读取文件并上传
            with open(temp_file_path, 'rb') as file_handle:
                files = {
                    'file': (file.filename, file_handle, file.content_type)
                }
                headers = {
                    'User-Agent': 'Mozilla/5.0',
                    # 添加其他必需的请求头
                }
                
                response = requests.post(self.upload_url, headers=headers, files=files)
            
            # 检查响应状态
            if response.status_code != 200:
                self.log_error(f"上传失败: {response.text}")
                return None
            
            # 解析响应
            result = response.json()
            
            # 根据API返回格式提取URL
            file_url = result.get('url')  # 根据实际API调整
            
            if not file_url:
                self.log_error(f"响应中缺少URL: {result}")
                return None
            
            # 返回标准格式
            return {
                'file_url': file_url,
                'width': file.width,   # 使用验证时获取的尺寸
                'height': file.height
            }
            
        except Exception as e:
            self.log_error(f"上传请求失败: {str(e)}")
            return None
```

### 2. 注册新渠道

在 `channels/__init__.py` 中导入并注册新渠道：

```python
# 导入新渠道
from .example import ExampleChannel

class ChannelManager:
    # ... 其他代码 ...
    
    def _register_default_channels(self):
        """注册默认的上传渠道"""
        self.register(ChatGLMChannel())
        self.register(JDChannel())
        self.register(ExampleChannel())  # 添加这行
```

### 3. 使用新渠道

新渠道注册后，可以通过API使用：

**直接文件上传：**
```bash
curl -X POST http://localhost:5500/upload \
  -H "X-Verification-Token: your_token" \
  -F "file=@image.jpg" \
  -F "channel=example"
```

**从URL上传：**
```bash
curl -X POST http://localhost:5500/upload_from_url \
  -H "X-Verification-Token: your_token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/image.jpg", "channel": "example"}'
```

## 基类方法说明

### 必须实现的方法

- `get_channel_name()`: 返回渠道的唯一标识符（字符串）
- `upload(temp_file_path, file)`: 实现具体的上传逻辑

### 可用的辅助方法

- `self.log_error(message)`: 记录错误日志（自动添加渠道名称前缀）
- `self.log_info(message)`: 记录信息日志（自动添加渠道名称前缀）

## 现有渠道

### ChatGLM（chatglm）
- 默认渠道
- 上传到 ChatGLM 图床
- 返回完整的图片URL和尺寸信息

### 京东（jd）
- 上传到京东反馈系统的图床
- 构建京东CDN URL
- 使用本地验证的图片尺寸

## 注意事项

1. **错误处理**: 所有异常都应该被捕获并返回 `None`，使用 `self.log_error()` 记录错误信息
2. **文件句柄**: 确保文件句柄在使用后正确关闭（使用 `with` 语句）
3. **返回格式**: 必须返回包含 `file_url`、`width`、`height` 的字典
4. **日志记录**: 使用 `self.log_info()` 和 `self.log_error()` 记录日志，会自动添加渠道标识
5. **渠道名称**: `get_channel_name()` 返回的名称必须唯一，建议使用小写字母

## 测试新渠道

添加新渠道后，建议进行以下测试：

1. **文件上传测试**: 测试直接上传图片文件
2. **URL上传测试**: 测试从URL下载并上传
3. **错误处理测试**: 测试各种异常情况（网络错误、无效响应等）
4. **日志检查**: 检查日志文件确保错误信息被正确记录

