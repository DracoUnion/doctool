from os import path
import os
import json
import requests
import time
from BookerDownloadTool.util import create_driver
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
import selenium.webdriver.support.expected_conditions as EC
from selenium.common.exceptions import TimeoutException

hdrs = {'Authorization': 'Bearer ' + os.environ.get('GITCODE_TOKEN', '')}

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

def import_gh_repos(ow):
    gh_repos = json.loads(open('opendoccn_repos.json', encoding='utf8').read())
    exi_repos = set(get_org_repos(ow))
    key = os.environ.get("GH_TOKEN", '')


    driver: Chrome = create_driver(False)
    cookie_fname = 'gitcode_cookies.json'
    if path.isfile(cookie_fname):
        print('导入Cookie')
        driver.get('https://gitcode.com')
        cookies = json.loads(open(cookie_fname, encoding='utf8').read())
        # for c in cookies: c['domain'] = '.csdn.net'
        print(cookies)
        for c in cookies: driver.add_cookie(c)
    
    driver.get('https://gitcode.com/login')
    print('等待页面加载')
    driver.implicitly_wait(20)
    print('页面加载完成')   
    if 'login' in driver.current_url:
        WebDriverWait(driver, 60).until(
            lambda d: 'login' not in d.current_url
        )
        cookies = driver.get_cookies()
        # for c in cookies: c['domain'] = '.csdn.net'
        open(cookie_fname, 'w', encoding='utf8').write(json.dumps(cookies))

    for i, r in enumerate(gh_repos):
        name = r['name']
        if name in exi_repos: continue
        if name == 'home': continue
        imp_url = f'https://oauth2:{key}@github.com/OpenDocCN/{name}.git'
        print(f'[{i+1}/{len(gh_repos)}] {ow}/{name} {imp_url}')
        
        driver.get('https://gitcode.com/create/migrate?type=3')
        driver.implicitly_wait(20)
        imp_url_text = '#app > div > div.gc-base-layout-content > div > div > div > div > div > div > div > div:nth-child(2) > form > div.mt-\[16px\].mb-\[16px\].font-\[none\].max-md\:mt-\[16px\] > div.mt-\[16px\].max-md\:mt-\[16px\].font-normal > form > div:nth-child(1) > div > div.devui-form__control-container.devui-form__control-container--horizontal > div > div > input'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, imp_url_text))
        )
        driver.execute_script(
            '''
            var el = document.querySelector(arguments[0]);
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', {bubbles: true}))
            ''',
            imp_url_text, imp_url,
        )
        name_text = '#app > div > div.gc-base-layout-content > div > div > div > div > div > div > div > div:nth-child(2) > form > div.mt-\[16px\].mb-\[16px\].font-\[none\].max-md\:mt-\[16px\] > div.mt-\[16px\].max-md\:mt-\[16px\].font-normal > form > div:nth-child(3) > div > div.devui-form__control-container.devui-form__control-container--horizontal > div > div > input'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, name_text))
        )
        driver.execute_script(
            '''
            var el = document.querySelector(arguments[0]);
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', {bubbles: true}))
            ''',
            name_text, name,
        )
        ow_sel = '.devui-editable-select-input__suffix'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ow_sel))
        )
        driver.execute_script(
            '''
            document.querySelector(arguments[0]).click()
            ''',
            ow_sel,
        )
        ow_dropdown = 'li.devui-editable-select__item:nth-child(2)'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ow_dropdown))
        )
        driver.execute_script(
            '''
            document.querySelector(arguments[0]).click()
            ''',
            ow_dropdown,
        )
        repo_name_text = 'div.devui-input:nth-child(3) > div:nth-child(1) > input:nth-child(1)'
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, repo_name_text))
        )
        driver.execute_script(
            '''
            var el = document.querySelector(arguments[0]);
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', {bubbles: true}))
            ''',
            repo_name_text, name,
        )
        driver.execute_script(
            'document.querySelector(arguments[0]).click()',
            '.devui-radio-group > div:nth-child(1) > label:nth-child(1) > input:nth-child(1)',
        )
        driver.execute_script(
            'document.querySelector(arguments[0]).click()',
            'div.repo-import-checkbox:nth-child(2) > div:nth-child(1) > label:nth-child(2) > span:nth-child(3)',
        )
        
        print('等待提交按钮启用')
        driver.execute_script(
            'window.scrollTo(0, document.body.scrollHeight);',
        )
        sub_btn_sele = 'button.devui-button.devui-button--solid.devui-button--solid--primary.devui-button--md.bg-B500.ml-2'
        WebDriverWait(driver, 20).until(
            lambda d: d.find_element(By.CSS_SELECTOR, sub_btn_sele).is_enabled()
        )
        print('提交按钮启用')
        for i in range(10):
            print(f'点击提交 #{i+1}')
            driver.execute_script(
                '''
                document.querySelector(arguments[0]).click()
                ''',
                sub_btn_sele,
            )
            try:
                WebDriverWait(driver, 5).until(
                    lambda d: 'migrate' not in d.current_url
                )
            except TimeoutException:
                pass
            if 'migrate' not in driver.current_url: break
    driver.quit()
        

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
    import_gh_repos('opendoccn1')

if __name__ == '__main__': main()