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
    'selectPwTab': '.login-third-passwd',
	'unBtn': 'input[autocomplete=username]',
    'pwBtn': 'input[autocomplete=current-password]',
    'pwVisBtn': '.base-input-icon-password',
    'cosentCheck': '.login-inform i',
    'loginBtn': '.login-form-item button',
    'titleText': 'input.article-bar__title',
    'bodyText': 'pre.editor__inner',
    'postButton': 'button.btn-publish',
    'noticeBox': '.notice-box span.notice',
    'pubPanel': '.modal__publish-article',
    'tagButton': '.mark_selection button.tag__btn-tag',
    'tagCloseButton': '.mark_selection_box button[title=关闭]',
    'tagPanel': '.mark_selection_box',
    'tagText': '.mark_selection_box input',
    'cateBtn': '#tagList>button',
    'cateDelBtn': '#tagList .tag__btn-tag-delete',
    'cateText': '#tagList span.tag__name',
    'catePanel': '.tag__options-content',
    'cateCloseBtn': '.tag__options-content button[title=关闭]',
    'pubBtn': '.modal__button-bar button:last-of-type',
    'impWait': 5,
    'condWait': 60,
    'cookie_fname': 'csdn_cookie.json',
}

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

def csdn_post_retry(args, title, body):
    for i in range(args.retry):
        try:
            driver = create_driver(args.headless)
            csdn_post(
                driver, args.un, args.pw, 
                title, body, 
                args.cate, args.tags.split(','),
                args.retry
            )
            driver.close()
            break
        except Exception as ex:
            print(f'CSDN Post Retry #{i}: {ex}')
            if i == args.retry - 1:
                raise ex
                
    

def csdn_post(driver: Chrome, un, pw, title, body, cate='默认分类', tags=[], retry=20):
    # 登录
    if path.isfile(config['cookie_fname']):
        print('导入Cookie')
        driver.get('https://csdn.net')
        cookies = json.loads(open(config['cookie_fname'], encoding='utf8').read())
        # for c in cookies: c['domain'] = '.csdn.net'
        print(cookies)
        for c in cookies: driver.add_cookie(c)
    print('打开登录页面')
    driver.get('https://passport.csdn.net/login')
    print('等待页面加载')
    driver.implicitly_wait(config['impWait'])
    print('页面加载完成')
    print('driver.current_url', driver.current_url)
    if driver.current_url.startswith('https://passport.csdn.net'):
        print('添加账号密码')
        driver.find_element(By.CSS_SELECTOR, config['selectPwTab']).click()
        driver.find_element(By.CSS_SELECTOR, config['unBtn']).send_keys(un)
        driver.find_element(By.CSS_SELECTOR, config['pwBtn']).send_keys(pw)
        # driver.find_element(By.CSS_SELECTOR, config['cosentCheck']).click()
        print('登录')
        driver.find_element(By.CSS_SELECTOR, config['loginBtn']).click()
        print('等待登录后跳转')
        WebDriverWait(driver, config['condWait']).until(
            lambda d: not d.current_url.startswith('https://passport.csdn.net')
        )
        print('保存 COOKIE')
        cookies = driver.get_cookies()
        # for c in cookies: c['domain'] = '.csdn.net'
        open(config['cookie_fname'], 'w', encoding='utf8').write(json.dumps(cookies))

    # driver.current_url
    print('打开编辑器')
    driver.get('https://editor.csdn.net/md/')
    print('等待编辑器加载')
    driver.implicitly_wait(config['impWait'])
    print('编辑器加载完成')
    print('driver.current_url', driver.current_url)
    print('填写标题内容')
    el_title = driver.find_element(By.CSS_SELECTOR, config['titleText'])
    el_title.clear()
    el_title.send_keys(title[:100])
    # driver.find_element(By.CSS_SELECTOR, config['bodyText']).send_keys(body)
    driver.execute_script(
        'document.querySelector(arguments[0]).textContent = arguments[1]',
        config['bodyText'], body,
    )
    print('点击发布按钮')
    driver.find_element(By.CSS_SELECTOR, config['postButton']).click()
    print('等待发布对话框')
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['pubPanel']))
    )
    print('发布对话框已加载')
    print('点击标签按钮')
    driver.find_element(By.CSS_SELECTOR, config['tagButton']).click()
    print('等待标签对话框')
    WebDriverWait(driver, config['condWait']).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, config['tagPanel']))
    )
    print('标签对话框已加载')
    print('设置标签')
    el_tag_text = driver.find_element(By.CSS_SELECTOR, config['tagText'])
    for t in tags:
        el_tag_text.send_keys(t)
        el_tag_text.send_keys(Keys.ENTER)
        el_tag_text.clear()
    driver.find_element(By.CSS_SELECTOR, config['tagCloseButton']).click()

    print('删除已有类别')
    for el in driver.find_elements(By.CSS_SELECTOR, config['cateDelBtn']):
        el.click()
    if not driver.find_elements(By.CSS_SELECTOR, config['cateText']):
        print('点击类别按钮')
        driver.find_element(By.CSS_SELECTOR, config['cateBtn']).click()
        print('等待类别文本框')
        WebDriverWait(driver, config['condWait']).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, config['cateText']))
        )
    print('类别文本框已加载')
    print('设置类别')
    driver.find_element(By.CSS_SELECTOR, config['cateText']).send_keys(cate)
    driver.find_element(By.CSS_SELECTOR, config['cateCloseBtn']).click()
    for i in range(retry):
        print(f'发布：{i}')
        driver.find_element(By.CSS_SELECTOR, config['pubBtn']).click()
        print('等待消息提示')
        WebDriverWait(driver, config['condWait']).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, config['noticeBox']))
        )
        time.sleep(1)
        el_notice = driver.find_element(By.CSS_SELECTOR, config['noticeBox'])
        notice = el_notice.text
        print('消息：', notice)
        if '文章标签' in notice:
            raise RuntimeError('请设置文章标签')
        if '成功' in notice or \
           '加载中' in notice:
            print('等待成功页面')
            WebDriverWait(driver, config['condWait']).until(
                lambda d: '/success/' in d.current_url
            )
            print('发布成功')
            break
        
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
        csdn_post_retry(args, title, body)
        os.remove(f)


    
if __name__ == '__main__': 
    try:
        main()
    except:
        traceback.print_exc()