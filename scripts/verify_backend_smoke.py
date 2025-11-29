#!/usr/bin/env python3
"""
后端 Smoke 回归测试脚本

测试基本后端功能：
1. API 文档端点可访问
2. 健康检查端点
3. 认证端点（注册/登录）
4. 基本 API 功能
"""
import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse

# 从环境变量获取 BASE_URL，默认为 http://127.0.0.1:8000
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
API_PREFIX = "/api/v1"

def log(message: str, level: str = "INFO"):
    """打印日志"""
    print(f"[{level}] {message}")

def http_request(path: str, method: str = "GET", data: dict = None, headers: dict = None) -> tuple:
    """发送 HTTP 请求"""
    url = f"{BASE_URL.rstrip('/')}{path}"
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    
    body = None
    if data:
        body = json.dumps(data).encode()
        req_headers["Content-Type"] = "application/json"
    
    try:
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode()
            return resp.getcode(), json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        try:
            error_content = e.read().decode()
            return e.code, json.loads(error_content) if error_content else {}
        except:
            return e.code, {}
    except Exception as e:
        log(f"请求异常: {e}", "ERROR")
        return None, None

def test_openapi():
    """测试 OpenAPI 文档端点"""
    log("测试 OpenAPI 文档端点...")
    code, data = http_request("/openapi.json")
    if code == 200 and isinstance(data, dict) and "openapi" in data:
        log("✅ OpenAPI 文档端点正常", "SUCCESS")
        return True
    else:
        log(f"❌ OpenAPI 文档端点失败: {code}", "ERROR")
        return False

def test_docs():
    """测试 API 文档页面"""
    log("测试 API 文档页面...")
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/docs")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.getcode() == 200:
                log("✅ API 文档页面可访问", "SUCCESS")
                return True
            else:
                log(f"❌ API 文档页面失败: {resp.getcode()}", "ERROR")
                return False
    except Exception as e:
        log(f"❌ API 文档页面异常: {e}", "ERROR")
        return False

def test_auth_endpoints():
    """测试认证端点（不实际注册/登录，只检查端点是否存在）"""
    log("测试认证端点...")
    
    # 测试注册端点（使用无效数据，期望 400 或 422）
    code, _ = http_request(f"{API_PREFIX}/auth/register", "POST", {"username": "", "password": ""})
    if code in [400, 422]:
        log("✅ 注册端点可访问", "SUCCESS")
        register_ok = True
    else:
        log(f"⚠️  注册端点响应异常: {code}", "WARNING")
        register_ok = False
    
    # 测试登录端点（使用无效数据，期望 400 或 401）
    code, _ = http_request(f"{API_PREFIX}/auth/token", "POST", {"username": "test", "password": "test"})
    if code in [400, 401, 422]:
        log("✅ 登录端点可访问", "SUCCESS")
        login_ok = True
    else:
        log(f"⚠️  登录端点响应异常: {code}", "WARNING")
        login_ok = False
    
    return register_ok and login_ok

def test_documents_endpoint():
    """测试文档端点（需要认证，只检查端点是否存在）"""
    log("测试文档端点...")
    
    # 测试文档列表端点（无认证，期望 401）
    code, _ = http_request(f"{API_PREFIX}/documents")
    if code == 401:
        log("✅ 文档端点存在（需要认证）", "SUCCESS")
        return True
    elif code == 200:
        log("⚠️  文档端点允许无认证访问", "WARNING")
        return True
    else:
        log(f"⚠️  文档端点响应异常: {code}", "WARNING")
        return False

def main():
    """主测试函数"""
    log(f"开始后端 Smoke 测试，BASE_URL: {BASE_URL}")
    log("=" * 50)
    
    results = []
    
    # 1. 测试 OpenAPI 文档
    results.append(("OpenAPI 文档", test_openapi()))
    
    # 2. 测试 API 文档页面
    results.append(("API 文档页面", test_docs()))
    
    # 3. 测试认证端点
    results.append(("认证端点", test_auth_endpoints()))
    
    # 4. 测试文档端点
    results.append(("文档端点", test_documents_endpoint()))
    
    # 汇总结果
    log("=" * 50)
    log("测试结果汇总:")
    passed = 0
    failed = 0
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        log(f"  {name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    log("=" * 50)
    log(f"总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        log("🎉 所有测试通过！", "SUCCESS")
        return 0
    else:
        log("❌ 部分测试失败", "ERROR")
        return 1

if __name__ == "__main__":
    sys.exit(main())



