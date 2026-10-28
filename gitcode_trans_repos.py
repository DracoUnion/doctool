from os import path
import os
import json
import requests
import time
from BookerDownloadTool.util import camou_create_driver

hdrs = {'Authorization': 'Bearer ' + os.environ.get('GITCODE_TOKEN', '')}

def get_gh_org_repos(org: str, token: str | None = None) -> list[str]:
    """
    获取 GitHub 组织下的所有仓库名称。

    :param org:   组织名称，例如 "python"
    :param token: GitHub Personal Access Token（可选，但强烈建议提供）
                  - 未认证：60 次/小时
                  - 已认证：5000 次/小时，且能访问私有仓库
    :return:      仓库名称列表
    """
    url = f"https://api.github.com/orgs/{org}/repos"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # type=all 会返回私有仓库（需要 token 有 repo 权限），public 仅公开仓库
    params = {"per_page": 100, "page": 1, "type": "all" if token else "public"}

    repos: list[str] = []
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 404:
            raise ValueError(f"组织 '{org}' 不存在，或无权访问")
        if resp.status_code == 403:
            raise PermissionError("触发 GitHub API 速率限制，请稍后重试或提供 token")
        resp.raise_for_status()

        data = resp.json()
        if not data:
            break

        repos.extend(item["name"] for item in data)

        # 通过 Link 头判断是否还有下一页（比 len(data) < per_page 更可靠）
        if "next" not in resp.links:
            break
        params["page"] += 1

    return repos

def get_org_repos(org):
    repos = []
    url = f'https://api.gitcode.com/api/v5/orgs/{org}/repos'
    idx = 1
    while True:
        params = {
            'per_page': 100,
            'page': idx,
        }
        r = requests.get(url, params=params, headers=hdrs)
        if 400 <= r.status_code < 600:
            break
        pt = r.json()
        if len(pt) == 0:
            break
        repos += [r['path'] for r in pt]
        idx += 1

    return repos

def import_org_repo(ow, repo, url):
    url = f'https://api.gitcode.com/api/v5/orgs/{ow}/repos'
    data = {
        'name': repo,
        'public': 1,
        'import_url': url,
    }
    r = requests.post(url, json=data, headers=hdrs)
    if 200 <= r.status_code < 300:
        return {'code': 0, 'msg': ''}
    else:
        return {'code': r.status_code, 'msg': r.text}

def del_repo(ow, repo):
    url = f'https://api.gitcode.com/api/v5/repos/{ow}/{repo}'
    r = requests.delete(url, headers=hdrs)
    if 200 <= r.status_code < 300:
        return {'code': 0, 'msg': ''}
    else:
        return {'code': r.status_code, 'msg': r.text}

def import_gh_repos(ow, gh_org):
    fname = f'{gh_org}_repos.json'
    key = os.environ.get("GH_TOKEN", '')
    if not path.isfile(fname):
        repos = get_gh_org_repos(gh_org, key)
        open(fname, 'w', encoding='utf8').write(
            json.dumps(repos))
    gh_repos = json.loads(open(f'{gh_org}_repos.json', encoding='utf8').read())
    print(gh_repos)

    exi_repos = set(get_org_repos(ow))
    key = os.environ.get("GH_TOKEN", '')


    cookie_fname = 'gitcode_cookies.json'
    with camou_create_driver(headless=True) as (cam, ctx, page):
        if path.isfile(cookie_fname):
            print('导入Cookie')
            page.goto('https://gitcode.com')
            cookies = json.loads(open(cookie_fname, encoding='utf8').read())
            print(cookies)
            ctx.add_cookies(cookies)

        page.goto('https://gitcode.com/login')
        print('等待页面加载')
        try:
            page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        print('页面加载完成')
        if 'login' in page.url:
            # 等待手动登录或登录后自动跳转，最多 60s
            for _ in range(120):
                if 'login' not in page.url:
                    break
                page.wait_for_timeout(500)
            cookies = ctx.cookies()
            open(cookie_fname, 'w', encoding='utf8').write(json.dumps(cookies))

        for i, name in enumerate(gh_repos):
            if name in exi_repos: continue
            if name == 'home': continue
            imp_url = f'https://oauth2:{key}@github.com/{gh_org}/{name}.git'
            print(f'[{i+1}/{len(gh_repos)}] {ow}/{name} {imp_url}')

            page.goto('https://gitcode.com/create/migrate?type=3')
            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                pass
            imp_url_text = '#app > div > div.gc-base-layout-content > div > div > div > div > div > div > div > div:nth-child(2) > form > div.mt-\[16px\].mb-\[16px\].font-\[none\].max-md\:mt-\[16px\] > div.mt-\[16px\].max-md\:mt-\[16px\].font-normal > form > div:nth-child(1) > div > div.devui-form__control-container.devui-form__control-container--horizontal > div > div > input'
            page.locator(imp_url_text).wait_for(state='attached', timeout=20000)
            page.evaluate(
                '''([sel, val]) => {
                    var el = document.querySelector(sel);
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}))
                }''',
                [imp_url_text, imp_url],
            )
            name_text = '#app > div > div.gc-base-layout-content > div > div > div > div > div > div > div > div:nth-child(2) > form > div.mt-\[16px\].mb-\[16px\].font-\[none\].max-md\:mt-\[16px\] > div.mt-\[16px\].max-md\:mt-\[16px\].font-normal > form > div:nth-child(3) > div > div.devui-form__control-container.devui-form__control-container--horizontal > div > div > input'
            page.locator(name_text).wait_for(state='attached', timeout=20000)
            page.evaluate(
                '''([sel, val]) => {
                    var el = document.querySelector(sel);
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}))
                }''',
                [name_text, name],
            )
            ow_sel = '.devui-editable-select-input__suffix'
            page.locator(ow_sel).wait_for(state='attached', timeout=20000)
            page.evaluate('(sel) => document.querySelector(sel).click()', ow_sel)
            ow_dropdown = 'li.devui-editable-select__item:nth-child(2)'
            page.locator(ow_dropdown).wait_for(state='attached', timeout=20000)
            page.evaluate('(sel) => document.querySelector(sel).click()', ow_dropdown)
            repo_name_text = 'div.devui-input:nth-child(3) > div:nth-child(1) > input:nth-child(1)'
            page.locator(repo_name_text).wait_for(state='attached', timeout=20000)
            page.evaluate(
                '''([sel, val]) => {
                    var el = document.querySelector(sel);
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}))
                }''',
                [repo_name_text, name],
            )
            page.evaluate(
                '(sel) => document.querySelector(sel).click()',
                '.devui-radio-group > div:nth-child(1) > label:nth-child(1) > input:nth-child(1)',
            )
            page.evaluate(
                '(sel) => document.querySelector(sel).click()',
                'div.repo-import-checkbox:nth-child(2) > div:nth-child(1) > label:nth-child(2) > span:nth-child(3)',
            )

            print('等待提交按钮启用')
            page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
            sub_btn_sele = 'button.devui-button.devui-button--solid.devui-button--solid--primary.devui-button--md.bg-B500.ml-2'
            page.wait_for_function(
                '''(sel) => {
                    const el = document.querySelector(sel);
                    return el && !el.disabled && !el.getAttribute('aria-disabled');
                }''',
                arg=sub_btn_sele,
                timeout=20000,
            )
            print('提交按钮启用')
            for i in range(10):
                print(f'点击提交 #{i+1}')
                page.evaluate('(sel) => document.querySelector(sel).click()', sub_btn_sele)
                try:
                    page.wait_for_url(lambda u: 'migrate' not in u, timeout=5000)
                except Exception:
                    pass
                if 'migrate' not in page.url: break
        

'''
def del_org_priv_repos(ow):
    repos = get_org_priv_repos(ow)
    for i, r in enumerate(repos):
        print(f'[{i+1}/{len(repos)}] {ow}/{r}')
        res = del_repo(ow, r)
        if res['code'] == 0:
            print(f'{ow}/{r} 删除成功')
        else:
            print(f'{ow}/{r} 删除失败：{res["msg"]}')
        time.sleep(1.5)
'''

def main():
    # del_org_priv_repos('opendoccn1')
    import_gh_repos('CyberCommy1', 'CyberCommy')

if __name__ == '__main__': main()
