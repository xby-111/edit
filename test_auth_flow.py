"""端到端认证流程测试"""
import requests
import json
import sys
import time

BASE_URL = "http://localhost:8000"

def test_auth_flow():
    """测试完整的认证流程"""
    print("开始端到端认证流程测试...")
    
    # 等待服务启动
    print("等待服务启动...")
    for i in range(10):
        try:
            response = requests.get(f"{BASE_URL}/api/docs")
            if response.status_code == 200:
                print("服务已启动")
                break
        except:
            pass
        time.sleep(1)
    else:
        print("服务启动失败")
        return False
    
    # 1. 测试用户注册
    print("\n1. 测试用户注册...")
    register_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "123456"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=register_data)
        print(f"注册接口状态码: {response.status_code}")
        print(f"注册接口响应: {response.text}")
        
        if response.status_code != 200:
            print("注册失败")
            return False
        
        user_data = response.json()
        print(f"注册成功，用户ID: {user_data.get('id')}")
    except Exception as e:
        print(f"注册请求出错: {e}")
        return False
    
    # 2. 测试重复注册（应该返回错误）
    print("\n2. 测试重复注册...")
    try:
        response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=register_data)
        print(f"重复注册状态码: {response.status_code}")
        print(f"重复注册响应: {response.text}")
        
        if response.status_code != 400:
            print("重复注册应该返回400错误")
            return False
        
        print("重复注册正确返回400错误")
    except Exception as e:
        print(f"重复注册请求出错: {e}")
        return False
    
    # 3. 测试用户登录
    print("\n3. 测试用户登录...")
    login_data = {
        "username": "testuser",
        "password": "123456"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/v1/auth/token", data=login_data)
        print(f"登录接口状态码: {response.status_code}")
        print(f"登录接口响应: {response.text}")
        
        if response.status_code != 200:
            print("登录失败")
            return False
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        print(f"登录成功，获得token: {access_token[:20]}...")
    except Exception as e:
        print(f"登录请求出错: {e}")
        return False
    
    # 4. 测试获取用户信息
    print("\n4. 测试获取用户信息...")
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    try:
        response = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=headers)
        print(f"获取用户信息状态码: {response.status_code}")
        print(f"获取用户信息响应: {response.text}")
        
        if response.status_code != 200:
            print("获取用户信息失败")
            return False
        
        me_data = response.json()
        print(f"用户信息: {me_data}")
    except Exception as e:
        print(f"获取用户信息请求出错: {e}")
        return False
    
    # 5. 测试错误密码登录
    print("\n5. 测试错误密码登录...")
    wrong_login_data = {
        "username": "testuser",
        "password": "wrongpassword"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/v1/auth/token", data=wrong_login_data)
        print(f"错误密码登录状态码: {response.status_code}")
        print(f"错误密码登录响应: {response.text}")
        
        if response.status_code != 401:
            print("错误密码应该返回401错误")
            return False
        
        print("错误密码正确返回401错误")
    except Exception as e:
        print(f"错误密码登录请求出错: {e}")
        return False
    
    print("\n✅ 所有认证流程测试通过！")
    return True

if __name__ == "__main__":
    success = test_auth_flow()
    sys.exit(0 if success else 1)