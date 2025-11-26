#!/usr/bin/env python3
"""
多用户共享与协作编辑验证脚本

测试场景：
1. 注册/登录 3 个用户：A/B/C
2. A 创建文档 doc
3. A 批量共享 doc 给 B/C（B editor, C viewer）
4. B/C 都能通过 HTTP 获取 doc 详情（can_view）
5. A、B、C 同时建立 WebSocket 连接到同一个 doc_id
6. A 发 content_update，B/C 都能收到
7. B 发 content_update，A/C 都能收到
8. C（viewer）发 content_update 应被拒绝（收到 error，不应持久化）
9. 最终数据库 content 与 A/B 最后一次更新一致（持久化正确）
"""

import asyncio
import json
import sys
import time
import websockets
from typing import Dict, List

import requests

# 配置
BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000"

# 测试用户数据
USERS = {
    "user_a": {"username": "test_user_a", "email": "test_a@example.com", "password": "test123456"},
    "user_b": {"username": "test_user_b", "email": "test_b@example.com", "password": "test123456"},
    "user_c": {"username": "test_user_c", "email": "test_c@example.com", "password": "test123456"},
}

# 存储认证信息
tokens = {}
user_ids = {}

def log(message: str, level: str = "INFO"):
    """打印日志"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def register_user(user_key: str) -> bool:
    """注册用户"""
    user_data = USERS[user_key]
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json=user_data
        )
        if response.status_code in [200, 201]:
            log(f"✅ 用户 {user_data['username']} 注册成功")
            return True
        elif response.status_code == 400 and ("already registered" in response.text or "已被注册" in response.text):
            log(f"ℹ️  用户 {user_data['username']} 已存在，跳过注册")
            return True
        else:
            log(f"❌ 用户 {user_data['username']} 注册失败: {response.status_code} {response.text}", "ERROR")
            return False
    except Exception as e:
        log(f"❌ 用户 {user_data['username']} 注册异常: {e}", "ERROR")
        return False

def login_user(user_key: str) -> bool:
    """登录用户"""
    user_data = USERS[user_key]
    try:
        form_data = {
            "username": user_data["username"],
            "password": user_data["password"]
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/token",
            data=form_data
        )
        if response.status_code == 200:
            data = response.json()
            tokens[user_key] = data["access_token"]
            # 获取用户ID
            me_response = requests.get(
                f"{BASE_URL}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {tokens[user_key]}"}
            )
            if me_response.status_code == 200:
                user_ids[user_key] = me_response.json()["id"]
            log(f"✅ 用户 {user_data['username']} 登录成功 (ID: {user_ids.get(user_key, 'unknown')})")
            return True
        else:
            log(f"❌ 用户 {user_data['username']} 登录失败: {response.status_code} {response.text}", "ERROR")
            return False
    except Exception as e:
        log(f"❌ 用户 {user_data['username']} 登录异常: {e}", "ERROR")
        return False

def create_document(user_key: str) -> Dict:
    """创建文档"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/documents",
            json={"title": "多用户协作测试文档", "content": "<p>初始内容</p>"},
            headers={"Authorization": f"Bearer {tokens[user_key]}"}
        )
        if response.status_code == 201:
            doc = response.json()
            log(f"✅ 用户 {USERS[user_key]['username']} 创建文档成功 (ID: {doc['id']})")
            return doc
        else:
            log(f"❌ 创建文档失败: {response.status_code} {response.text}", "ERROR")
            return {}
    except Exception as e:
        log(f"❌ 创建文档异常: {e}", "ERROR")
        return {}

def batch_add_collaborators(user_key: str, doc_id: int, collaborators: List[Dict]) -> bool:
    """批量添加协作者"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/documents/{doc_id}/collaborators/batch",
            json={"users": collaborators},
            headers={"Authorization": f"Bearer {tokens[user_key]}"}
        )
        if response.status_code == 200:
            result = response.json()
            log(f"✅ 批量添加协作者成功: {result['message']}")
            for res in result.get("results", []):
                status = "✅" if res["success"] else "❌"
                log(f"   {status} {res['username']}: {res['message']}")
            return True
        else:
            log(f"❌ 批量添加协作者失败: {response.status_code} {response.text}", "ERROR")
            return False
    except Exception as e:
        log(f"❌ 批量添加协作者异常: {e}", "ERROR")
        return False

def get_document(user_key: str, doc_id: int) -> Dict:
    """获取文档详情"""
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {tokens[user_key]}"}
        )
        if response.status_code == 200:
            doc = response.json()
            log(f"✅ 用户 {USERS[user_key]['username']} 获取文档成功")
            return doc
        else:
            log(f"❌ 用户 {USERS[user_key]['username']} 获取文档失败: {response.status_code} {response.text}", "ERROR")
            return {}
    except Exception as e:
        log(f"❌ 用户 {USERS[user_key]['username']} 获取文档异常: {e}", "ERROR")
        return {}

async def websocket_connect(user_key: str, doc_id: int, message_queue: asyncio.Queue, timeout: float = 30.0) -> bool:
    """建立WebSocket连接并监听消息"""
    try:
        uri = f"{WS_URL}/ws/documents/{doc_id}?token={tokens[user_key]}&username={USERS[user_key]['username']}"
        async with websockets.connect(uri) as websocket:
            log(f"✅ 用户 {USERS[user_key]['username']} WebSocket 连接成功")
            
            # 监听消息（带超时）
            try:
                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                        data = json.loads(message)
                        await message_queue.put({"user": user_key, "message": data})
                        log(f"📨 用户 {USERS[user_key]['username']} 收到消息: {data.get('type', 'unknown')}")
                    except asyncio.TimeoutError:
                        log(f"⏱️  用户 {USERS[user_key]['username']} WebSocket 接收超时，继续监听...")
                        continue
            except websockets.exceptions.ConnectionClosed:
                log(f"ℹ️  用户 {USERS[user_key]['username']} WebSocket 连接关闭")
            except Exception as e:
                log(f"❌ 用户 {USERS[user_key]['username']} WebSocket 接收消息异常: {e}", "ERROR")
        return True
    except Exception as e:
        log(f"❌ 用户 {USERS[user_key]['username']} WebSocket 连接异常: {e}", "ERROR")
        return False

async def websocket_send(user_key: str, doc_id: int, content: str, message_queue: asyncio.Queue) -> bool:
    """发送WebSocket消息（使用已建立的连接）"""
    try:
        uri = f"{WS_URL}/ws/documents/{doc_id}?token={tokens[user_key]}&username={USERS[user_key]['username']}"
        async with websockets.connect(uri) as websocket:
            # 等待初始化
            init_received = False
            init_timeout = 5.0
            start_time = time.time()
            
            while not init_received and (time.time() - start_time) < init_timeout:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    if data.get("type") == "init":
                        init_received = True
                        log(f"✅ 用户 {USERS[user_key]['username']} WebSocket 初始化完成")
                        # 将init消息也放入队列
                        await message_queue.put({"user": user_key, "message": data})
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    log(f"⚠️  等待初始化时出错: {e}", "WARNING")
                    break
            
            if not init_received:
                log(f"⚠️  用户 {USERS[user_key]['username']} WebSocket 初始化超时", "WARNING")
            
            # 发送内容更新
            message = {
                "type": "content_update",
                "payload": {"html": content}
            }
            await websocket.send(json.dumps(message))
            log(f"📤 用户 {USERS[user_key]['username']} 发送内容更新: {content[:50]}...")
            
            # 等待一小段时间确保消息发送和接收
            await asyncio.sleep(1.0)
            return True
    except Exception as e:
        log(f"❌ 用户 {USERS[user_key]['username']} WebSocket 发送消息异常: {e}", "ERROR")
        return False

async def test_multi_user_collaboration(doc_id: int) -> bool:
    """测试多用户协作"""
    log("🚀 开始多用户协作测试")
    
    # 消息队列
    message_queues = {
        "user_a": asyncio.Queue(),
        "user_b": asyncio.Queue(),
        "user_c": asyncio.Queue()
    }
    
    # 启动WebSocket连接任务
    connection_tasks = []
    for user_key in ["user_a", "user_b", "user_c"]:
        task = asyncio.create_task(websocket_connect(user_key, doc_id, message_queues[user_key]))
        connection_tasks.append(task)
    
    # 等待连接建立
    await asyncio.sleep(2)
    
    # 测试1: A 发送内容更新
    log("📝 测试1: A 发送内容更新")
    content_a = "<p>A用户编辑的内容</p>"
    await websocket_send("user_a", doc_id, content_a, message_queues["user_a"])
    await asyncio.sleep(2)  # 增加等待时间确保消息传播
    
    # 检查B和C是否收到（从队列中读取）
    b_received_a = False
    c_received_a = False
    
    # 处理B的消息队列
    b_messages = []
    while not message_queues["user_b"].empty():
        b_messages.append(await message_queues["user_b"].get())
    
    for msg in b_messages:
        msg_data = msg["message"]
        if msg_data.get("type") == "content_update":
            payload_html = msg_data.get("payload", {}).get("html", "")
            if payload_html == content_a:
                b_received_a = True
                log("✅ B 收到 A 的内容更新")
    
    # 处理C的消息队列
    c_messages = []
    while not message_queues["user_c"].empty():
        c_messages.append(await message_queues["user_c"].get())
    
    for msg in c_messages:
        msg_data = msg["message"]
        if msg_data.get("type") == "content_update":
            payload_html = msg_data.get("payload", {}).get("html", "")
            if payload_html == content_a:
                c_received_a = True
                log("✅ C 收到 A 的内容更新")
    
    # 测试2: B 发送内容更新
    log("📝 测试2: B 发送内容更新")
    content_b = "<p>B用户编辑的内容</p>"
    await websocket_send("user_b", doc_id, content_b, message_queues["user_b"])
    await asyncio.sleep(2)
    
    # 检查A和C是否收到
    a_received_b = False
    c_received_b = False
    
    # 处理A的消息队列
    a_messages = []
    while not message_queues["user_a"].empty():
        a_messages.append(await message_queues["user_a"].get())
    
    for msg in a_messages:
        msg_data = msg["message"]
        if msg_data.get("type") == "content_update":
            payload_html = msg_data.get("payload", {}).get("html", "")
            if payload_html == content_b:
                a_received_b = True
                log("✅ A 收到 B 的内容更新")
    
    # 处理C的消息队列（继续读取）
    while not message_queues["user_c"].empty():
        c_messages.append(await message_queues["user_c"].get())
    
    for msg in c_messages:
        msg_data = msg["message"]
        if msg_data.get("type") == "content_update":
            payload_html = msg_data.get("payload", {}).get("html", "")
            if payload_html == content_b:
                c_received_b = True
                log("✅ C 收到 B 的内容更新")
    
    # 测试3: C（viewer）发送内容更新，应该被拒绝
    log("📝 测试3: C（viewer）发送内容更新，应该被拒绝")
    content_c = "<p>C用户尝试编辑的内容</p>"
    await websocket_send("user_c", doc_id, content_c, message_queues["user_c"])
    await asyncio.sleep(2)
    
    # 检查C是否收到错误消息
    c_received_error = False
    
    # 处理C的消息队列（继续读取）
    while not message_queues["user_c"].empty():
        c_messages.append(await message_queues["user_c"].get())
    
    for msg in c_messages:
        msg_data = msg["message"]
        if msg_data.get("type") == "error":
            error_msg = msg_data.get("payload", {}).get("message", "unknown")
            if "无编辑权限" in error_msg or "无权限" in error_msg:
                c_received_error = True
                log(f"✅ C 收到权限错误消息: {error_msg}")
    
    # 关闭连接任务
    for task in connection_tasks:
        task.cancel()
    
    # 验证结果
    success = True
    if not b_received_a:
        log("❌ B 未收到 A 的内容更新", "ERROR")
        success = False
    if not c_received_a:
        log("❌ C 未收到 A 的内容更新", "ERROR")
        success = False
    if not a_received_b:
        log("❌ A 未收到 B 的内容更新", "ERROR")
        success = False
    if not c_received_b:
        log("❌ C 未收到 B 的内容更新", "ERROR")
        success = False
    if not c_received_error:
        log("❌ C 未收到权限错误消息", "ERROR")
        success = False
    
    return success

def verify_document_content(user_key: str, doc_id: int, expected_content: str) -> bool:
    """验证文档内容"""
    doc = get_document(user_key, doc_id)
    if doc and doc.get("content") == expected_content:
        log(f"✅ 文档内容验证成功: {expected_content}")
        return True
    else:
        log(f"❌ 文档内容验证失败，期望: {expected_content}，实际: {doc.get('content', 'none')}", "ERROR")
        return False

async def main():
    """主测试函数"""
    log("🎯 开始多用户共享与协作编辑测试")
    
    # 1. 注册/登录用户
    log("\n📝 步骤1: 注册/登录用户")
    for user_key in ["user_a", "user_b", "user_c"]:
        if not register_user(user_key):
            log(f"❌ 测试终止：用户注册失败", "ERROR")
            return False
        if not login_user(user_key):
            log(f"❌ 测试终止：用户登录失败", "ERROR")
            return False
    
    # 2. A 创建文档
    log("\n📝 步骤2: A 创建文档")
    doc = create_document("user_a")
    if not doc:
        log("❌ 测试终止：文档创建失败", "ERROR")
        return False
    doc_id = doc["id"]
    
    # 3. A 批量共享文档给 B/C
    log("\n📝 步骤3: A 批量共享文档给 B/C")
    collaborators = [
        {"username": USERS["user_b"]["username"], "role": "editor"},
        {"username": USERS["user_c"]["username"], "role": "viewer"}
    ]
    if not batch_add_collaborators("user_a", doc_id, collaborators):
        log("❌ 测试终止：批量共享失败", "ERROR")
        return False
    
    # 4. B/C 获取文档详情
    log("\n📝 步骤4: B/C 获取文档详情")
    for user_key in ["user_b", "user_c"]:
        doc_check = get_document(user_key, doc_id)
        if not doc_check:
            log(f"❌ 测试终止：{USERS[user_key]['username']} 无法获取文档", "ERROR")
            return False
    
    # 5. 多用户协作测试
    log("\n📝 步骤5: 多用户协作测试")
    collab_success = await test_multi_user_collaboration(doc_id)
    if not collab_success:
        log("❌ 测试终止：多用户协作测试失败", "ERROR")
        return False
    
    # 6. 验证文档内容
    log("\n📝 步骤6: 验证文档内容")
    # 最后一次更新应该是B的内容
    expected_content = "<p>B用户编辑的内容</p>"
    content_success = verify_document_content("user_a", doc_id, expected_content)
    if not content_success:
        log("❌ 测试终止：文档内容验证失败", "ERROR")
        return False
    
    # 测试完成
    log("\n🎉 多用户共享与协作编辑测试全部通过！")
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        log(f"\n💥 测试执行异常: {e}", "ERROR")
        sys.exit(1)
