from pyquery import PyQuery as pq
import requests
from BookerDownloadTool.util import request_retry
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
import selenium.webdriver.support.expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import json 
from os import path
import argparse

cookie = open('gh_cookie.txt', encoding='utf8').read()
dft_hdrs = {
    'Cookie': cookie,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
}


config = {
    'inviteBtn': 'button[aria-label="Invite member"]',
    'inviteDlg': '#invite-member-dialog',
    'inviteText': '#org-invite-complete-input',
    'inviteBtn2': 'div.input-group-button--autocomplete-embedded-icon>button[type=submit]',
    'sendBtn': 'body > div.logged-in.env-production.page-responsive > div.application-main > main > div.settings-next.container-sm.p-4 > form > div > div > button',
    'inviteTip': 'anchored-position[aria-label="results"]',
    'inviteTip0': 'anchored-position[aria-label="results"]>div:first-of-type',
    'cookie_fname': 'gh_cokies.json',
    'condWait': 5,
    'impWait': 60,
}


def create_driver(headless=False):
    options = Options()
    options.binary_location = r'D:\Program Files\chrome-for-testing\chrome.exe'
    custom_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    if headless:
        options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f'--user-agent={custom_user_agent}')
    driver = webdriver.Chrome(options=options)
    driver.set_script_timeout(1000)
    # StealthJS
    # stealth = open(d('stealth.min.js')).read()
    # driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    #     "source": stealth
    # })
    return driver

def get_tokrn(html):
    return pq(html).find('input[name="authenticity_token"]').val()

def get_iid(html):
    return pq(html).find('input[name="invitee_id"]').val()

def invite_retry(args, name):
    for i in range(args.retry):
        try:
            driver = create_driver(args.headless)
            invite(
                driver, name
            )
            driver.close()
            break
        except Exception as ex:
            print(f'GH invite Retry #{i}: {ex}')
            # if i == args.retry - 1:
            #     raise ex

def invite(driver: Chrome, name: str):
    if path.isfile(config['cookie_fname']):
        print('导入Cookie')
        driver.get('https://github.com/')
        cookies = json.loads(open(config['cookie_fname'], encoding='utf8').read())
        # for c in cookies: c['domain'] = '.csdn.net'
        print(cookies)
        for c in cookies: driver.add_cookie(c)
    print('打开登录页面')
    driver.get('https://github.com/login')
    print('等待页面加载')
    driver.implicitly_wait(config['impWait'])
    print('页面加载完成')
    print('driver.current_url', driver.current_url)
    if driver.current_url.startswith('https://github.com/login'):
        print('添加账号密码')
        print('等待登录后跳转')
        WebDriverWait(driver, 60).until(
            lambda d: not d.current_url.startswith('https://github.com/login')
        )
        print('保存 COOKIE')
        cookies = driver.get_cookies()
        open(config['cookie_fname'], 'w', encoding='utf8').write(json.dumps(cookies))

    print('打开邀请页面')
    driver.get('https://github.com/orgs/OpenDocCN/people')
    print('等待邀请页面加载')
    WebDriverWait(driver, config['condWait']).until(
        lambda d: 'publish' in d.current_url
    )
    print('driver.current_url', driver.current_url)
    print('邀请页面加载完成')
    
    print('点击邀请按钮')
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['inviteBtn']))
    )
    driver.find_element(By.CSS_SELECTOR, config['inviteBtn']).click()
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['inviteDlg']))
    )
    print('填写邀请人')
    driver.find_element(By.CSS_SELECTOR, config['inviteText']).send_keys(name)
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['inviteTip']))
    )
    print('点击邀请人')
    el_invite_tip0 =  driver.find_element(By.CSS_SELECTOR, config['inviteTip0'])
    if 'isn\'t a GitHub member' in el_invite_tip0.text:
        print(f'{name} 不存在！')
        return
    el_invite_tip0.click()
    driver.find_element(By.CSS_SELECTOR, config['inviteBtn2']).click()
    
    print('打开编辑页面')
    WebDriverWait(driver, config['condWait']).until(
        lambda d: 'edit' in d.current_url
    )
    
    print('打开发送按钮')
    driver.find_element(By.CSS_SELECTOR, config['sendBtn']).click()
    WebDriverWait(driver, config['condWait']).until(
        lambda d: 'edit' not in d.current_url
    )
    print(f'{name} 邀请成功！')
    

def main():

    parser = argparse.ArgumentParser(prog="GPTTestTrain", description="GPTTestTrain", formatter_class=argparse.RawDescriptionHelpFormatter)
    # parser.add_argument("-v", "--version", action="version", version=f"BookerMarkdownTool version: {__version__}")
    # parser.set_defaults(func=lambda x: parser.print_help())
    # subparsers = parser.add_subparsers()
    # train_parser = subparsers.add_parser("train", help="train GLM model")
    parser.add_argument("fname", help="list fname")
    parser.add_argument("-r", "--retry", type=int, default=20,  help="retry")
    parser.add_argument("-H","--headless", action='store_true', help="hdls")
    args = parser.parse_args()

    li = open(args.fname, encoding='utf8').read().split('\n')
    li = [n for n in li if n]
    for name in li:
        print(name)
        invite_retry(args, name)

if __name__ == '__main__': main()