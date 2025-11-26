"""
通知 WebSocket 冒烟脚本

验证点：
1) 无效 token 必须关闭 code=1008。
2) 缺失 token 允许连接（但不推送）。
3) 可选：填写有效 token 后验证可以收到握手 init 或保持连接。

运行方式： python scripts/notify_ws_smoke.py
"""
import asyncio
import os
import sys
from typing import Optional

import websockets
from websockets.exceptions import ConnectionClosed

BASE_WS_URL = os.getenv("NOTIFY_WS_URL", "ws://localhost:8000/api/v1/ws/notifications")


def print_step(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


async def expect_invalid_token():
    print_step("测试：无效 token 必须返回 1008")
    uri = f"{BASE_WS_URL}?token=invalid_token_123"
    try:
        async with websockets.connect(uri) as ws:
            try:
                await asyncio.wait_for(ws.recv(), timeout=2)
            except ConnectionClosed as e:
                if e.code == 1008:
                    print("✅ 无效 token 正确返回 1008")
                    return True
                print(f"❌ 错误的 close code: {e.code}")
                return False
            except asyncio.TimeoutError:
                print("❌ 无效 token 应在 2s 内关闭")
                return False
    except ConnectionClosed as e:
        if e.code == 1008:
            print("✅ 握手阶段直接关闭 1008")
            return True
        print(f"❌ 连接被关闭，code={e.code}")
        return False
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False


async def expect_missing_token():
    print_step("测试：缺失 token 允许连接")
    uri = BASE_WS_URL
    try:
        async with websockets.connect(uri) as ws:
            await asyncio.sleep(2)
            print("✅ 连接保持 2 秒未被 1008 关闭")
            return True
    except ConnectionClosed as e:
        print(f"❌ 连接被关闭 code={e.code}")
        return False
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False


async def optional_valid_token(token: Optional[str]):
    if not token:
        print_step("可选：填写有效 token 测试")
        print("未提供 token，跳过该测试。请先登录获取 JWT 后再尝试。")
        return True

    uri = f"{BASE_WS_URL}?token={token}"
    print_step("可选：有效 token 连接")
    try:
        async with websockets.connect(uri) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                print(f"✅ 收到消息: {msg[:100]}...")
            except asyncio.TimeoutError:
                print("⚠️ 未收到消息，但连接保持，视为通过")
            await ws.close()
            return True
    except ConnectionClosed as e:
        print(f"❌ 连接被关闭 code={e.code}")
        return False
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False


async def main():
    invalid_ok = await expect_invalid_token()
    missing_ok = await expect_missing_token()
    token = os.getenv("VALID_NOTIFY_TOKEN")
    valid_ok = await optional_valid_token(token)

    success = all([invalid_ok, missing_ok, valid_ok])
    print_step("结果")
    if success:
        print("✅ 所有检查完成")
        sys.exit(0)
    print("❌ 存在失败项")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
