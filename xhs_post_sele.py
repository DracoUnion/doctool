import random
import traceback
import argparse
from os import path
import time
import re
import os
import json
from camoufox.sync_api import Camoufox
from BookerDownloadTool.util import *
from BookerMarkdownTool.util import get_md_title

config = {
    'selectPwTab': '.SignFlow-tab:last-of-type',
    'unText': 'input[placeholder="手机号或邮箱"]',
    'pwText': 'input[placeholder="密码"]',
    'loginBtn': '.JmYzaky7MEPMFcJDLNMG',
    'newBtn': '.new-btn',
    'titleText': 'textarea[placeholder="输入标题"]',
    'titleText2': 'textarea[placeholder="输入标题"] + textarea',
    'contText': 'div[contenteditable="true"]',
    'nextBtn': '.next-btn',
    'loadingCard': '.loading-card',
    'cusBtn': 'div.footer > .custom-button',
    'cusBtnDis': 'div.footer > .custom-button[disabled]',
    'tmplCard': '.template-card',
    'pubBtn': '.publishBtn',
    'pubBtn2': '.publish-page-publish-btn > button:last-of-type',
    'notice': '.d-toast-notice',
    'impWait': 5,
    'timeout': 15,
    'cookie_fname': 'xhs_cooklie.json',
}

def txt2html(body):
    return re.sub(r'^(.+?)$', r'<p>\1</p>', body, flags=re.M)

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


def xhs_post_retry(args, title, body):
    for i in range(args.retry):
        try:
            
            with camou_create_driver(args.headless) as (browser, context, page):
                page.set_default_timeout(config['timeout'] * 1000)
                page.set_default_navigation_timeout(config['timeout'] * 1000)
                xhs_post(
                    context, page, args.un, args.pw,
                    title, body,
                    args.retry,
                )
            break
        except Exception as ex:
            print(f'CSDN Post Retry #{i}: {ex}')


def xhs_post(context, page, un, pw, title, body, retry=20):
    # 登录
    if path.isfile(config['cookie_fname']):
        print('导入Cookie')
        page.goto('https://www.xiaohongshu.com/')
        cookies = json.loads(open(config['cookie_fname'], encoding='utf8').read())
        context.add_cookies(normalise_cookies(cookies))
    print('打开登录页面')
    page.goto('https://www.xiaohongshu.com/login')
    print('等待页面加载')
    page.wait_for_load_state('domcontentloaded')
    print('页面加载完成')
    print('page.url', page.url)
    if page.url.startswith('https://www.xiaohongshu.com/login'):
        print('等待登录后跳转')
        page.wait_for_url(
            lambda url: not url.startswith('https://www.xiaohongshu.com/login'),
            timeout=60000,
        )
        print('保存 COOKIE')
        cookies = context.cookies()
        open(config['cookie_fname'], 'w', encoding='utf8').write(
            json.dumps(normalise_cookies(cookies))
        )

    print('打开编辑器')
    page.goto('https://creator.xiaohongshu.com/publish/publish?source=official&from=menu&target=article')
    print('等待编辑器加载')
    page.wait_for_url(
        lambda url: 'publish' in url,
    )
    print('page.url', page.url)
    print('编辑器加载完成')


    print('填写标题')
    page.locator(config['newBtn']).first.click()
    page.wait_for_selector(config['titleText'])
    page.evaluate("""(sel, val) => {
        const el = document.querySelector(sel)
        el.value = val
        el.dispatchEvent(new Event('input', {bubbles: true}))
    }""", config['titleText'], title[:100])

    print('填写内容')

    html = md2html_pandoc(body)
    page.evaluate(
        "(sel, html) => { document.querySelector(sel).innerHTML = html }",
        config['contText'], html,
    )
    print('下一步')
    page.locator(config['nextBtn']).first.click()

    print('选择模版')
    page.wait_for_selector(
        config['loadingCard'], state='detached',
    )

    page.evaluate("""(sel) => {
        const els = document.querySelectorAll(sel)
        const idx = Math.floor(Math.random() * els.length)
        els[idx].click()
    }""", config['tmplCard'])

    print('下一步')
    page.wait_for_selector(
        config['cusBtnDis'], state='detached',
    )
    page.locator(config['cusBtn']).first.click()

    print('填写摘要')
    page.wait_for_selector(config['pubBtn2'])
    html = txt2html(body[:500])
    page.evaluate(
        "(sel, html) => { document.querySelector(sel).innerHTML = html }",
        config['contText'], html,
    )
    page.wait_for_timeout(1000)


    for i in range(retry):
        print(f'发布：{i}')
        page.locator(config['pubBtn2']).first.click()
        print('等待消息提示')
        try:
            page.wait_for_url(
                lambda url: (
                    'success' in url
                ),
            )
            print('发布成功')
            break
        except:
            pass

        try:
            notice = page.locator(config['notice']).first.inner_text()
            print(notice)
        except Exception as ex:
            print(ex)


        if i == retry - 1:
            raise Exception('发布失败')
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
        print('请提供小红书 TXT 文件或目录')
        return

    # page.maximize_window()  # Camoufox 窗口大小由 screen 参数控制
    for f in fnames:
        print(f)
        txt = open(f, encoding='utf8').read()
        m = re.search(r'\A\s*^(.+?)$', txt, flags=re.M)
        if not m:
            print(f'{f} TXT 文件无标题')
            return
        title = m.group(1)
        pos = m.span()[1]
        body = txt[pos:]
        xhs_post_retry(args, title, body)
        os.remove(f)



if __name__ == '__main__':
    try:
        main()
    except:
        traceback.print_exc()