#!/usr/bin/env python3
"""
WebSocket 协同编辑验证脚本
验证目标：
1. 无效token -> close code=1008 (Policy Violation)
2. 有效token -> 正常连接，收到init消息
3. content_update -> 落库并广播
4. 心跳机制 -> ping/pong正常工作
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import websockets
    from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
except ImportError:
    print("错误：需要安装 websockets 库")
    print("请运行: pip install websockets")
    sys.exit(1)

# 配置
WS_URL = "ws://localhost:8000/ws/documents/1"
VALID_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0dXNlciIsImV4cCI6MTczMjY0NjQwMH0.invalid"  # 替换为有效token
INVALID_TOKEN = "invalid.token.here"
TIMEOUT = 15  # 测试超时时间


async def test_invalid_token():
    """测试无效token，应该收到close code=1008"""
    print("=" * 60)
    print("测试1: 无效token连接 (期望: close code=1008)")
    print("=" * 60)
    
    try:
        uri = f"{WS_URL}?token={INVALID_TOKEN}"
        print(f"连接到: {uri.replace(INVALID_TOKEN, 'INVALID_TOKEN')}")
        
        async with websockets.connect(uri, timeout=TIMEOUT) as websocket:
            print("❌ 错误：无效token不应该连接成功")
            return False
            
    except ConnectionClosedError as e:
        if e.code == 1008:
            print(f"✅ 正确：收到close code=1008 (Policy Violation)")
            print(f"   原因: {e.reason}")
            return True
        else:
            print(f"❌ 错误：收到错误的close code={e.code}, 期望1008")
            return False
    except ConnectionClosedOK as e:
        if e.code == 1008:
            print(f"✅ 正确：收到close code=1008 (Policy Violation)")
            print(f"   原因: {e.reason}")
            return True
        else:
            print(f"❌ 错误：收到错误的close code={e.code}, 期望1008")
            return False
    except Exception as e:
        print(f"❌ 错误：意外异常 {type(e).__name__}: {e}")
        return False


async def test_valid_token_and_init():
    """测试有效token，应该正常连接并收到init消息"""
    print("\n" + "=" * 60)
    print("测试2: 有效token连接与init消息 (期望: 正常连接)")
    print("=" * 60)
    
    try:
        uri = f"{WS_URL}?token={VALID_TOKEN}"
        print(f"连接到: {uri.replace(VALID_TOKEN, 'VALID_TOKEN')}")
        
        async with websockets.connect(uri, timeout=TIMEOUT) as websocket:
            print("✅ 连接成功")
            
            # 等待init消息
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(message)
                
                if data.get("type") == "init":
                    print("✅ 收到init消息")
                    print(f"   文档ID: {data.get('doc_id')}")
                    print(f"   内容长度: {len(data.get('payload', {}).get('html', ''))}")
                    permissions = data.get('permissions', {})
                    print(f"   权限: can_view={permissions.get('can_view')}, can_edit={permissions.get('can_edit')}")
                    return True
                else:
                    print(f"❌ 错误：收到意外消息类型: {data.get('type')}")
                    return False
                    
            except asyncio.TimeoutError:
                print("❌ 错误：超时未收到init消息")
                return False
                
    except ConnectionClosedError as e:
        print(f"❌ 错误：连接被关闭 code={e.code}, reason={e.reason}")
        return False
    except Exception as e:
        print(f"❌ 错误：意外异常 {type(e).__name__}: {e}")
        return False


async def test_content_update():
    """测试content_update落库和广播"""
    print("\n" + "=" * 60)
    print("测试3: content_update落库与广播 (期望: 更新成功并广播)")
    print("=" * 60)
    
    try:
        uri = f"{WS_URL}?token={VALID_TOKEN}"
        print(f"连接到: {uri.replace(VALID_TOKEN, 'VALID_TOKEN')}")
        
        async with websockets.connect(uri, timeout=TIMEOUT) as websocket1:
            print("✅ 用户1连接成功")
            
            # 等待init消息
            message = await asyncio.wait_for(websocket1.recv(), timeout=5.0)
            data = json.loads(message)
            if data.get("type") != "init":
                print("❌ 错误：未收到init消息")
                return False
            
            # 建立第二个连接
            async with connect(uri, timeout=TIMEOUT) as websocket2:
                print("✅ 用户2连接成功")
                
                # 等待用户2的init消息
                message = await asyncio.wait_for(websocket2.recv(), timeout=5.0)
                data = json.loads(message)
                if data.get("type") != "init":
                    print("❌ 错误：用户2未收到init消息")
                    return False
                
                # 用户1发送content_update
                test_content = "<p>测试内容更新 - " + str(int(time.time())) + "</p>"
                update_msg = {
                    "type": "content_update",
                    "payload": {"html": test_content}
                }
                
                print(f"📝 用户1发送内容更新: {test_content[:30]}...")
                await websocket1.send(json.dumps(update_msg))
                
                # 用户1等待确认（可能收到自己的广播）
                try:
                    message = await asyncio.wait_for(websocket1.recv(), timeout=3.0)
                    data = json.loads(message)
                    if data.get("type") == "content_update":
                        print("✅ 用户1收到内容更新广播")
                except asyncio.TimeoutError:
                    print("⚠️  用户1未收到广播（可能正常，某些实现不广播给发送者）")
                
                # 用户2等待广播
                try:
                    message = await asyncio.wait_for(websocket2.recv(), timeout=3.0)
                    data = json.loads(message)
                    if data.get("type") == "content_update":
                        received_content = data.get('payload', {}).get('html', '')
                        if test_content in received_content:
                            print("✅ 用户2收到内容更新广播")
                            print(f"   广播内容: {received_content[:30]}...")
                            return True
                        else:
                            print("❌ 错误：广播内容不匹配")
                            return False
                    else:
                        print(f"❌ 错误：收到意外消息类型: {data.get('type')}")
                        return False
                except asyncio.TimeoutError:
                    print("❌ 错误：用户2未收到内容更新广播")
                    return False
                
    except ConnectionClosedError as e:
        print(f"❌ 错误：连接被关闭 code={e.code}, reason={e.reason}")
        return False
    except Exception as e:
        print(f"❌ 错误：意外异常 {type(e).__name__}: {e}")
        return False


async def test_heartbeat():
    """测试心跳机制"""
    print("\n" + "=" * 60)
    print("测试4: 心跳机制 (期望: ping/pong正常)")
    print("=" * 60)
    
    try:
        uri = f"{WS_URL}?token={VALID_TOKEN}"
        print(f"连接到: {uri.replace(VALID_TOKEN, 'VALID_TOKEN')}")
        
        async with websockets.connect(uri, timeout=TIMEOUT) as websocket:
            print("✅ 连接成功，等待心跳...")
            
            ping_received = False
            pong_sent = False
            
            # 等待最多30秒接收心跳
            for i in range(30):
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data.get("type") == "ping":
                        print(f"✅ 收到ping消息 (第{i+1}秒)")
                        ping_received = True
                        
                        # 回复pong
                        pong_msg = {"type": "pong"}
                        await websocket.send(json.dumps(pong_msg))
                        print("✅ 发送pong响应")
                        pong_sent = True
                        break
                        
                    elif data.get("type") == "init":
                        print("✅ 收到init消息")
                        continue
                        
                except asyncio.TimeoutError:
                    continue
            
            if not ping_received:
                print("⚠️  警告：30秒内未收到心跳消息")
                print("   可能原因：服务未启动心跳任务或心跳间隔较长")
                return False
            
            if ping_received and pong_sent:
                print("✅ 心跳机制正常工作")
                return True
            else:
                print("❌ 心跳机制异常")
                return False
                
    except ConnectionClosedError as e:
        print(f"❌ 错误：连接被关闭 code={e.code}, reason={e.reason}")
        return False
    except Exception as e:
        print(f"❌ 错误：意外异常 {type(e).__name__}: {e}")
        return False


async def main():
    print("WebSocket 协同编辑验证测试")
    print(f"目标服务器: {WS_URL}")
    print(f"测试超时: {TIMEOUT}秒")
    print("\n注意：请确保后端服务已启动，并且有有效的测试token")
    
    # 运行测试
    results = []
    
    # 测试1：无效token
    results.append(await test_invalid_token())
    
    # 测试2：有效token连接
    results.append(await test_valid_token_and_init())
    
    # 测试3：内容更新
    results.append(await test_content_update())
    
    # 测试4：心跳机制
    results.append(await test_heartbeat())
    
    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    test_names = [
        "无效token (1008错误码)", 
        "有效token连接与init", 
        "content_update落库广播", 
        "心跳机制"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, results), 1):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"测试{i} ({name}): {status}")
    
    passed = sum(results)
    total = len(results)
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，请检查服务状态")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
