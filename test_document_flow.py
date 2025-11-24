"""文档 CRUD 流程测试"""
import requests
import json
import sys
import time

BASE_URL = "http://localhost:8000"

def register_and_login_user(username, email, password):
    """注册并登录用户，返回 token"""
    # 注册用户
    register_data = {
        "username": username,
        "email": email,
        "password": password
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=register_data)
    if response.status_code == 400 and "已被注册" in response.text:
        # 用户已存在，直接登录
        pass
    elif response.status_code != 200:
        print(f"注册用户失败: {response.status_code} - {response.text}")
        return None
    
    # 登录获取 token
    login_data = {
        "username": username,
        "password": password
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/auth/token", data=login_data)
    if response.status_code != 200:
        print(f"登录失败: {response.status_code} - {response.text}")
        return None
    
    token_data = response.json()
    return token_data.get("access_token")

def test_document_flow():
    """测试完整的文档 CRUD 流程"""
    print("开始文档 CRUD 流程测试...")
    
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
    
    # 1. 注册并登录测试用户
    print("\n1. 注册并登录测试用户...")
    token = register_and_login_user("docuser", "doc@example.com", "123456")
    if not token:
        print("用户认证失败")
        return False
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    print("用户认证成功")
    
    # 2. 创建文档
    print("\n2. 创建文档...")
    create_data = {
        "title": "测试文档",
        "content": "这是测试文档内容",
        "status": "active"
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/documents", json=create_data, headers=headers)
    print(f"创建文档状态码: {response.status_code}")
    print(f"创建文档响应: {response.text}")
    
    if response.status_code != 201:
        print("创建文档失败")
        return False
    
    document = response.json()
    document_id = document.get('id')
    print(f"文档创建成功，ID: {document_id}")
    
    # 3. 获取文档列表
    print("\n3. 获取文档列表...")
    response = requests.get(f"{BASE_URL}/api/v1/documents", headers=headers)
    print(f"获取文档列表状态码: {response.status_code}")
    
    if response.status_code != 200:
        print("获取文档列表失败")
        return False
    
    documents = response.json()
    print(f"文档列表: {len(documents)} 个文档")
    
    # 确认刚创建的文档在列表中
    found = False
    for doc in documents:
        if doc.get('id') == document_id:
            found = True
            print(f"找到创建的文档: {doc.get('title')}")
            break
    
    if not found:
        print("创建的文档不在列表中")
        return False
    
    # 4. 获取单个文档详情
    print("\n4. 获取单个文档详情...")
    response = requests.get(f"{BASE_URL}/api/v1/documents/{document_id}", headers=headers)
    print(f"获取文档详情状态码: {response.status_code}")
    print(f"获取文档详情响应: {response.text}")
    
    if response.status_code != 200:
        print("获取文档详情失败")
        return False
    
    document_detail = response.json()
    if document_detail.get('title') != "测试文档" or document_detail.get('content') != "这是测试文档内容":
        print("文档详情内容不匹配")
        return False
    
    print("文档详情验证通过")
    
    # 5. 更新文档
    print("\n5. 更新文档...")
    update_data = {
        "title": "更新后的测试文档",
        "content": "这是更新后的测试文档内容"
    }
    
    response = requests.put(f"{BASE_URL}/api/v1/documents/{document_id}", json=update_data, headers=headers)
    print(f"更新文档状态码: {response.status_code}")
    print(f"更新文档响应: {response.text}")
    
    if response.status_code != 200:
        print("更新文档失败")
        return False
    
    updated_document = response.json()
    print(f"文档更新成功: {updated_document.get('title')}")
    
    # 6. 再次获取详情，确认内容已更新
    print("\n6. 验证文档更新...")
    response = requests.get(f"{BASE_URL}/api/v1/documents/{document_id}", headers=headers)
    if response.status_code != 200:
        print("获取更新后的文档详情失败")
        return False
    
    document_detail = response.json()
    if document_detail.get('title') != "更新后的测试文档" or document_detail.get('content') != "这是更新后的测试文档内容":
        print("文档更新验证失败")
        return False
    
    print("文档更新验证通过")
    
    # 7. 删除文档
    print("\n7. 删除文档...")
    response = requests.delete(f"{BASE_URL}/api/v1/documents/{document_id}", headers=headers)
    print(f"删除文档状态码: {response.status_code}")
    
    if response.status_code != 204:
        print("删除文档失败")
        return False
    
    print("文档删除成功")
    
    # 8. 确认文档已不存在
    print("\n8. 确认文档已不存在...")
    response = requests.get(f"{BASE_URL}/api/v1/documents/{document_id}", headers=headers)
    print(f"获取已删除文档状态码: {response.status_code}")
    
    if response.status_code != 404:
        print("文档删除验证失败，应该返回404")
        return False
    
    print("文档删除验证通过")
    
    # 9. 确认文档不在列表中
    print("\n9. 确认文档不在列表中...")
    response = requests.get(f"{BASE_URL}/api/v1/documents", headers=headers)
    if response.status_code != 200:
        print("获取文档列表失败")
        return False
    
    documents = response.json()
    found = False
    for doc in documents:
        if doc.get('id') == document_id:
            found = True
            break
    
    if found:
        print("已删除的文档仍在列表中")
        return False
    
    print("文档不在列表中，验证通过")
    
    print("\n✅ 文档 CRUD 流程测试通过")
    return True

if __name__ == "__main__":
    success = test_document_flow()
    sys.exit(0 if success else 1)