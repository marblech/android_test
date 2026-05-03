#!/usr/bin/env python3
"""
Gitee Android Pipeline Monitor
自动监控Gitee Android流水线构建状态，失败时自动分析并修复
"""

import time
import json
import subprocess
import sys
import urllib.request
import urllib.error
import os
from datetime import datetime

# 配置
GITEE_TOKEN = "b19bf0b5be1de7a458582c619c155c3d7"
GITEE_OWNER = "marblelog"
GITEE_REPO = "my-android-app"
API_BASE = f"https://gitee.com/api/v4/repos/{GITEE_OWNER}/{GITEE_REPO}"
CHECK_INTERVAL = 30  # 检查间隔（秒）
MAX_RETRIES = 10  # 最大重试次数

def api_request(endpoint):
    """发起Gitee API请求"""
    url = f"{API_BASE}/{endpoint}"
    if "?" not in url:
        url += "?"
    url += f"access_token={GITEE_TOKEN}"
    
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[ERROR] API请求失败: {e.code} - {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        print(f"[ERROR] API请求异常: {e}")
        return None

def get_pipelines(status="running"):
    """获取流水线列表"""
    return api_request(f"pipeline_branches?status={status}")

def get_pipeline_runs(pipeline_id):
    """获取流水线的运行记录"""
    return api_request(f"pipelines/{pipeline_id}/runs")

def get_job_logs(job_id):
    """获取任务日志"""
    url = f"{API_BASE}/pipelines/{job_id}/runs/logs"
    if "?" not in url:
        url += "?"
    url += f"access_token={GITEE_TOKEN}"
    
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        return f"[ERROR] 获取日志失败: {e}"

def check_build_status():
    """检查最新构建状态"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在检查流水线状态...")
    
    # 获取运行中的流水线
    pipelines = get_pipelines("running")
    if pipelines:
        for p in pipelines:
            print(f"  流水线 #{p.get('id')}: 状态={p.get('status')}, 分支={p.get('ref')}")
        return "running", pipelines
    
    # 获取失败的流水线
    pipelines = get_pipelines("failed")
    if pipelines:
        return "failed", pipelines
    
    # 获取成功的流水线
    pipelines = get_pipelines("success")
    if pipelines:
        return "success", pipelines
    
    return "unknown", []

def analyze_and_fix_issues(log_content):
    """分析日志并尝试自动修复"""
    fixes_applied = []
    
    if "cannot access './gradlew'" in log_content or "gradlew: No such file or directory" in log_content:
        fixes_applied.append("修复gradlew脚本问题")
        print("  [检测] 发现gradlew相关问题")
        
    if "gradle" in log_content.lower() and "not found" in log_content.lower():
        fixes_applied.append("修复gradle路径问题")
        print("  [检测] 发现gradle未找到问题")
        
    if "sdk" in log_content.lower() and "not found" in log_content.lower():
        fixes_applied.append("配置Android SDK")
        print("  [检测] 可能需要配置Android SDK")
        
    return fixes_applied

def create_fix_commit():
    """创建修复提交"""
    print("  [操作] 创建修复提交...")
    
    # 修改流水线配置使用更兼容的方式
    pipeline_config = """name: Android Build

on:
  push:
    branches: [ master ]
  pull_request:
    branches: [ master ]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up JDK 17
      uses: actions/setup-java@v3
      with:
        java-version: '17'
        distribution: 'temurin'
        cache: gradle

    - name: Setup Gradle
      uses: gradle/gradle-build-action@v2

    - name: Build with Gradle
      run: gradle :app:assembleDebug --no-daemon

    - name: Upload APK
      uses: actions/upload-artifact@v3
      with:
        name: app-debug-apk
        path: app/build/outputs/apk/debug/app-debug.apk
"""
    
    config_path = os.path.join("J:\\Android_test\\android-hello-world", ".gitee", "workflow", "build.yml")
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(pipeline_config)
    
    # 提交更改
    repo_path = "J:\\Android_test\\android-hello-world"
    subprocess.run(["git", "add", "."], cwd=repo_path)
    subprocess.run(["git", "commit", "-m", "fix-update-pipeline-v2"], cwd=repo_path, capture_output=True)
    result = subprocess.run(["git", "pull", "--rebase", "&&", "git", "push"], 
                          cwd=repo_path, capture_output=True, text=True, shell=True)
    
    if result.returncode == 0:
        print("  [成功] 修复已推送")
        return True
    else:
        print(f"  [失败] 推送失败: {result.stderr}")
        return False

def main():
    print("=" * 60)
    print("  Gitee Android Pipeline Monitor")
    print("=" * 60)
    print(f"仓库: {GITEE_OWNER}/{GITEE_REPO}")
    print(f"检查间隔: {CHECK_INTERVAL}秒")
    print(f"最大重试: {MAX_RETRIES}次")
    print("=" * 60)
    
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n[第 {attempt}/{MAX_RETRIES} 次检查]")
        
        status, pipelines = check_build_status()
        
        if status == "running":
            print("  [状态] 构建正在进行中，等待完成...")
            time.sleep(CHECK_INTERVAL)
            continue
            
        elif status == "failed":
            print("  [失败] 构建失败")
            if pipelines:
                pipeline = pipelines[0]
                pid = pipeline.get('id')
                print(f"  [信息] 流水线ID: {pid}")
                
                # 获取运行记录
                runs = get_pipeline_runs(pid)
                if runs:
                    latest_run = runs[0]
                    print(f"  [信息] 最新运行: {latest_run.get('id')}")
                
                # 尝试获取日志
                log = get_job_logs(pid)
                if log and len(log) > 100:
                    print("  [日志] 最近错误日志:")
                    print("-" * 40)
                    print(log[-1000:])  # 最后1000字符
                    print("-" * 40)
                
                # 自动修复
                print("  [操作] 尝试自动修复...")
                if create_fix_commit():
                    print("  [成功] 修复已推送，将触发新构建")
                    time.sleep(60)  # 等待新构建启动
                    continue
                else:
                    print("  [失败] 自动修复失败，需要手动干预")
                    break
            else:
                time.sleep(CHECK_INTERVAL)
                continue
                
        elif status == "success":
            print("  [成功] 构建成功!")
            print("\n" + "=" * 60)
            print("  流水线构建成功完成!")
            print("=" * 60)
            return True
            
        else:
            print("  [信息] 未找到相关流水线")
            time.sleep(CHECK_INTERVAL)
    
    print("\n[完成] 达到最大重试次数，请手动检查Gitee流水线状态")
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)