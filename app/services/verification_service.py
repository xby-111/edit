"""
验证码服务 - 用于密码重置、验证码登录等场景
"""
import random
import string
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 验证码类型
CODE_TYPE_PASSWORD_RESET = "password_reset"
CODE_TYPE_LOGIN = "login"
CODE_TYPE_EMAIL_VERIFY = "email_verify"
CODE_TYPE_PHONE_VERIFY = "phone_verify"

# 验证码配置
CODE_LENGTH = 6
CODE_EXPIRE_MINUTES = 10
MAX_ATTEMPTS = 5  # 最大尝试次数


def generate_code(length: int = CODE_LENGTH) -> str:
    """生成数字验证码"""
    return ''.join(random.choices(string.digits, k=length))


def hash_code(code: str) -> str:
    """对验证码进行哈希，存储时使用"""
    return hashlib.sha256(code.encode()).hexdigest()


def create_verification_code(
    db,
    *,
    user_id: Optional[int],
    email: Optional[str] = None,
    phone: Optional[str] = None,
    code_type: str,
) -> str:
    """
    创建验证码并存储到数据库
    
    Args:
        db: 数据库连接
        user_id: 用户ID（可选，未注册用户可能没有）
        email: 邮箱地址
        phone: 手机号
        code_type: 验证码类型
    
    Returns:
        生成的验证码明文（用于发送给用户）
    """
    code = generate_code()
    code_hash = hash_code(code)
    expires_at = datetime.utcnow() + timedelta(minutes=CODE_EXPIRE_MINUTES)
    
    # 先删除该用户/邮箱/手机的旧验证码（同类型）
    if user_id:
        db.execute(
            "DELETE FROM verification_codes WHERE user_id = %s AND code_type = %s",
            (user_id, code_type)
        )
    if email:
        db.execute(
            "DELETE FROM verification_codes WHERE email = %s AND code_type = %s",
            (email, code_type)
        )
    if phone:
        db.execute(
            "DELETE FROM verification_codes WHERE phone = %s AND code_type = %s",
            (phone, code_type)
        )
    
    # 插入新验证码
    db.execute(
        """
        INSERT INTO verification_codes (user_id, email, phone, code_hash, code_type, expires_at, attempts)
        VALUES (%s, %s, %s, %s, %s, %s, 0)
        """,
        (user_id, email, phone, code_hash, code_type, expires_at)
    )
    
    logger.info(f"验证码已创建: type={code_type}, email={email}, phone={phone}")
    return code


def verify_code(
    db,
    *,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    code: str,
    code_type: str,
    consume: bool = True,
) -> Dict[str, Any]:
    """
    验证验证码
    
    Args:
        db: 数据库连接
        email: 邮箱地址
        phone: 手机号
        code: 用户提交的验证码
        code_type: 验证码类型
        consume: 验证成功后是否消费（删除）验证码
    
    Returns:
        验证结果字典，包含 success, message, user_id 等
    """
    code_hash = hash_code(code)
    
    # 构建查询条件
    conditions = ["code_type = %s", "code_hash = %s"]
    params = [code_type, code_hash]
    
    if email:
        conditions.append("email = %s")
        params.append(email)
    if phone:
        conditions.append("phone = %s")
        params.append(phone)
    
    where_clause = " AND ".join(conditions)
    
    # 查询验证码记录
    rows = db.query(
        f"""
        SELECT id, user_id, expires_at, attempts
        FROM verification_codes
        WHERE {where_clause}
        LIMIT 1
        """,
        tuple(params)
    )
    
    if not rows:
        # 可能是验证码错误，增加尝试次数
        _increment_attempts(db, email=email, phone=phone, code_type=code_type)
        return {"success": False, "message": "验证码错误或已过期"}
    
    record = rows[0]
    record_id = record[0]
    user_id = record[1]
    expires_at = record[2]
    attempts = record[3]
    
    # 检查是否超过最大尝试次数
    if attempts >= MAX_ATTEMPTS:
        db.execute("DELETE FROM verification_codes WHERE id = %s", (record_id,))
        return {"success": False, "message": "验证码已失效，请重新获取"}
    
    # 检查是否过期
    if expires_at < datetime.utcnow():
        db.execute("DELETE FROM verification_codes WHERE id = %s", (record_id,))
        return {"success": False, "message": "验证码已过期，请重新获取"}
    
    # 验证成功
    if consume:
        db.execute("DELETE FROM verification_codes WHERE id = %s", (record_id,))
    
    logger.info(f"验证码验证成功: type={code_type}, email={email}, phone={phone}")
    return {"success": True, "message": "验证成功", "user_id": user_id}


def _increment_attempts(
    db,
    *,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    code_type: str,
) -> None:
    """增加验证码尝试次数"""
    conditions = ["code_type = %s"]
    params = [code_type]
    
    if email:
        conditions.append("email = %s")
        params.append(email)
    if phone:
        conditions.append("phone = %s")
        params.append(phone)
    
    where_clause = " AND ".join(conditions)
    
    db.execute(
        f"UPDATE verification_codes SET attempts = attempts + 1 WHERE {where_clause}",
        tuple(params)
    )


def cleanup_expired_codes(db) -> int:
    """清理过期的验证码，返回清理数量"""
    result = db.execute(
        "DELETE FROM verification_codes WHERE expires_at < %s",
        (datetime.utcnow(),)
    )
    count = result if isinstance(result, int) else 0
    logger.info(f"已清理 {count} 条过期验证码")
    return count


# ==================== 邮件/短信发送模拟 ====================
# 注意：实际生产环境需要集成真正的邮件/短信服务

def send_email_code(email: str, code: str, code_type: str) -> bool:
    """
    发送邮件验证码
    
    注意：这是模拟实现，实际生产环境需要集成邮件服务如：
    - SMTP (smtplib)
    - SendGrid
    - AWS SES
    - 阿里云邮件推送
    """
    subject_map = {
        CODE_TYPE_PASSWORD_RESET: "密码重置验证码",
        CODE_TYPE_LOGIN: "登录验证码",
        CODE_TYPE_EMAIL_VERIFY: "邮箱验证码",
    }
    subject = subject_map.get(code_type, "验证码")
    
    # 模拟发送，实际应调用邮件服务
    logger.info(f"[模拟邮件] 发送到 {email}: {subject} - 验证码: {code}")
    
    # TODO: 集成实际邮件服务
    # 示例:
    # import smtplib
    # from email.mime.text import MIMEText
    # msg = MIMEText(f"您的验证码是：{code}，{CODE_EXPIRE_MINUTES}分钟内有效。")
    # msg['Subject'] = subject
    # msg['From'] = 'noreply@example.com'
    # msg['To'] = email
    # with smtplib.SMTP('smtp.example.com') as server:
    #     server.login('user', 'password')
    #     server.send_message(msg)
    
    return True


def send_sms_code(phone: str, code: str, code_type: str) -> bool:
    """
    发送短信验证码
    
    注意：这是模拟实现，实际生产环境需要集成短信服务如：
    - 阿里云短信
    - 腾讯云短信
    - Twilio
    """
    template_map = {
        CODE_TYPE_PASSWORD_RESET: "您正在重置密码",
        CODE_TYPE_LOGIN: "您正在登录",
        CODE_TYPE_PHONE_VERIFY: "您正在验证手机号",
    }
    template = template_map.get(code_type, "验证码")
    
    # 模拟发送，实际应调用短信服务
    logger.info(f"[模拟短信] 发送到 {phone}: {template} - 验证码: {code}")
    
    # TODO: 集成实际短信服务
    # 示例 (阿里云短信):
    # from alibabacloud_dysmsapi20170525.client import Client
    # client.send_sms(...)
    
    return True
