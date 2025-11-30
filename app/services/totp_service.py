"""
双因素认证服务 - 基于 TOTP (Time-based One-Time Password)
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
import logging
from typing import Optional, List, Dict, Any
import json

logger = logging.getLogger(__name__)

# TOTP 配置
TOTP_DIGITS = 6  # 验证码位数
TOTP_PERIOD = 30  # 验证码有效期（秒）
TOTP_ALGORITHM = "sha1"
TOTP_ISSUER = "协作文档系统"  # 在验证器App中显示的名称
BACKUP_CODES_COUNT = 10  # 备用码数量


def generate_secret(length: int = 32) -> str:
    """
    生成 TOTP 密钥
    返回 Base32 编码的密钥
    """
    # 生成随机字节
    random_bytes = secrets.token_bytes(length)
    # Base32 编码（TOTP 标准要求）
    return base64.b32encode(random_bytes).decode('utf-8').rstrip('=')


def generate_backup_codes(count: int = BACKUP_CODES_COUNT) -> List[str]:
    """
    生成备用恢复码
    每个备用码只能使用一次
    """
    codes = []
    for _ in range(count):
        # 生成 8 位随机数字码
        code = ''.join(secrets.choice('0123456789') for _ in range(8))
        # 格式化为 XXXX-XXXX 形式
        formatted = f"{code[:4]}-{code[4:]}"
        codes.append(formatted)
    return codes


def get_totp_uri(secret: str, username: str, issuer: str = TOTP_ISSUER) -> str:
    """
    生成 TOTP URI，用于生成二维码
    格式: otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30
    """
    from urllib.parse import quote
    
    label = f"{issuer}:{username}"
    params = {
        "secret": secret,
        "issuer": issuer,
        "algorithm": TOTP_ALGORITHM.upper(),
        "digits": str(TOTP_DIGITS),
        "period": str(TOTP_PERIOD),
    }
    
    param_str = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"otpauth://totp/{quote(label)}?{param_str}"


def _hotp(secret: str, counter: int) -> str:
    """
    HOTP 算法实现 (RFC 4226)
    """
    # 解码 Base32 密钥
    # 补齐 padding
    missing_padding = len(secret) % 8
    if missing_padding:
        secret += '=' * (8 - missing_padding)
    
    key = base64.b32decode(secret.upper())
    
    # 将 counter 转换为 8 字节大端序
    counter_bytes = struct.pack('>Q', counter)
    
    # HMAC-SHA1
    hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    
    # 动态截取
    offset = hmac_hash[-1] & 0x0F
    truncated = struct.unpack('>I', hmac_hash[offset:offset + 4])[0]
    truncated &= 0x7FFFFFFF
    
    # 取模得到指定位数
    code = truncated % (10 ** TOTP_DIGITS)
    
    # 补零
    return str(code).zfill(TOTP_DIGITS)


def generate_totp(secret: str, timestamp: Optional[int] = None) -> str:
    """
    生成 TOTP 验证码 (RFC 6238)
    """
    if timestamp is None:
        timestamp = int(time.time())
    
    counter = timestamp // TOTP_PERIOD
    return _hotp(secret, counter)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """
    验证 TOTP 验证码
    
    Args:
        secret: TOTP 密钥
        code: 用户输入的验证码
        window: 时间窗口（允许前后几个周期的偏差）
    
    Returns:
        验证是否成功
    """
    if not code or len(code) != TOTP_DIGITS:
        return False
    
    current_time = int(time.time())
    current_counter = current_time // TOTP_PERIOD
    
    # 检查当前时间窗口及前后偏差
    for offset in range(-window, window + 1):
        expected_code = _hotp(secret, current_counter + offset)
        if hmac.compare_digest(expected_code, code):
            return True
    
    return False


# ==================== 数据库操作 ====================

def setup_2fa(db, user_id: int) -> Dict[str, Any]:
    """
    为用户设置 2FA
    返回密钥和备用码（用于显示给用户）
    """
    # 检查是否已经有 2FA
    existing = db.query(
        "SELECT id, is_enabled FROM totp_secrets WHERE user_id = %s LIMIT 1",
        (user_id,)
    )
    
    if existing and existing[0][1]:  # 已启用
        raise ValueError("2FA 已启用，请先禁用后再重新设置")
    
    # 生成新密钥和备用码
    secret = generate_secret()
    backup_codes = generate_backup_codes()
    backup_codes_json = json.dumps(backup_codes)
    
    # 获取用户名（用于生成 URI）
    user_rows = db.query(
        "SELECT username FROM users WHERE id = %s LIMIT 1",
        (user_id,)
    )
    username = user_rows[0][0] if user_rows else f"user_{user_id}"
    
    if existing:
        # 更新现有记录
        db.execute(
            """
            UPDATE totp_secrets 
            SET secret = %s, backup_codes = %s, is_enabled = FALSE, updated_at = now()
            WHERE user_id = %s
            """,
            (secret, backup_codes_json, user_id)
        )
    else:
        # 创建新记录
        db.execute(
            """
            INSERT INTO totp_secrets (user_id, secret, backup_codes, is_enabled)
            VALUES (%s, %s, %s, FALSE)
            """,
            (user_id, secret, backup_codes_json)
        )
    
    uri = get_totp_uri(secret, username)
    
    logger.info(f"用户 {user_id} 设置了 2FA")
    
    return {
        "secret": secret,
        "uri": uri,
        "backup_codes": backup_codes,
    }


def enable_2fa(db, user_id: int, code: str) -> bool:
    """
    启用 2FA（需要验证一次验证码确认用户已正确设置）
    """
    rows = db.query(
        "SELECT secret FROM totp_secrets WHERE user_id = %s AND is_enabled = FALSE LIMIT 1",
        (user_id,)
    )
    
    if not rows:
        raise ValueError("请先设置 2FA")
    
    secret = rows[0][0]
    
    # 验证验证码
    if not verify_totp(secret, code):
        return False
    
    # 启用 2FA
    db.execute(
        "UPDATE totp_secrets SET is_enabled = TRUE, updated_at = now() WHERE user_id = %s",
        (user_id,)
    )
    
    logger.info(f"用户 {user_id} 启用了 2FA")
    return True


def disable_2fa(db, user_id: int, code: str) -> bool:
    """
    禁用 2FA（需要验证码或备用码）
    """
    rows = db.query(
        "SELECT secret, backup_codes FROM totp_secrets WHERE user_id = %s AND is_enabled = TRUE LIMIT 1",
        (user_id,)
    )
    
    if not rows:
        raise ValueError("2FA 未启用")
    
    secret = rows[0][0]
    backup_codes_json = rows[0][1]
    
    # 先尝试 TOTP 验证码
    if verify_totp(secret, code):
        db.execute(
            "DELETE FROM totp_secrets WHERE user_id = %s",
            (user_id,)
        )
        logger.info(f"用户 {user_id} 禁用了 2FA")
        return True
    
    # 再尝试备用码
    if backup_codes_json:
        backup_codes = json.loads(backup_codes_json)
        # 格式化用户输入的备用码
        formatted_code = code.strip().upper()
        if len(formatted_code) == 8:
            formatted_code = f"{formatted_code[:4]}-{formatted_code[4:]}"
        
        if formatted_code in backup_codes:
            db.execute(
                "DELETE FROM totp_secrets WHERE user_id = %s",
                (user_id,)
            )
            logger.info(f"用户 {user_id} 使用备用码禁用了 2FA")
            return True
    
    return False


def verify_2fa(db, user_id: int, code: str) -> bool:
    """
    验证 2FA 验证码（登录时使用）
    """
    rows = db.query(
        "SELECT secret, backup_codes FROM totp_secrets WHERE user_id = %s AND is_enabled = TRUE LIMIT 1",
        (user_id,)
    )
    
    if not rows:
        # 用户未启用 2FA，直接通过
        return True
    
    secret = rows[0][0]
    backup_codes_json = rows[0][1]
    
    # 先尝试 TOTP 验证码
    if verify_totp(secret, code):
        return True
    
    # 再尝试备用码（备用码使用后失效）
    if backup_codes_json:
        backup_codes = json.loads(backup_codes_json)
        # 格式化用户输入的备用码
        formatted_code = code.strip().upper()
        if len(formatted_code) == 8:
            formatted_code = f"{formatted_code[:4]}-{formatted_code[4:]}"
        
        if formatted_code in backup_codes:
            # 移除已使用的备用码
            backup_codes.remove(formatted_code)
            db.execute(
                "UPDATE totp_secrets SET backup_codes = %s, updated_at = now() WHERE user_id = %s",
                (json.dumps(backup_codes), user_id)
            )
            logger.info(f"用户 {user_id} 使用备用码登录（剩余 {len(backup_codes)} 个）")
            return True
    
    return False


def is_2fa_enabled(db, user_id: int) -> bool:
    """检查用户是否启用了 2FA"""
    rows = db.query(
        "SELECT is_enabled FROM totp_secrets WHERE user_id = %s LIMIT 1",
        (user_id,)
    )
    return bool(rows and rows[0][0])


def get_2fa_status(db, user_id: int) -> Dict[str, Any]:
    """获取用户的 2FA 状态"""
    rows = db.query(
        "SELECT is_enabled, backup_codes, created_at FROM totp_secrets WHERE user_id = %s LIMIT 1",
        (user_id,)
    )
    
    if not rows:
        return {
            "enabled": False,
            "setup": False,
            "backup_codes_remaining": 0,
        }
    
    is_enabled = rows[0][0]
    backup_codes_json = rows[0][1]
    created_at = rows[0][2]
    
    backup_codes_count = 0
    if backup_codes_json:
        try:
            backup_codes_count = len(json.loads(backup_codes_json))
        except Exception:
            pass
    
    return {
        "enabled": is_enabled,
        "setup": True,
        "backup_codes_remaining": backup_codes_count,
        "created_at": created_at,
    }


def regenerate_backup_codes(db, user_id: int, code: str) -> List[str]:
    """
    重新生成备用码（需要验证 TOTP）
    """
    rows = db.query(
        "SELECT secret FROM totp_secrets WHERE user_id = %s AND is_enabled = TRUE LIMIT 1",
        (user_id,)
    )
    
    if not rows:
        raise ValueError("2FA 未启用")
    
    secret = rows[0][0]
    
    # 验证 TOTP
    if not verify_totp(secret, code):
        raise ValueError("验证码错误")
    
    # 生成新备用码
    new_codes = generate_backup_codes()
    db.execute(
        "UPDATE totp_secrets SET backup_codes = %s, updated_at = now() WHERE user_id = %s",
        (json.dumps(new_codes), user_id)
    )
    
    logger.info(f"用户 {user_id} 重新生成了备用码")
    return new_codes
