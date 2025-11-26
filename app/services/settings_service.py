"""系统配置相关服务"""
import json
from typing import Any, Optional


def get_setting(conn, key: str) -> Optional[Any]:
    rows = conn.query("SELECT value FROM system_settings WHERE key = %s", (key,))
    if not rows:
        return None
    raw_value = rows[0][0]
    try:
        return json.loads(raw_value)
    except Exception:
        return raw_value


def is_feature_enabled(conn, key: str, default: bool = True) -> bool:
    value = get_setting(conn, key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"false", "0", "off", "no"}:
            return False
        if lowered in {"true", "1", "on", "yes"}:
            return True
    try:
        return bool(value)
    except Exception:
        return default
