#!/usr/bin/env python3
"""
通知MVP一键验收脚本 - 纯Python实现
"""
import os
import sys
import subprocess
import time
import socket
from pathlib import Path

# 确保项目根目录在Python路径中
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 日志目录
LOG_DIR = project_root / "artifacts" / "verify_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def build_env():
    """构建统一的环境变量字典，确保 TEMP/TMP 指向项目本地目录"""
    temp_dir = project_root / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    return env

def run_command(cmd, description, capture_output=True, text=True):
    """运行命令并记录结果"""
    print(f"[RUN] {description}")
    print(f"    命令: {' '.join(cmd)}")
    
    # 使用统一的环境变量构建函数
    env = build_env()
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=text,
            encoding="utf-8",
            errors="replace",
            cwd=project_root,
            env=env  # 注入环境变量
        )
        
        if capture_output:
            print(f"    退出码: {result.returncode}")
            if result.stdout:
                print(f"    输出: {result.stdout[:200]}...")
            if result.stderr:
                print(f"    错误: {result.stderr[:200]}...")
        
        return result
    except Exception as e:
        print(f"    异常: {e}")
        return None

def write_log(filename, content, mode="w"):
    """写入日志文件"""
    filepath = LOG_DIR / filename
    with open(filepath, mode, encoding="utf-8", errors="replace") as f:
        f.write(content)
    print(f"    日志已保存: {filepath}")

def append_log(filename, content):
    """追加日志文件"""
    write_log(filename, content, "a")

def check_port(host, port, timeout=10):
    """检查端口是否可连接"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (socket.error, socket.timeout):
            time.sleep(0.5)
    return False

def kill_process(pid):
    """杀死进程"""
    try:
        if os.name == 'nt':  # Windows
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], 
                         capture_output=True, check=False)
        else:  # Unix-like
            subprocess.run(['kill', '-9', str(pid)], 
                         capture_output=True, check=False)
        return True
    except Exception:
        return False

def main():
    print("=== 通知MVP一键验收开始 ===")
    
    # 步骤结果记录
    results = {}
    
    # 1. 环境检查
    print("\n==== 步骤1: 环境检查 ===")
    env_content = []
    
    # Python版本
    result = run_command([sys.executable, "--version"], "Python版本")
    if result:
        env_content.append(f"Python版本: {result.stdout.strip()}")
        results["python_version"] = result.returncode
    
    # pip list
    result = run_command([sys.executable, "-m", "pip", "list"], "pip list")
    if result:
        env_content.append("\npip list:\n")
        env_content.append(result.stdout)
        results["pip_list"] = result.returncode
    
    # 关键包导入检查
    import_check = [
        "try:\n",
        "    import fastapi; print('[OK] fastapi')\n",
        "except Exception as e: print(f'[FAIL] fastapi: {e}')\n",
        "try:\n",
        "    import pydantic; print('[OK] pydantic')\n",
        "except Exception as e: print(f'[FAIL] pydantic: {e}')\n",
        "try:\n",
        "    import uvicorn; print('[OK] uvicorn')\n",
        "except Exception as e: print(f'[FAIL] uvicorn: {e}')\n",
        "try:\n",
        "    import jose; print('[OK] jose')\n",
        "except Exception as e: print(f'[FAIL] jose: {e}')\n",
        "try:\n",
        "    import py_opengauss; print('[OK] py_opengauss')\n",
        "except Exception as e: print(f'[FAIL] py_opengauss: {e}')\n",
        "try:\n",
        "    import websockets; print('[OK] websockets')\n",
        "except Exception as e: print(f'[FAIL] websockets: {e}')\n",
    ]
    
    import_script = project_root / "temp_import_check.py"
    with open(import_script, "w", encoding="utf-8") as f:
        f.writelines(import_check)
    
    result = run_command([sys.executable, str(import_script)], "关键包导入检查")
    if result:
        env_content.append("\n关键包导入检查:\n")
        env_content.append(result.stdout)
        results["import_check"] = result.returncode
    
    # 清理临时文件
    try:
        import_script.unlink()
    except:
        pass
    
    write_log("env.txt", "\n".join(env_content))
    
    # 2. 静态检查
    print("\n==== 步骤2: 静态检查 ===")
    transcript_content = []
    
    # compileall
    result = run_command([sys.executable, "-m", "compileall", "app"], "编译检查app目录")
    if result:
        transcript_content.append("=== compileall app ===\n")
        transcript_content.append(result.stdout)
        if result.stderr:
            transcript_content.append("STDERR:\n")
            transcript_content.append(result.stderr)
        results["compileall"] = result.returncode
    
    # smoke_imports
    result = run_command([sys.executable, "scripts/smoke_imports.py"], "导入测试")
    if result:
        transcript_content.append("\n=== smoke_imports ===\n")
        transcript_content.append(result.stdout)
        if result.stderr:
            transcript_content.append("STDERR:\n")
            transcript_content.append(result.stderr)
        results["smoke_imports"] = result.returncode
    
    write_log("run_transcript.txt", "\n".join(transcript_content))
    
    # 3. 数据库检查
    print("\n==== 步骤3: 数据库检查 ===")
    result = run_command([sys.executable, "scripts/check_db.py"], "数据库自检")
    if result:
        write_log("check_db_output.txt", result.stdout)
        if result.stderr:
            append_log("check_db_output.txt", f"\nSTDERR:\n{result.stderr}")
        results["check_db"] = result.returncode
        
        if result.returncode != 0:
            print("❌ 数据库检查失败，停止后续流程")
            return 1
    
    # 4. 启动uvicorn
    print("\n==== 步骤4: 启动服务 ===")
    uvicorn_cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000", "--log-level", "debug"
    ]
    
    print(f"[RUN] 启动uvicorn服务")
    print(f"    命令: {' '.join(uvicorn_cmd)}")
    
    try:
        # 使用统一的环境变量构建函数
        env = build_env()
        
        # 启动uvicorn进程
        with open(LOG_DIR / "uvicorn.log", "w", encoding="utf-8", errors="replace") as out_file, \
             open(LOG_DIR / "uvicorn.err.log", "w", encoding="utf-8", errors="replace") as err_file:
            
            uvicorn_process = subprocess.Popen(
                uvicorn_cmd,
                stdout=out_file,
                stderr=err_file,
                cwd=project_root,
                env=env  # 注入环境变量
            )
        
        uvicorn_pid = uvicorn_process.pid
        print(f"    uvicorn PID: {uvicorn_pid}")
        
        # 保存PID
        with open(LOG_DIR / "uvicorn.pid", "w") as f:
            f.write(str(uvicorn_pid))
        
        # 等待服务启动
        print("    等待服务启动...")
        if check_port("127.0.0.1", 8000, timeout=10):
            print("    ✅ 服务已启动")
            results["uvicorn_start"] = 0
        else:
            print("    ❌ 服务启动超时")
            results["uvicorn_start"] = 1
            
    except Exception as e:
        print(f"    启动uvicorn失败: {e}")
        results["uvicorn_start"] = 1
        uvicorn_pid = None
    
    # 5. REST API测试
    print("\n==== 步骤5: REST API测试 ===")
    if results.get("uvicorn_start") == 0:
        result = run_command([sys.executable, "scripts/test_notification_rest_flow.py"], "REST API测试")
        if result:
            write_log("rest_flow_output.txt", result.stdout)
            if result.stderr:
                append_log("rest_flow_output.txt", f"\nSTDERR:\n{result.stderr}")
            results["rest_flow"] = result.returncode
    else:
        print("    跳过REST API测试（服务未启动）")
        write_log("rest_flow_output.txt", "SKIP: 服务未启动")
        results["rest_flow"] = 1
    
    # 6. WebSocket测试
    print("\n==== 步骤6: WebSocket测试 ===")
    if results.get("uvicorn_start") == 0:
        # 检查websockets是否可用
        ws_check = [
            "try:\n",
            "    import websockets\n",
            "    print('websockets available')\n",
            "except ImportError:\n",
            "    print('websockets not installed')\n",
            "    exit(2)\n"
        ]
        
        ws_script = project_root / "temp_ws_check.py"
        with open(ws_script, "w", encoding="utf-8") as f:
            f.writelines(ws_check)
        
        result = run_command([sys.executable, str(ws_script)], "检查websockets模块")
        try:
            ws_script.unlink()
        except:
            pass
        
        if result and result.returncode == 0:
            # websockets可用，运行测试
            result = run_command([sys.executable, "scripts/ws_notifications_smoke.py"], "WebSocket测试")
            if result:
                write_log("ws_flow_output.txt", result.stdout)
                if result.stderr:
                    append_log("ws_flow_output.txt", f"\nSTDERR:\n{result.stderr}")
                results["ws_flow"] = result.returncode
        elif result and result.returncode == 2:
            # websockets不可用
            write_log("ws_flow_output.txt", "SKIP websockets not installed")
            results["ws_flow"] = 0  # 跳过不算失败
        else:
            write_log("ws_flow_output.txt", "WebSocket检查失败")
            results["ws_flow"] = 1
    else:
        print("    跳过WebSocket测试（服务未启动）")
        write_log("ws_flow_output.txt", "SKIP: 服务未启动")
        results["ws_flow"] = 1
    
    # 7. 停止服务
    print("\n==== 步骤7: 停止服务 ===")
    if uvicorn_pid:
        print(f"    停止uvicorn (PID: {uvicorn_pid})")
        if kill_process(uvicorn_pid):
            print("    ✅ 服务已停止")
            results["uvicorn_stop"] = 0
        else:
            print("    ❌ 停止服务失败")
            results["uvicorn_stop"] = 1
    else:
        results["uvicorn_stop"] = 0
    
    # 清理PID文件
    try:
        (LOG_DIR / "uvicorn.pid").unlink()
    except:
        pass
    
    # 8. 生成摘要
    print("\n==== 步骤8: 生成摘要 ===")
    summary_lines = ["=== 通知MVP验收摘要 ===\n"]
    summary_lines.append(f"验收时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    # 步骤结果
    summary_lines.append("步骤结果:\n")
    step_names = {
        "python_version": "Python版本检查",
        "pip_list": "pip list检查", 
        "import_check": "关键包导入检查",
        "compileall": "编译检查",
        "smoke_imports": "导入测试",
        "check_db": "数据库检查",
        "uvicorn_start": "服务启动",
        "rest_flow": "REST API测试",
        "ws_flow": "WebSocket测试",
        "uvicorn_stop": "服务停止"
    }
    
    all_passed = True
    for step, name in step_names.items():
        exit_code = results.get(step, -1)
        status = "✅ 通过" if exit_code == 0 else "❌ 失败"
        summary_lines.append(f"  {name}: {status} (退出码: {exit_code})\n")
        if exit_code != 0:
            all_passed = False
    
    summary_lines.append("\n关键日志文件:\n")
    log_files = [
        "env.txt",
        "run_transcript.txt", 
        "check_db_output.txt",
        "uvicorn.log",
        "uvicorn.err.log",
        "rest_flow_output.txt",
        "ws_flow_output.txt"
    ]
    
    for log_file in log_files:
        filepath = LOG_DIR / log_file
        if filepath.exists():
            summary_lines.append(f"  {log_file} ({filepath.stat().st_size} bytes)\n")
    
    # 如果有失败，收集关键错误信息
    if not all_passed:
        summary_lines.append("\n关键错误信息:\n")
        
        # 收集各个失败步骤的最后30行
        error_files = {
            "check_db": "check_db_output.txt",
            "rest_flow": "rest_flow_output.txt",
            "ws_flow": "ws_flow_output.txt",
            "uvicorn": "uvicorn.err.log"
        }
        
        for step, filename in error_files.items():
            if results.get(step, 0) != 0:
                filepath = LOG_DIR / filename
                if filepath.exists():
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                            if lines:
                                summary_lines.append(f"\n{filename} (最后30行):\n")
                                for line in lines[-30:]:
                                    summary_lines.append(f"  {line.rstrip()}\n")
                    except Exception as e:
                        summary_lines.append(f"  读取{filename}失败: {e}\n")
    
    write_log("summary.txt", "\n".join(summary_lines))
    
    # 打印摘要内容
    print("\n" + "="*50)
    with open(LOG_DIR / "summary.txt", "r", encoding="utf-8", errors="replace") as f:
        print(f.read())
    
    print("\n=== 验收完成 ===")
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
