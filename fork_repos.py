#!/usr/bin/env python3
"""
将 opendoccn 组织的所有仓库 fork 到 opendoccn-archive 组织
使用 GitHub REST API
"""

import json
import requests
import time
import sys
import os
from BookerDownloadTool.util import request_retry

# ============ 配置区域 ============
SOURCE_ORG = "opendoccn"           # 源组织
TARGET_ORG = "opendoccn-archive"   # 目标组织
GITHUB_TOKEN = os.environ.get('GHP_TOKEN', '')  # 替换为你的 Personal Access Token
# =================================

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

API_BASE = "https://api.github.com"


def get_all_repos(org):
    """获取指定组织的所有仓库（支持分页）"""
    repos = []
    page = 1
    per_page = 100

    while True:
        url = f"{API_BASE}/orgs/{org}/repos"
        params = {"page": page, "per_page": per_page, "type": "all"}
        response = request_retry('GET', url, headers=HEADERS, params=params)

        if response.status_code != 200:
            break

        data = response.json()
        if not data:
            break

        repos.extend(data)
        page += 1

    return repos


def check_fork_exists(target_org, repo_name):
    """检查目标组织中是否已存在同名 fork"""
    url = f"{API_BASE}/repos/{target_org}/{repo_name}"
    response = request_retry('GET', url, headers=HEADERS)
    return response.status_code == 200


def fork_repo(source_org, repo_name, target_org):
    """将仓库 fork 到目标组织"""
    url = f"{API_BASE}/repos/{source_org}/{repo_name}/forks"
    data = {"organization": target_org}

    r = request_retry('POST', url, headers=HEADERS, json=data)

    if 200 <= r.status_code < 300:
        return {'code': 0, 'msg': ''}
    else:
        return {'code': r.status_code, 'msg': r.json().get('message', '')}


def main():
    print(f"🚀 开始将 {SOURCE_ORG} 的所有仓库 fork 到 {TARGET_ORG}")
    print("=" * 60)

    # 1. 获取源组织所有仓库
    print(f"\n📂 获取 {SOURCE_ORG} 的仓库列表...")
    repos_fname = SOURCE_ORG + '_repos.json'
    if os.path.isfile(repos_fname):
        repos = json.loads(open(repos_fname, encoding='utf8').read())
    else:
        repos = get_all_repos(SOURCE_ORG)
        open(repos_fname, 'w', encoding='utf8').write(json.dumps(repos))

    if not repos:
        print("❌ 未获取到任何仓库，请检查组织名称和 Token 权限")
        sys.exit(1)

    print(f"\n📊 共找到 {len(repos)} 个仓库")

    # 2. 逐个 fork
    success_count = 0
    skip_count = 0
    fail_count = 0

    for idx, repo in enumerate(repos, 1):
        repo_name = repo["name"]
        print(f"\n[{idx}/{len(repos)}] 处理: {repo_name}")

        # 检查是否已存在
        if check_fork_exists(TARGET_ORG, repo_name):
            print(f"⏭️ 目标组织中已存在 {repo_name}，跳过")
            skip_count += 1
            continue

        # 执行 fork
        r = fork_repo(SOURCE_ORG, repo_name, TARGET_ORG)
        if r['code'] == 0:
            print(f"✅ 成功发起 fork: {SOURCE_ORG}/{repo_name} → {TARGET_ORG}/{repo_name}")
            success_count += 1
        else:
            print(f"❌ Fork 失败 {repo_name}: {r['code']} - {r['msg']}")
            fail_count += 1

        # 避免触发 GitHub API 限流，每次 fork 后等待一下[reference:1]
        # 如果仓库数量较少，可以适当减少或增加等待时间
        if idx < len(repos):
            time.sleep(2)

    # 3. 输出统计
    print("\n" + "=" * 60)
    print("📊 执行完成！")
    print(f"   ✅ 成功 fork: {success_count}")
    print(f"   ⏭️ 已存在跳过: {skip_count}")
    print(f"   ❌ 失败: {fail_count}")


if __name__ == "__main__":
    main()