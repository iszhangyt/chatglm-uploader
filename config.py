"""
配置管理模块
从 config.yaml 加载配置，未找到配置文件时使用默认值
"""
import os
import yaml

_config = None

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.yaml')

DEFAULTS = {
    'server': {
        'host': '0.0.0.0',
        'port': 5500,
        'debug': False,
    },
    'auth': {
        'default_code': 'admin123',
        'token_expiry_days': 30,
        'cookie_secure': False,
    },
    'log': {
        'level': 'INFO',
    },
    'channel': {
        'default': 'miyoushe',
    },
    'miyoushe': {
        'api_type': 'web',
        'cookie': '',
        'app_cookie': '',
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 中的值优先"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    """从 config.yaml 加载配置，不存在时使用默认值"""
    global _config

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f) or {}
        _config = _deep_merge(DEFAULTS, user_config)
    else:
        _config = DEFAULTS.copy()

    return _config


def get_config() -> dict:
    """获取当前配置，首次调用时自动加载"""
    global _config
    if _config is None:
        return load_config()
    return _config
