#!/usr/bin/env python3
"""
将 opendoccn 组织的所有仓库 fork 到 opendoccn-archive 组织
使用 GitHub REST API
"""

from os import path
import shutil
import tempfile
import subprocess as subp
import json
import requests
import time
import sys
import os
from BookerDownloadTool.util import request_retry
from BookerDownloadTool.util import create_driver
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
import selenium.webdriver.support.expected_conditions as EC
from selenium.common.exceptions import TimeoutException


# ============ 配置区域 ============
SOURCE_ORG = "opendoccn"           # 源组织
TARGET_ORG = "opendoccn0"   # 目标组织
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

def create_repo(owner, repo, org=True):
    url = f"https://api.github.com/orgs/{owner}/repos" if org else "https://api.github.com/user/repos"
    data = {'name': repo, 'private': False}
    r = request_retry('POST', url, json=data, headers=HEADERS)
    if 200 <= r.status_code < 300: 
        return {'code': 0, 'msg': ''}
    else:
        return {'code': r.status_code, 'msg': r.json().get('message', '')}


def is_repo_empty_by_size(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}"
    response = request_retry('GET', url, headers=HEADERS)
    repo_data = response.json()
    return repo_data.get('size', 0) == 0

def check_repo_exists(target_org, repo_name):
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

def import_repos():
    gh_repos = json.loads(open('opendoccn_repos.json', encoding='utf8').read())
    exi_repos = set([r['name'] for r in get_all_repos('opendoccn0')])


    driver: Chrome = create_driver(False)
    cookie_fname = 'gh_cookies.json'
    if path.isfile(cookie_fname):
        print('导入Cookie')
        driver.get('https://github.com')
        driver.implicitly_wait(20)
        cookies = json.loads(open(cookie_fname, encoding='utf8').read())
        # for c in cookies: c['domain'] = '.csdn.net'
        print(cookies)
        for c in cookies: 
            try:
                driver.add_cookie(c)
            except: 
                pass
    
    driver.get('https://github.com/login')
    print('等待页面加载')
    driver.implicitly_wait(20)
    print('页面加载完成')   
    if 'login' in driver.current_url:
        WebDriverWait(driver, 60).until(
            lambda d: 'login' not in d.current_url and 'sessions' not in d.current_url
        )
        cookies = driver.get_cookies()
        # for c in cookies: c['domain'] = '.csdn.net'
        open(cookie_fname, 'w', encoding='utf8').write(json.dumps(cookies))

    for i, r in enumerate(gh_repos):
        name = r['name']
        if name in exi_repos: continue
        if name == 'home': continue
        imp_url = f'https://gitcode.com/OpenDocCN1/{name}.git'
        print(f'[{i+1}/{len(gh_repos)}] opendoccn/{name} {imp_url}')

        driver.get('https://github.com/new/import')
        driver.implicitly_wait(20)

        url_text = '#_r_2_'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, url_text))
        )
        driver.find_element(By.CSS_SELECTOR, url_text).send_keys(imp_url)

        name_text = '#repository-name-input'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, name_text))
        )
        driver.find_element(By.CSS_SELECTOR, name_text).send_keys(name)

        ow_sel = '#owner-dropdown-header-button'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ow_sel))
        )
        driver.execute_script(
            '''
            document.querySelector(arguments[0]).click()
            ''',
            ow_sel,
        )
        time.sleep(0.5)
        ow_text = 'input.prc-components-Input-IwWrt:nth-child(2)'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ow_text))
        )
        driver.find_element(By.CSS_SELECTOR, ow_text).send_keys('opendoccn0')
        time.sleep(0.5)
        ow_dropdown = '.prc-ActionList-ActionListContent-KBb8-'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ow_dropdown))
        )
        driver.execute_script(
            '''
            document.querySelector(arguments[0]).click()
            ''',
            ow_dropdown,
        )
        time.sleep(1.5)
        pub_radio = '#_r_10_'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, pub_radio))
        )
        driver.execute_script(
            '''
            document.querySelector(arguments[0]).click()
            ''',
            pub_radio,
        )

        print('等待提交按钮启用')
        sub_btn = 'body > div.logged-in.env-production.page-responsive > div.application-main > main > react-app > div > form > div.prc-Stack-Stack-UQ9k6 > div > button:nth-child(2)'
        WebDriverWait(driver, 20).until(
            lambda d: d.find_element(By.CSS_SELECTOR, sub_btn).is_enabled()
        )
        print('提交按钮启用')
        
        for i in range(10):
            print(f'点击提交 #{i+1}')
            driver.execute_script(
                '''
                document.querySelector(arguments[0]).click()
                ''',
                sub_btn,
            )
            try:
                WebDriverWait(driver, 5).until(
                lambda d: 'new/import' not in d.current_url
            )
            except TimeoutException:
                pass
            if 'new/import' not in driver.current_url: break
    driver.quit()


def fork_repos():
    print(f"🚀 开始将 {SOURCE_ORG} 的所有仓库 fork 到 {TARGET_ORG}")
    print("=" * 60)

    data_dir = os.path.join(tempfile.gettempdir(), 'gh-migrate')
    os.makedirs(data_dir, exist_ok=True)

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

    for idx, repo in enumerate(repos, 1):
        repo_name = repo["name"]
        print(f"\n[{idx}/{len(repos)}] 处理: {repo_name}")

        # 检查是否已存在
        if not check_repo_exists(TARGET_ORG, repo_name):
            print(f"⏭️ 目标组织中不存在 {repo_name}，正在创建")
            r = create_repo(TARGET_ORG, repo_name)
            if r['code'] != 0:
                print(f'{TARGET_ORG}/{repo_name} 创建失败，跳过')
                continue
        if not is_repo_empty_by_size(TARGET_ORG, repo_name):
            print(f'{TARGET_ORG}/{repo_name} 已有内容，跳过')
            continue

        # 执行 clone+push
        try:
            subp.run([
                'git', 'clone', f'https://github.com/{SOURCE_ORG}/{repo_name}'
            ], cwd=data_dir).check_returncode()
            repo_dir = os.path.join(data_dir, repo_name)
            subp.run([
                'git', 'push', f'https://github.com/{TARGET_ORG}/{repo_name}'
            ], cwd=repo_dir).check_returncode()
        except subp.CalledProcessError as ex:
            print(f'{SOURCE_ORG}/{repo_name} -> {TARGET_ORG}/{repo_name} 迁移失败，跳过')
            continue

        shutil.rmtree(repo_dir, True)

        # 避免触发 GitHub API 限流，每次 fork 后等待一下[reference:1]
        # 如果仓库数量较少，可以适当减少或增加等待时间
        if idx < len(repos):
            time.sleep(2)

    # 3. 输出统计
    print("\n" + "=" * 60)
    print("📊 执行完成！")

def main():
    import_repos()

if __name__ == "__main__":
    main()