import traceback
import argparse
from os import path
import time
import os 
import json
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
import selenium.webdriver.support.expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from BookerDownloadTool.util import *
from BookerMarkdownTool.util import get_md_title

config = {
    'selectPwTab': '.SignFlow-tab:last-of-type',
    'unText': 'input[placeholder="手机号或邮箱"]',
    'pwText': 'input[placeholder="密码"]',
    'loginBtn': '.JmYzaky7MEPMFcJDLNMG',
    'docBtn': 'button[aria-label="导入"]',
	'impBtn': '.Menu>button[aria-label="导入文档"]',
    'impFile': '.Modal-content input[type=file]',
    'titleText': 'textarea.Input',
    'contText': '.DraftEditor-root',
    'colRadio': '#PublishPanel-columnLabel-1',
    'giftRadio': '#PublishPanel-RewardSetting-0',
    'giftBtn': '.RewardForm-rewardSubmit',
    'pubBtn': '.JmYzaky7MEPMFcJDLNMG',
    'pubBtnDis': '.JmYzaky7MEPMFcJDLNMG[disabled]',
    'noticeBox': '.Notification',
    'alertBtn': '.Modal-content button',
    'impWait': 5,
    'condWait': 15,
    'cookie_fname': 'zhihu_cookie.json',
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
    custom_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    if headless:
        options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    options.add_argument(f'--user-agent={UA}')
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

def zhihu_post_retry(args, title, fname):
    for i in range(args.retry):
        try:
            driver = create_driver(args.headless)
            zhihu_post(
                driver, args.un, args.pw, 
                title, fname, 
                args.retry,
            )
            driver.close()
            break
        except Exception as ex:
            print(f'CSDN Post Retry #{i}: {ex}')
            # if i == args.retry - 1:
            #     raise ex
                
    

def zhihu_post(driver: Chrome, un, pw, title, fname, retry=20):
    # 登录
    if path.isfile(config['cookie_fname']):
        print('导入Cookie')
        driver.get('https://zhihu.com')
        cookies = json.loads(open(config['cookie_fname'], encoding='utf8').read())
        # for c in cookies: c['domain'] = '.csdn.net'
        print(cookies)
        for c in cookies: driver.add_cookie(c)
    print('打开登录页面')
    driver.get('https://www.zhihu.com/signin')
    print('等待页面加载')
    driver.implicitly_wait(config['impWait'])
    print('页面加载完成')
    print('driver.current_url', driver.current_url)
    if driver.current_url.startswith('https://www.zhihu.com/signin'):
        print('添加账号密码')
        driver.find_element(By.CSS_SELECTOR, config['selectPwTab']).click()
        driver.find_element(By.CSS_SELECTOR, config['unText']).send_keys(un)
        driver.find_element(By.CSS_SELECTOR, config['pwText']).send_keys(pw)
        # driver.find_element(By.CSS_SELECTOR, config['cosentCheck']).click()
        print('登录')
        driver.find_element(By.CSS_SELECTOR, config['loginBtn']).click()
        print('等待登录后跳转')
        WebDriverWait(driver, 60).until(
            lambda d: not d.current_url.startswith('https://www.zhihu.com/signin')
        )
        print('保存 COOKIE')
        cookies = driver.get_cookies()
        # for c in cookies: c['domain'] = '.csdn.net'
        open(config['cookie_fname'], 'w', encoding='utf8').write(json.dumps(cookies))

    # driver.current_url
    print('打开编辑器')
    driver.get('https://zhuanlan.zhihu.com/write')
    print('等待编辑器加载')
    driver.implicitly_wait(config['impWait'])
    print('编辑器加载完成')
    print('driver.current_url', driver.current_url)
    
    
    print('填写标题')
    el_title = driver.find_element(By.CSS_SELECTOR, config['titleText'])
    el_title.clear()
    el_title.send_keys(title[:100])
    # driver.find_element(By.CSS_SELECTOR, config['bodyText']).send_keys(body)
    
    print('选择专栏')
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['colRadio']))
    )
    # el_col = driver.find_element(By.CSS_SELECTOR, config['colRadio'])
    # el_col.click()
    driver.execute_script('''
        document.querySelector(arguments[0]).click()
    ''', config['colRadio'])
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

    el_alert = driver.find_element(By.CSS_SELECTOR, config['alertBtn'])
    if el_alert: el_alert.click()
    
    # html = md2html_pandoc(body)
    # driver.execute_script('''
    #     document.querySelector(arguments[0]).innerHTML = arguments[1]
    # ''', config['contText'], html)
    
  
    el_doc = driver.find_element(By.CSS_SELECTOR, config['docBtn'])
    el_doc.click()
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['impBtn']))
    )
    el_imp = driver.find_element(By.CSS_SELECTOR, config['impBtn'])
    el_imp.click()
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['impFile']))
    )
    el_file = driver.find_element(By.CSS_SELECTOR, config['impFile'])
    el_file.send_keys(fname)
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['titleText']))
    )
    
    time.sleep(10)

   
    for i in range(retry):
        print(f'发布：{i}')
        WebDriverWait(driver, config['condWait']).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, config['pubBtnDis']))
        )
        # driver.find_element(By.CSS_SELECTOR, config['pubBtn']).click()
        driver.execute_script('''
            document.querySelector(arguments[0]).click()
        ''', config['pubBtn'])
        print('等待消息提示')
        try:
            WebDriverWait(driver, config['condWait']).until(
                lambda d: (
                    'edit' not in d.current_url and
                    'write' not in d.current_url
                )
            )
            print('发布成功')
            break
        except:
            pass
            
        try:
            WebDriverWait(driver, config['condWait']).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, config['noticeBox']))
            )
            time.sleep(1)
            el_notice = driver.find_element(By.CSS_SELECTOR, config['noticeBox'])
            notice = el_notice.text
            print(notice)
        except Exception as ex:
            print(ex)
        
        # if i == retry - 1:
        #     raise Exception('发布失败')
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
        # body = md[pos[1]:]
        fname = path.abspath(f)
        zhihu_post_retry(args, title, fname)
        os.remove(f)


    
if __name__ == '__main__': 
    try:
        main()
    except:
        traceback.print_exc()