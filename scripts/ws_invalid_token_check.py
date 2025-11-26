#!/usr/bin/env python3
"""
WebSocket token 验证验收脚本

验证：
1. token 存在但无效：必须收到 close code 1008
2. token 缺失：允许连接（匿名 user_id=0），至少 2 秒不被 1008 关闭
"""
import asyncio
import sys
import websockets
from websockets.exceptions import ConnectionClosed


async def test_invalid_token():
    """测试无效 token 必须返回 1008"""
    print("测试 1: 无效 token 必须返回 1008...")
    invalid_token = "invalid_token_12345"
    uri = f"ws://localhost:8000/ws/documents/1?token={invalid_token}"
    
    try:
        async with websockets.connect(uri) as ws:
            # 连接可能成功，但应该很快收到 close
            try:
                # 等待接收消息或 close
                await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                # 如果 2 秒内没有收到 close，说明测试失败
                print("❌ 错误：无效 token 应该在 2 秒内收到 close，但没有收到")
                return False
            except ConnectionClosed as e:
                if e.code == 1008:
                    print(f"✅ 通过：无效 token 正确返回 close code 1008")
                    return True
                else:
                    print(f"❌ 错误：无效 token 返回了错误的 close code: {e.code} (期望 1008)")
                    return False
    except ConnectionClosed as e:
        if e.code == 1008:
            print(f"✅ 通过：无效 token 在握手时返回 close code 1008")
            return True
        else:
            print(f"❌ 错误：无效 token 返回了错误的 close code: {e.code} (期望 1008)")
            return False
    except Exception as e:
        print(f"❌ 错误：连接失败: {e}")
        return False


async def test_missing_token():
    """测试缺失 token 允许匿名连接"""
    print("\n测试 2: 缺失 token 允许匿名连接...")
    uri = "ws://localhost:8000/ws/documents/1"
    
    try:
        async with websockets.connect(uri) as ws:
            # 连接成功，等待至少 2 秒
            print("  连接成功，等待 2 秒验证连接保持...")
            await asyncio.sleep(2.0)
            
            # 尝试接收消息（可能是 init 消息）
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                print(f"  ✅ 收到消息: {message[:100]}...")
            except asyncio.TimeoutError:
                # 没有消息也可以，只要连接没被关闭
                print("  ✅ 连接保持（未收到消息但连接正常）")
            
            # 如果执行到这里，说明连接仍然打开（没有抛出 ConnectionClosed 异常）
            print("✅ 通过：缺失 token 允许匿名连接，至少 2 秒未被 1008 关闭")
            return True
                
    except ConnectionClosed as e:
        if e.code == 1008:
            print(f"❌ 错误：缺失 token 不应该被 1008 关闭，但收到了 close code 1008")
            return False
        else:
            print(f"❌ 错误：缺失 token 连接被关闭，code: {e.code}")
            return False
    except Exception as e:
        print(f"❌ 错误：连接失败: {e}")
        return False


async def main():
    """主函数"""
    print("=" * 60)
    print("WebSocket Token 验证验收测试")
    print("=" * 60)
    
    result1 = await test_invalid_token()
    result2 = await test_missing_token()
    
    print("\n" + "=" * 60)
    if result1 and result2:
        print("✅ 所有测试通过")
        sys.exit(0)
    else:
        print("❌ 测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

