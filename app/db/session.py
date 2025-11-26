# app/db/session.py

import logging
import urllib.parse
import time
import re
import functools
from typing import Generator, Any, Optional, Sequence
import py_opengauss
from app.core.config import settings

logger = logging.getLogger(__name__)

_PATCH_INSTALLED = False


def _convert_percent_s_to_dollar(sql: str) -> str:
    """
    Convert psycopg2-style %s placeholders to openGauss $1,$2,... placeholders.

    Safety:
    - Do NOT replace inside single quotes: '...' (handles '' escape)
    - Do NOT replace inside double quotes: "..." (identifiers)
    - Do NOT replace inside -- line comments
    - Do NOT replace inside /* */ block comments
    - Handle %% as literal %
    - Best-effort handle dollar-quoted strings: $tag$ ... $tag$
    """
    if "%s" not in sql:
        return sql

    out = []
    i = 0
    n = 0
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: Optional[str] = None  # e.g. "$$" or "$tag$"

    def starts_dollar_tag(s: str, pos: int) -> Optional[str]:
        # $tag$ where tag is [A-Za-z_][A-Za-z0-9_]* or empty (i.e. $$)
        if pos >= len(s) or s[pos] != "$":
            return None
        j = pos + 1
        while j < len(s) and (s[j].isalnum() or s[j] == "_"):
            j += 1
        if j < len(s) and s[j] == "$":
            return s[pos : j + 1]
        return None

    while i < len(sql):
        ch = sql[i]

        # Handle block comments /* */
        if not in_single and not in_double and not in_line_comment and not dollar_tag:
            if i + 1 < len(sql) and sql[i:i+2] == "/*":
                in_block_comment = True
                out.append("/*")
                i += 2
                continue
            if in_block_comment and i + 1 < len(sql) and sql[i:i+2] == "*/":
                in_block_comment = False
                out.append("*/")
                i += 2
                continue
            if in_block_comment:
                out.append(ch)
                i += 1
                continue

        # Handle line comments --
        if not in_single and not in_double and not in_block_comment and not dollar_tag:
            if i + 1 < len(sql) and sql[i:i+2] == "--":
                in_line_comment = True
                out.append("--")
                i += 2
                continue
            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                out.append(ch)
                i += 1
                continue

        # Dollar-quote open/close check (only when not in ' or " or comments)
        if not in_single and not in_double and not in_line_comment and not in_block_comment:
            if dollar_tag is None:
                tag = starts_dollar_tag(sql, i)
                if tag:
                    dollar_tag = tag
                    out.append(tag)
                    i += len(tag)
                    continue
            else:
                if sql.startswith(dollar_tag, i):
                    out.append(dollar_tag)
                    i += len(dollar_tag)
                    dollar_tag = None
                    continue

        # Inside dollar-quote: copy raw until closing tag
        if dollar_tag is not None:
            out.append(ch)
            i += 1
            continue

        # Toggle quote states (basic SQL escaping: '' inside single quotes)
        if ch == "'" and not in_double and not in_line_comment and not in_block_comment:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single and not in_line_comment and not in_block_comment:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue

        # Replace only when not inside quotes or comments
        if not in_single and not in_double and not in_line_comment and not in_block_comment and ch == "%":
            # literal %%
            if i + 1 < len(sql) and sql[i + 1] == "%":
                out.append("%")
                i += 2
                continue
            # placeholder %s
            if i + 1 < len(sql) and sql[i + 1] == "s":
                n += 1
                out.append(f"${n}")
                i += 2
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _wrap_method(ConnCls, method_name: str) -> bool:
    """
    Wrap a Connection method to convert percent-placeholder (%s) -> $n before calling original.
    
    Returns True if method exists and was successfully wrapped (or already wrapped), False otherwise.
    """
    if not hasattr(ConnCls, method_name):
        return False
    
    orig = getattr(ConnCls, method_name)
    
    # Check if already wrapped (幂等性检查)
    if getattr(orig, "_percent_placeholder_patched", False):
        return True
    
    # 锁住原函数引用，避免 late-binding bug
    original_method = orig
    
    @functools.wraps(original_method)
    def wrapped(self, query, *args, **kwargs):
        try:
            if isinstance(query, str) and "%s" in query:
                query = _convert_percent_s_to_dollar(query)
        except Exception:
            # Never break DB calls because of conversion errors
            logger.warning("openGauss percent-placeholder convert failed; fallback to original query", exc_info=True)
        # 使用锁定的原函数引用
        return original_method(self, query, *args, **kwargs)
    
    # 标记已包装，防止重复包装
    wrapped._percent_placeholder_patched = True
    setattr(ConnCls, method_name, wrapped)
    return True


def _install_pyopengauss_percent_patch() -> bool:
    """
    Install monkey patch for py_opengauss.driver.pq3.Connection methods.
    Patches both _prepare and prepare to ensure coverage across versions.
    
    Returns:
        True if at least one method was patched, False otherwise.
    
    Note:
        - 幂等：重复调用不会重复包装
        - 失败不阻塞：异常只记录日志，不抛出
        - 自动安装：模块导入时自动执行
    """
    global _PATCH_INSTALLED
    if _PATCH_INSTALLED:
        return True
    
    try:
        from py_opengauss.driver import pq3  # type: ignore
        Conn = pq3.Connection  # class
        
        # 依次尝试 patch prepare 和 _prepare（存在才 patch）
        ok1 = _wrap_method(Conn, "prepare")
        ok2 = _wrap_method(Conn, "_prepare")
        
        _PATCH_INSTALLED = bool(ok1 or ok2)
        logger.info(f"py_opengauss percent-placeholder patch installed: {_PATCH_INSTALLED}")
        return _PATCH_INSTALLED
    except Exception as e:
        logger.warning(f"py_opengauss percent-placeholder patch install failed: {e}", exc_info=True)
        logger.info(f"py_opengauss percent-placeholder patch installed: False")
        return False


# Install at import-time (must happen before first connection usage)
_install_pyopengauss_percent_patch()


class OpenGaussCompat:
    """
    将业务层常见的 %s 占位符参数化 SQL 转成 py-opengauss/openGauss 支持的 $1,$2,... 形式，
    并通过 prepare() 执行，从而避免服务器解析 '%' 报错。
    """
    def __init__(self, raw_conn):
        self.raw = raw_conn

    @staticmethod
    def _convert_placeholders(sql: str) -> str:
        if "%s" not in sql:
            return sql
        i = 0
        def repl(_m):
            nonlocal i
            i += 1
            return f"${i}"
        return re.sub(r"%s", repl, sql)

    def query(self, sql: str, params: Optional[Sequence[Any]] = None):
        # 有参数：必须走 prepare 参数化执行
        if params is not None:
            converted = self._convert_placeholders(sql)
            logger.debug(f"OpenGaussCompat: {sql} -> {converted}")
            stmt = self.raw.prepare(converted)
            return stmt(*params)
        # 无参数：尽量走原生（不同版本 py-opengauss 可能只有 prepare）
        if hasattr(self.raw, "query"):
            return self.raw.query(sql)
        return self.raw.prepare(sql)()

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None):
        if params is not None:
            converted = self._convert_placeholders(sql)
            logger.debug(f"OpenGaussCompat: {sql} -> {converted}")
            stmt = self.raw.prepare(converted)
            return stmt(*params)
        if hasattr(self.raw, "execute"):
            return self.raw.execute(sql)
        return self.raw.prepare(sql)()

    def __call__(self, sql, *parameters):
        """支持连接对象的直接调用，这是py-opengauss的调用方式"""
        if parameters:
            # 转换占位符
            converted = self._convert_placeholders(sql)
            logger.debug(f"OpenGaussCompat __call__: {sql} -> {converted}")
            # 使用prepare方法执行参数化查询
            return self.raw.prepare(converted)(*parameters)
        else:
            # 无参数时直接执行
            return self.raw(sql)

    def __getattr__(self, name):
        # 代理未覆盖的方法（commit/close/transaction 等）
        return getattr(self.raw, name)

# 从配置中读取数据库连接字符串
# py-opengauss 需要特定的连接格式
DATABASE_URL = settings.DATABASE_URL

# 解析连接字符串
# 格式: opengauss://username:password@host:port/database
def parse_database_url(url):
    """解析数据库连接字符串，支持密码中的特殊字符"""
    try:
        # 移除协议前缀
        if url.startswith('opengauss://'):
            url = url[12:]
        
        # 分离认证信息和主机信息
        if '@' in url:
            auth, host_db = url.split('@', 1)
        else:
            raise ValueError("Invalid database URL: missing @")
        
        # 分离用户名和密码
        if ':' in auth:
            username, password = auth.split(':', 1)
        else:
            raise ValueError("Invalid database URL: missing password")
        
        # URL decode 密码（处理特殊字符如 %40）
        password = urllib.parse.unquote(password)
        
        # 分离主机和数据库
        if '/' in host_db:
            host_port, database = host_db.split('/', 1)
        else:
            raise ValueError("Invalid database URL: missing database")
        
        # 分离主机和端口
        if ':' in host_port:
            host, port = host_port.split(':', 1)
        else:
            host = host_port
            port = 5432  # 默认端口
        
        return {
            'host': host,
            'port': int(port),
            'user': username,
            'password': password,
            'database': database
        }
    except Exception as e:
        logger.error(f"解析数据库连接字符串失败: {e}")
        raise


def create_connection(max_retries=3):
    """创建新的数据库连接（延迟连接 + 重试机制）"""
    last_error = None
    for attempt in range(max_retries):
        try:
            # 解析连接参数
            db_params = parse_database_url(DATABASE_URL)
            # 安全地记录连接参数（不包含密码）
            logger.info(f"尝试连接数据库 (尝试 {attempt + 1}/{max_retries}): host={db_params['host']}, port={db_params['port']}, user={db_params['user']}, database={db_params['database']}")
            
            # 使用解析后的参数创建连接
            # py-opengauss 使用 open 方法
            raw_conn = py_opengauss.open(DATABASE_URL)
            logger.info("openGauss 连接创建成功")
            
            # 返回原始连接（兼容层将在get_db中应用）
            return raw_conn
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避：1s, 2s, 4s
                logger.warning(f"连接数据库失败，{wait_time}秒后重试: {e}")
                time.sleep(wait_time)
            else:
                logger.error(f"创建 openGauss 连接失败（已重试{max_retries}次）: {e}", exc_info=True)
    
    # 所有重试都失败
    raise last_error


def get_db() -> Generator[Any, None, None]:
    """
    FastAPI 依赖：为每个请求提供独立的数据库连接。
    使用上下文管理器确保连接正确关闭。
    """
    conn = None
    try:
        conn = create_connection()
        yield OpenGaussCompat(conn)  # 关键：返回兼容层包装的连接
    except Exception as e:
        logger.error(f"Database connection error: {e}", exc_info=True)
        raise
    finally:
        if conn:
            try:
                conn.close()
                logger.debug("数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接失败: {e}")


def get_db_connection():
    """
    获取数据库连接（用于脚本等非FastAPI场景）
    注意：调用者需要负责关闭连接
    """
    return OpenGaussCompat(create_connection())


def close_connection_safely(conn):
    """安全关闭数据库连接"""
    if conn:
        try:
            conn.close()
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}")


# 向后兼容的全局连接（仅用于非关键路径，如脚本）
_global_conn = None

def get_global_connection():
    """获取全局连接（向后兼容，仅用于脚本等非并发场景）"""
    global _global_conn
    if _global_conn is None:
        try:
            _global_conn = OpenGaussCompat(create_connection())
            logger.warning("使用全局连接，仅建议用于脚本等非并发场景")
        except Exception as e:
            logger.error(f"创建全局连接失败: {e}")
            raise
    return _global_conn