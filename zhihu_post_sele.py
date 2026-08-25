import traceback
import argparse
from os import path
import time
import os
import json
import re
from camoufox.sync_api import Camoufox
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
    'colCombo': '.css-dlnfsc > button',
    'declCombo': 'div.css-be2u3:nth-child(4) > div:nth-child(2) > div:nth-child(1)  > button',
    'colItem': '.Select-list>.Select-option:nth-of-type({i})',
    'declItem': '.Select-list>.Select-option:nth-of-type(5)',
    'giftRadio': '#PublishPanel-RewardSetting-0',
    'giftBtn': '.RewardForm-rewardSubmit',
    'pubBtn': '.JmYzaky7MEPMFcJDLNMG',
    'pubBtnDis': '.JmYzaky7MEPMFcJDLNMG[disabled]',
    'noticeBox': '.Notification',
    'alertBtn': '.Modal-content button',
    'timeout': 15,
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

def js_click(page, sel, optional=False):
    """JS 触发点击，等价原 driver.execute_script('document.querySelector(sel).click()')"""
    if optional:
        page.evaluate("(sel) => { document.querySelector(sel)?.click() }", sel)
    else:
        page.evaluate("(sel) => { document.querySelector(sel).click() }", sel)

def normalise_cookies(cookies):
    """Playwright add_cookies 不接受 sameSite 为空，统一转成 Lax"""
    for c in cookies:
        if c.get('sameSite') is None:
            c['sameSite'] = 'Lax'
    return cookies


def zhihu_post_retry(args, title, fname, col_idx):
    for i in range(args.retry):
        try:
            with camou_create_driver(args.headless) as (browser, context, page):
                page.set_default_timeout(config['timeout'] * 1000)
                page.set_default_navigation_timeout(config['timeout'] * 1000)
                zhihu_post(
                    context, page, args.un, args.pw,
                    title, fname, col_idx,
                    args.retry,
                )
            break
        except Exception as ex:
            print(f'CSDN Post Retry #{i}: {ex}')


def zhihu_post(context, page, un, pw, title, fname, col_idx, retry=20):
    # 登录
    if path.isfile(config['cookie_fname']):
        print('导入Cookie')
        page.goto('https://zhihu.com')
        cookies = json.loads(open(config['cookie_fname'], encoding='utf8').read())
        context.add_cookies(normalise_cookies(cookies))
    print('打开登录页面')
    page.goto('https://www.zhihu.com/signin')
    print('等待页面加载')
    page.wait_for_load_state('domcontentloaded')
    print('页面加载完成')
    print('page.url', page.url)
    if page.url.startswith('https://www.zhihu.com/signin'):
        print('添加账号密码')
        js_click(page, config['selectPwTab'])
        page.locator(config['unText']).first.fill(un)
        page.locator(config['pwText']).first.fill(pw)
        print('登录')
        js_click(page, config['loginBtn'])
        print('等待登录后跳转')
        page.wait_for_url(
            lambda url: not url.startswith('https://www.zhihu.com/signin'),
            timeout=60000,
        )
        print('保存 COOKIE')
        cookies = context.cookies()
        open(config['cookie_fname'], 'w', encoding='utf8').write(
            json.dumps(normalise_cookies(cookies))
        )

    print('打开编辑器')
    page.goto('https://zhuanlan.zhihu.com/write')
    print('等待编辑器加载')
    page.wait_for_load_state('domcontentloaded')
    print('编辑器加载完成')
    print('page.url', page.url)

    print('填写标题')
    page.locator(config['titleText']).first.fill(title[:100])

    print('选择专栏')
    # el_col = page.locator(config['colRadio']).first
    # el_col.click()
    if col_idx != 0:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_selector(config['colRadio'])
        js_click(page, config['colRadio'])
        page.wait_for_selector(config['colCombo'])
        js_click(page, config['colCombo'])
        el =  config['colItem'].replace('{i}', str(col_idx))
        page.wait_for_selector(el)
        js_click(page, el)
    # el_gift = page.locator(config['giftRadio']).first
    # el_gift.click()

    print('声明 AI 创作')
    page.wait_for_selector(config['declCombo'])
    js_click(page, config['declCombo'])
    page.wait_for_selector(config['declItem'])
    js_click(page, config['declItem'])

    print('填写内容')

    js_click(page, config['alertBtn'], optional=True)

    page.locator(config['docBtn']).first.click()
    page.locator(config['impBtn']).first.click()
    page.locator(config['impFile']).first.set_input_files(fname)
    page.wait_for_timeout(10000)


    for i in range(retry):
        print(f'发布：{i}')
        page.wait_for_selector(
            config['pubBtnDis'], state='detached'
        )
        js_click(page, config['pubBtn'])
        print('等待消息提示')
        try:
            page.wait_for_url(
                lambda url: (
                    'edit' not in url and
                    'write' not in url
                ),
            )
            print('发布成功')
            break
        except:
            pass

        try:
            page.wait_for_selector(config['noticeBox'])
            page.wait_for_timeout(1000)
            notice = page.locator(config['noticeBox']).first.inner_text()
            print(notice)
        except Exception as ex:
            print(ex)

        time.sleep(1)


def main():

    parser = argparse.ArgumentParser(prog="GPTTestTrain", description="GPTTestTrain", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fname", help="MD fname")
    parser.add_argument("-u", "--un", default=os.environ.get('CSDN_USERNAME', ''), help="username")
    parser.add_argument("-p", "--pw", default=os.environ.get('CSDN_PASSWORD', ''), help="password")
    parser.add_argument("-c", "--cate", default='默认分类',  help="cate")
    parser.add_argument("-t", "--tags", default='默认标签',  help="tags")
    parser.add_argument("-r", "--retry", type=int, default=20,  help="retry")
    parser.add_argument("-H","--headless", action='store_true', help="hdls")
    parser.add_argument("-i","--col-idx", type=int, default=0, help="col idx")
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

    # page.maximize_window()  # Camoufox 窗口大小由 screen 参数控制
    for f in fnames:
        print(f)
        md = open(f, encoding='utf8').read()
        md = re.sub(r'!\[[^\]]*\]\(([^\)]+)\)', r'<\1>', md)
        open(f, 'w', encoding='utf8').write(md)
        title, pos = get_md_title(md)
        if not title:
            print(f'{f} MD 文件无标题')
            continue
        # body = md[pos[1]:]
        title = re.sub(r'[^\u0000-\uFFFF]', '', title)
        fname = path.abspath(f)
        zhihu_post_retry(args, title, fname, args.col_idx)
        os.remove(f)



if __name__ == '__main__':
    try:
        main()
    except:
        traceback.print_exc()