import requests
import json

# 测试用户注册
url = "http://localhost:8000/api/v1/auth/register"
data = {
    "username": "testuser", 
    "password": "test123", 
    "email": "test@example.com"
}

try:
    response = requests.post(url, json=data, timeout=5)
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.text}")
except Exception as e:
    print(f"错误: {e}")