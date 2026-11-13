#!/usr/bin/env python3
"""
将 GitHub 组织 A 的所有仓库，通过 GitLab 的 URL 导入 API 导入到 GitLab 组织 B。
使用端点: POST /api/v4/projects
关键参数: import_url
"""

import os
import sys
import time
import urllib.parse

import requests
from BookerDownloadTool.util import request_retry

# ---------- 配置：从环境变量读取 ----------
GH_TOKEN = os.environ.get("GH_TOKEN")
GL_TOKEN = os.environ.get("GL_TOKEN")
GITHUB_ORG = 'OpenDocCN'      # GitHub 组织 A 的 login 名
GITLAB_GROUP = 'OpenDocCN1'  # GitLab 组织 B 的路径 (full_path)
GITLAB_BASE_URL = os.environ.get("GL_BASE_URL", "https://gitlab.com").rstrip("/")

if not all([GH_TOKEN, GL_TOKEN, GITHUB_ORG, GITLAB_GROUP]):
    sys.exit("请设置环境变量: GH_TOKEN, GL_TOKEN, GH_ORG, GL_GROUP")

# ---------- 通用请求头 ----------
GH_HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
}
GL_HEADERS = {
    "PRIVATE-TOKEN": GL_TOKEN,
    "Content-Type": "application/json",
}


def list_github_repos(org: str) -> list[dict]:
    """分页获取 GitHub 组织下的所有仓库，返回 id、name、clone_url 等字段。"""
    repos = []
    page = 1
    per_page = 100
    while True:
        url = f"https://api.github.com/orgs/{org}/repos"
        params = {"type": "all", "per_page": per_page, "page": page}
        resp = request_retry('GET', url, headers=GH_HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        repos.extend(batch)
        print(f"  已获取 GitHub 仓库: 第 {page} 页, 本页 {len(batch)} 个")
        if len(batch) < per_page:
            break
        page += 1
    return repos


def get_gitlab_group_id(group_path: str) -> int:
    """通过 full_path 查询 GitLab 群组 ID，用于创建项目时指定命名空间。"""
    encoded = urllib.parse.quote(group_path, safe="")
    url = f"{GITLAB_BASE_URL}/api/v4/groups/{encoded}"
    resp = request_retry('GET', url, headers=GL_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]


def list_gitlab_repo_paths(group_id: int) -> set:
    """
    分页获取指定 GitLab 群组下已存在的项目，返回小写化的 path 集合，
    用于与 GitHub 仓库名做大小写不敏感的比对。
    """
    paths = set()
    page = 1
    per_page = 100
    while True:
        url = f"{GITLAB_BASE_URL}/api/v4/groups/{group_id}/projects"
        params = {"per_page": per_page, "page": page, "include_subgroups": False}
        resp = request_retry('GET', url, headers=GL_HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        paths.update(p["path"].lower() for p in batch)
        print(f"  已获取 GitLab 仓库: 第 {page} 页, 本页 {len(batch)} 个, 累计 {len(paths)} 个")
        if len(batch) < per_page:
            break
        page += 1
    return paths


def build_auth_import_url(clone_url: str, gh_token: str) -> str:
    """
    为 GitHub 克隆 URL 嵌入认证信息，以便 GitLab 拉取私有仓库。
    将 https://github.com/org/repo.git 转换为
    https://oauth2:<TOKEN>@github.com/org/repo.git
    """
    if clone_url.startswith("https://"):
        return clone_url.replace("https://", f"https://oauth2:{gh_token}@")
    elif clone_url.startswith("http://"):
        return clone_url.replace("http://", f"http://oauth2:{gh_token}@")
    return clone_url  # 对于 ssh 等其他协议，暂不处理


def import_repo_by_url(repo: dict, namespace_id: int) -> bool:
    """
    使用 Projects API 的 import_url 参数导入单个仓库。
    """
    url = f"{GITLAB_BASE_URL}/api/v4/projects"

    # 为私有仓库构建带认证的导入 URL
    import_url = build_auth_import_url(repo["clone_url"], GH_TOKEN)

    payload = {
        "name": repo["name"],
        "path": repo["name"],
        "namespace_id": namespace_id,
        "import_url": import_url,
        # 可选：启用镜像以保持同步（如果需要）
        "mirror": True,
    }

    resp = request_retry('POST', url, headers=GL_HEADERS, json=payload, timeout=30)

    if resp.status_code in (200, 201, 202):
        print(f"  ✅ 已触发导入: {repo['full_name']}")
        return True
    else:
        print(f"  ❌ 导入失败 {repo['full_name']}: {resp.status_code} {resp.text[:300]}")
        return False


def main():
    print(f"GitHub 组织: {GITHUB_ORG}")
    print(f"GitLab 群组: {GITLAB_GROUP}  (base: {GITLAB_BASE_URL})")

    # 1. 获取 GitLab 目标群组 ID
    print("正在获取 GitLab 群组 ID...")
    try:
        namespace_id = get_gitlab_group_id(GITLAB_GROUP)
        print(f"  群组 ID: {namespace_id}")
    except Exception as exc:
        sys.exit(f"无法获取群组 '{GITLAB_GROUP}' 的 ID: {exc}")

    # 2. 获取 GitHub 仓库列表
    print("正在获取 GitHub 仓库列表...")
    repos = list_github_repos(GITHUB_ORG)
    print(f"共发现 {len(repos)} 个仓库")

    # 3. 获取 GitLab 群组中已存在的项目，计算尚未导入的仓库
    print("正在获取 GitLab 已存在的项目...")
    try:
        existing_paths = list_gitlab_repo_paths(namespace_id)
    except Exception as exc:
        sys.exit(f"无法获取 GitLab 群组 '{GITLAB_GROUP}' 的项目列表: {exc}")
    print(f"GitLab 群组中已有 {len(existing_paths)} 个项目\n")

    missing_repos = [r for r in repos if r["name"].lower() not in existing_paths]
    skipped = len(repos) - len(missing_repos)
    if skipped:
        print(f"已导入，跳过: {skipped} 个")
    print(f"待迁移: {len(missing_repos)} 个仓库\n")

    if not missing_repos:
        print("没有需要迁移的仓库，全部已存在。")
        return

    success = 0
    failed = 0
    for i, repo in enumerate(missing_repos, 1):
        print(f"[{i}/{len(missing_repos)}] {repo['full_name']}")
        try:
            if import_repo_by_url(repo, namespace_id):
                success += 1
            else:
                failed += 1
        except Exception as exc:
            print(f"  ❌ 异常: {exc}")
            failed += 1

        # GitLab 对项目创建/导入有速率限制，保守间隔
        if i < len(missing_repos):
            time.sleep(5)  # URL 导入通常比 GitHub 导入限速宽松，5秒是较安全的间隔

    print(f"\n完成。成功: {success}, 失败: {failed}, 跳过(已存在): {skipped}")


if __name__ == "__main__":
    main()