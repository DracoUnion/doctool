import os
import requests
import time

# 配置
GITHUB_TOKEN = os.getenv("GH_TOKEN")  # 建议从环境变量读取

if not GITHUB_TOKEN:
    raise ValueError("请设置 GITHUB_TOKEN 环境变量")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}


def get_all_org_repos(org):
    """分页获取组织下所有仓库"""
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{org}/repos"
        params = {"per_page": 100, "page": page, "type": "all"}
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        repos.extend(data)
        page += 1
        time.sleep(0.1)  # 温和限速
    return repos


def sync_fork(owner, repo, branch):
    """调用 merge-upstream 同步 Fork"""
    url = f"https://api.github.com/repos/{owner}/{repo}/merge-upstream"
    payload = {"branch": branch}
    resp = requests.post(url, headers=HEADERS, json=payload)

    if resp.status_code == 200:
        result = resp.json()
        return True, result.get("merge_type", "synced")
    elif resp.status_code == 409:
        return False, "合并冲突，需手动处理"
    elif resp.status_code == 422:
        return False, f"无法同步: {resp.json().get('message')}"
    else:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"

def sync_fork_org(org_name):
    print(f"获取组织 {org_name} 的仓库列表...")
    repos = get_all_org_repos(org_name)
    forks = [r for r in repos if r.get("fork")]

    print(f"共 {len(repos)} 个仓库，其中 {len(forks)} 个是 Fork\n")

    if not forks:
        return

    for repo in forks:
        name = repo["name"]
        default_branch = repo.get("default_branch", "main")
        print(f"同步 {name} (分支: {default_branch}) ... ", end="")

        try:
            ok, msg = sync_fork(org_name, name, default_branch)
            if ok:
                print(f"✅ 成功 ({msg})")
            else:
                print(f"❌ 失败: {msg}")
        except Exception as e:
            print(f"❌ 异常: {e}")

        time.sleep(0.2)  # 避免触发速率限制

def main():
    sync_fork_org('OpenDocCN1')

if __name__ == "__main__":
    main()