# 上传渠道系统

## 概述

FusionPic 采用模块化的渠道系统设计，将各个图床上传渠道分离成独立的模块，方便维护和扩展。

前端渠道配置（下拉框选项、渠道显示名、文件大小限制等）通过后端 Context Processor 和 Jinja2 模板自动注入，**新增渠道无需修改前端代码**。

## 目录结构

```
channels/
├── __init__.py      # 渠道管理器（ChannelManager）
├── base.py          # 基类定义（BaseChannel）
├── chatglm.py       # ChatGLM 渠道
├── jd.py            # 京东渠道
├── miyoushe.py      # 米游社渠道
├── xiaoheihe.py     # 小黑盒渠道
├── si399.py         # 4399 渠道
└── README.md        # 本文档
```

## 如何添加新的上传渠道

### 1. 创建渠道模块

在 `channels` 目录下创建新的 Python 文件，例如 `example.py`：

```python
"""
示例图床上传渠道
"""
import requests
from .base import BaseChannel


class ExampleChannel(BaseChannel):
    """示例图床上传渠道"""
    
    # 可选：设置文件大小限制（字节），不设置则无限制
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def __init__(self):
        super().__init__()
        self.upload_url = "https://example.com/upload"
    
    def get_channel_name(self):
        """获取渠道标识符（唯一，用于 API 调用和内部标识）"""
        return "example"
    
    def get_display_name(self):
        """获取渠道显示名称（用于前端下拉框、历史记录等展示）"""
        return "示例图床"
    
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

### 2. 注册渠道

在 `channels/__init__.py` 中导入并注册：

```python
from .example import ExampleChannel

class ChannelManager:
    # ... 其他代码 ...
    
    def _register_default_channels(self):
        """注册默认的上传渠道"""
        self.register(MiyousheChannel())
        self.register(ChatGLMChannel())
        self.register(JDChannel())
        self.register(XiaoheiheChannel())
        self.register(ExampleChannel())  # 新增
```

完成以上两步后，前端会自动：
- 在上传页渠道下拉框显示"示例图床"选项
- 在画廊/历史记录页正确显示渠道名称
- 应用对应的文件大小限制

### 3.（可选）添加缩略图处理

如果新渠道的 CDN 支持图片处理（缩略图加速），需要在前端 `getThumbnailUrl()` 函数中添加处理分支。该函数存在于以下两个文件中：

- `static/js/gallery.js` - 画廊页缩略图（建议宽度 400px）
- `static/js/history.js` - 历史记录页缩略图（建议宽度 600px）

```javascript
function getThumbnailUrl(originalUrl, channel) {
    if (channel === 'miyoushe') {
        // 阿里云 OSS 图片处理
        ...
    }
    if (channel === 'xiaoheihe') {
        // 腾讯云 COS 数据万象
        ...
    }
    // 新增：示例渠道缩略图处理
    if (channel === 'example') {
        const params = '...';  // 根据 CDN 文档编写
        return `${originalUrl}?${params}`;
    }
    return originalUrl;  // 不支持图片处理的渠道返回原图
}
```

> 如果新渠道 CDN 不支持图片处理，则无需修改前端，会自动使用原图。

### 4. 使用新渠道

新渠道注册后，可以通过 API 使用：

**直接文件上传：**
```bash
curl -X POST http://localhost:5500/upload \
  -H "Cookie: auth_token=your_token" \
  -F "file=@image.jpg" \
  -F "channel=example"
```

**从 URL 上传：**
```bash
curl -X POST http://localhost:5500/upload_from_url \
  -H "Cookie: auth_token=your_token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/image.jpg", "channel": "example"}'
```

## 基类方法说明

### 必须实现的方法

| 方法 | 说明 |
|------|------|
| `get_channel_name()` | 返回渠道唯一标识符（小写英文），用于 API 调用和内部标识 |
| `upload(temp_file_path, file)` | 实现具体的上传逻辑，成功返回 `dict`，失败返回 `None` |

### 可选覆写的方法

| 方法 | 默认值 | 说明 |
|------|--------|------|
| `get_display_name()` | 同 `get_channel_name()` | 返回渠道中文显示名，用于前端展示 |

### 可选的类常量

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_FILE_SIZE` | `None`（无限制） | 最大文件大小限制（字节），前端和后端同时生效 |

### 可用的辅助方法

| 方法 | 说明 |
|------|------|
| `self.log_error(message)` | 记录错误日志（自动添加渠道名称前缀） |
| `self.log_info(message)` | 记录信息日志（自动添加渠道名称前缀） |
| `self.get_max_file_size()` | 获取 `MAX_FILE_SIZE` 值 |
| `self.check_file_size(file_path)` | 检查文件是否超出大小限制 |

## 前端配置自动化机制

后端通过 Flask Context Processor 向所有模板注入以下变量：

| 模板变量 | 类型 | 用途 |
|---------|------|------|
| `channels` | `list[dict]` | 渠道列表 `[{name, display_name}, ...]`，用于渲染下拉框 |
| `channel_map` | `dict` | `{标识符: 显示名}` 映射，通过 `<script type="application/json">` 注入 JS |
| `channel_limits` | `dict` | `{标识符: MB值或null}` 映射，通过 `<script type="application/json">` 注入 JS |
| `default_channel` | `str` | 默认渠道标识符 |

## 现有渠道

### 米游社（miyoushe）
- 支持网页端和 App 端两种上传模式
- 上传到阿里云 OSS
- 需要配置 Cookie
- 最大文件限制 20MB
- 画廊/历史记录支持 OSS 缩略图加速

### ChatGLM（chatglm）
- 上传到 ChatGLM 图床
- 无文件大小限制
- 返回完整的图片 URL 和尺寸信息

### 京东（jd）
- 上传到京东反馈系统的图床
- 构建京东 CDN URL
- 无文件大小限制
- 使用本地验证的图片尺寸

### 小黑盒（xiaoheihe）
- 上传到腾讯云 COS（四步流程：获取路径 → 获取凭证 → PUT 上传 → 回调确认）
- 自实现 COS URI 签名和 hkey 请求签名
- 需要配置 Cookie（从浏览器抓取）
- 最大文件限制 20MB
- 画廊/历史记录支持 COS 数据万象缩略图加速

### 4399（4399）
- 上传到 4399 论坛图床（单步 POST 上传）
- 需要配置 4 个特殊请求头（user_agent, mauth, mauthcode, pauth）
- 图片 CDN 地址: `https://fs.img4399.com/bbs/`
- 无文件大小限制
- 使用本地验证的图片尺寸

## 注意事项

1. **错误处理**: 所有异常都应该被捕获并返回 `None`，使用 `self.log_error()` 记录错误信息
2. **文件句柄**: 确保文件句柄在使用后正确关闭（使用 `with` 语句）
3. **返回格式**: 必须返回包含 `file_url`、`width`、`height` 的字典
4. **日志记录**: 使用 `self.log_info()` 和 `self.log_error()` 记录日志，会自动添加渠道标识
5. **渠道名称**: `get_channel_name()` 返回的名称必须唯一，建议使用小写字母
6. **显示名称**: `get_display_name()` 建议实现，否则前端会直接显示英文标识符

## 测试新渠道

添加新渠道后，建议进行以下测试：

1. **前端渠道显示**: 确认上传页下拉框、画廊筛选和历史记录的渠道名称正确显示
2. **文件大小限制**: 确认超出限制的文件在前端被正确拦截
3. **文件上传测试**: 测试直接上传图片文件
4. **URL 上传测试**: 测试从 URL 下载并上传
5. **错误处理测试**: 测试各种异常情况（网络错误、无效响应等）
6. **日志检查**: 检查日志文件确保错误信息被正确记录
