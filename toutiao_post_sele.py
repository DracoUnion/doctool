import traceback
import argparse
from os import path
import time
import os 
import json
import uuid
import tempfile
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
import selenium.webdriver.support.expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from BookerDownloadTool.util import *
from BookerMarkdownTool.util import get_md_title

config = {
    'selectPwTab': 'li[aria-label="账密登录"]',
    'unText': 'input[placeholder="手机号/邮箱"]',
    'pwText': 'input[placeholder="密码"]',
    'protCheck': 'span[aria-label="协议勾选框"]',
    'loginBtn': 'button[type="submit"]',
    'contText': '.ProseMirror',
    'titleText': '.editor-title>textarea',
    'coverRadio': '#root > div > div.left-column > div > div.form-wrap > div.form-container > div:nth-child(1) > div > div.edit-input > div > div > label:nth-child(3) > span > div',
    'pubBtn': '.publish-btn-last',
    'msgBox': '.byte-message-wrapper',
    'impWait': 5,
    'condWait': 60,
    'cookie_fname': 'toutiao_cookie.json',
}

def md2html_pandoc(md):
    fname = path.join(tempfile.gettempdir(), uuid.uuid4().hex + '.md')
    ofname = fname[:-3] + '.html'
    open(fname, 'w', encoding='utf8').write(md)
    subp.Popen(['pandoc', fname, '-o', ofname]).communicate()
    html = open(ofname, encoding='utf8').read()
    safe_remove(fname)
    safe_remove(ofname)
    return html

def create_driver(headless=False):
    options = Options()
    options.binary_location = r'D:\Program Files\chrome-for-testing\chrome.exe'
    if headless:
        options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    options.add_argument(f'--user-agent={UA}')
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=options)
    driver.set_script_timeout(1000)
    # StealthJS
    # stealth = open(d('stealth.min.js')).read()
    # driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    #     "source": stealth
    # })
    return driver

def toutiao_post_retry(args, title, body):
    for i in range(args.retry):
        try:
            driver = create_driver(args.headless)
            toutiao_post(
                driver, args.un, args.pw, 
                title, body, 
                args.retry,
            )
            driver.close()
            break
        except Exception as ex:
            print(f'CSDN Post Retry #{i}: {ex}')
            if i == args.retry - 1:
                raise ex
                
    

def toutiao_post(driver: Chrome, un, pw, title, body, retry=20):
    # 登录
    if path.isfile(config['cookie_fname']):
        print('导入Cookie')
        driver.get('https://mp.toutiao.com')
        cookies = json.loads(open(config['cookie_fname'], encoding='utf8').read())
        # for c in cookies: c['domain'] = '.csdn.net'
        print(cookies)
        for c in cookies: driver.add_cookie(c)
    print('打开登录页面')
    driver.get('https://mp.toutiao.com/auth/page/login')
    print('等待页面加载')
    driver.implicitly_wait(config['impWait'])
    print('页面加载完成')
    print('driver.current_url', driver.current_url)
    if driver.current_url.startswith('https://mp.toutiao.com/auth/page/login'):
        print('添加账号密码')
        '''
        driver.find_element(By.CSS_SELECTOR, config['selectPwTab']).click()
        driver.find_element(By.CSS_SELECTOR, config['unText']).send_keys(un)
        driver.find_element(By.CSS_SELECTOR, config['pwText']).send_keys(pw)
        # driver.find_element(By.CSS_SELECTOR, config['cosentCheck']).click()
        print('登录')
        driver.find_element(By.CSS_SELECTOR, config['loginBtn']).click()
        '''
        print('等待登录后跳转')
        WebDriverWait(driver, config['condWait']).until(
            lambda d: not d.current_url.startswith('https://mp.toutiao.com/auth/page/login')
        )
        print('保存 COOKIE')
        cookies = driver.get_cookies()
        # for c in cookies: c['domain'] = '.csdn.net'
        open(config['cookie_fname'], 'w', encoding='utf8').write(json.dumps(cookies))

    # driver.current_url
    print('打开编辑器')
    driver.get('https://mp.toutiao.com/profile_v4/graphic/publish')
    print('等待编辑器加载')
    driver.implicitly_wait(config['impWait'])
    print('编辑器加载完成')
    print('driver.current_url', driver.current_url)
    
    
    print('填写标题')
    el_title = driver.find_element(By.CSS_SELECTOR, config['titleText'])
    el_title.clear()
    el_title.send_keys(title[:100])
    # driver.find_element(By.CSS_SELECTOR, config['bodyText']).send_keys(body)
    
    print('选择封面')
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['coverRadio']))
    )
    # el_col = driver.find_element(By.CSS_SELECTOR, config['colRadio'])
    # el_col.click()
    driver.execute_script('''
        document.querySelector(arguments[0]).click()
    ''', config['coverRadio'])
    # el_gift = driver.find_element(By.CSS_SELECTOR, config['giftRadio'])
    # el_gift.click()
    
    # driver.execute_script('''
    #     document.querySelector(arguments[0]).click()
    # ''', config['giftRadio'])
    # WebDriverWait(driver, config['condWait']).until(
    #     EC.presence_of_element_located((By.CSS_SELECTOR, config['giftBtn']))
    # )
    # el_gift = driver.find_element(By.CSS_SELECTOR, config['giftBtn'])
    # el_gift.click()
    
    print('填写内容')    
    html = md2html_pandoc(body)
    driver.execute_script('''
        document.querySelector(arguments[0]).innerHTML = arguments[1]
    ''', config['contText'], html)
   
    for i in range(retry):
        print(f'发布：{i}')
        # driver.find_element(By.CSS_SELECTOR, config['pubBtn']).click()
        driver.execute_script('''
            document.querySelector(arguments[0]).click()
        ''', config['pubBtn'])
        time.sleep(5)
        driver.execute_script('''
            document.querySelector(arguments[0]).click()
        ''', config['pubBtn'])
        print('等待消息提示')

        WebDriverWait(driver, config['condWait']).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, config['msgBox']))
        )
        el_msg = driver.find_element(By.CSS_SELECTOR, config['msgBox'])
        msg = ''
        for i in range(5):
            msg += el_msg.text
            time.sleep(0.5)
        if '成功' in msg:
            print('发布成功')
            break
        else:
            print(msg)
       
        
        if i == retry - 1:
            raise Exception('发布失败')
        time.sleep(1)


def main():
    
    parser = argparse.ArgumentParser(prog="GPTTestTrain", description="GPTTestTrain", formatter_class=argparse.RawDescriptionHelpFormatter)
    # parser.add_argument("-v", "--version", action="version", version=f"BookerMarkdownTool version: {__version__}")
    # parser.set_defaults(func=lambda x: parser.print_help())
    # subparsers = parser.add_subparsers()
    # train_parser = subparsers.add_parser("train", help="train GLM model")
    parser.add_argument("fname", help="MD fname")
    parser.add_argument("-u", "--un", default=os.environ.get('CSDN_USERNAME', ''), help="username")
    parser.add_argument("-p", "--pw", default=os.environ.get('CSDN_PASSWORD', ''), help="password")
    parser.add_argument("-c", "--cate", default='默认分类',  help="cate")
    parser.add_argument("-t", "--tags", default='默认标签',  help="tags")
    parser.add_argument("-r", "--retry", type=int, default=20,  help="retry")
    parser.add_argument("-H","--headless", action='store_true', help="hdls")
    args = parser.parse_args()

    if path.isfile(args.fname):
        fnames = [args.fname]
    else:
        fnames = [
            path.join(args.fname, f)
            for f in os.listdir(args.fname)
        ]
    fnames = [f for f in fnames if f.endswith('.md')]
    if not fnames:
        print('请提供 MD 文件或目录')
        return
    
    # driver.maximize_window()
    for f in fnames:
        print(f)
        md = open(f, encoding='utf8').read()
        title, pos = get_md_title(md)
        if not title:
            print(f'{f} MD 文件无标题')
            return
        body = md[pos[1]:]
        toutiao_post_retry(args, title, body)
        os.remove(f)


    
if __name__ == '__main__': 
    try:
        main()
    except:
        traceback.print_exc()