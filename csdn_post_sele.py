import re
import traceback
import argparse
from os import path
import time
import os
import json
from camoufox import Camoufox
from camoufox.addons import DefaultAddons
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
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
    'multiPlatRadio': '#multiPlatformPublishNo',
    'timeout': 15,
    'cookie_fname': 'csdn_cookie.json',
}


def _clean_cookie(raw):
    """把 Selenium/JSON 格式的 cookie 转成 Playwright 可接受的格式。"""
    key_map = {'expiry': 'expires'}
    out = {'path': '/'}
    valid_keys = {'name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite'}
    for k, v in raw.items():
        key = key_map.get(k, k)
        if key in valid_keys:
            out[key] = v
    if out.get('sameSite') not in ('Strict', 'Lax', 'None'):
        out.pop('sameSite', None)
    return out

def csdn_post_retry(args, title, body):
    with camou_create_driver(args.headless) as (browser, context, page):
        page.set_default_timeout(config['timeout'] * 1000)
        page.set_default_navigation_timeout(config['timeout'] * 1000)
        for i in range(args.retry):
            try:
                csdn_post(
                    context, page,
                    args.un, args.pw,
                    title, body,
                    args.cate, args.tags.split(','),
                    args.retry
                )
                break
            except Exception as ex:
                print(f'CSDN Post Retry #{i}: {traceback.format_exc()}')
                if i == args.retry - 1:
                    raise ex


def csdn_post(context, page, un, pw, title, body, cate='默认分类', tags=[], retry=20):
    # 登录
    if path.isfile(config['cookie_fname']):
        print('导入Cookie')
        page.goto('https://csdn.net')
        cookies = json.loads(open(config['cookie_fname'], encoding='utf8').read())
        cookies = [_clean_cookie(c) for c in cookies]
        print(cookies)
        context.add_cookies(cookies)

    print('打开登录页面')
    page.goto('https://passport.csdn.net/login')
    print('等待页面加载')
    page.wait_for_load_state('networkidle')
    print('页面加载完成')
    print('page.url', page.url)
    if page.url.startswith('https://passport.csdn.net'):
        print('添加账号密码')
        page.locator(config['selectPwTab']).click()
        page.locator(config['unBtn']).fill(un)
        page.locator(config['pwBtn']).fill(pw)
        print('登录')
        page.locator(config['loginBtn']).click()
        print('等待登录后跳转')
        page.wait_for_function(
            '() => !location.href.startsWith("https://passport.csdn.net")',
            timeout=60000
        )
        print('保存 COOKIE')
        cookies = context.cookies()
        open(config['cookie_fname'], 'w', encoding='utf8').write(json.dumps(cookies))

    print('打开编辑器')
    page.goto('https://editor.csdn.net/md/')
    print('等待编辑器加载')
    page.wait_for_load_state('networkidle')
    print('编辑器加载完成')
    print('page.url', page.url)
    print('填写标题内容')
    page.locator(config['titleText']).evaluate(
        '''(el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }''', 
        title[:100]
    )

    # body：直接设置 textContent，避免在富文本框中逐字输入
    page.locator(config['bodyText']).evaluate(
        '(el, value) => el.textContent = value',
        body
    )

    print('点击发布按钮')
    page.locator(config['postButton']).click()
    print('等待发布对话框')
    page.wait_for_selector(config['pubPanel'], state='visible')
    print('发布对话框已加载')
    print('关闭多平台发布')
    page.locator(config['multiPlatRadio']).evaluate('el => el.click()')
    print('点击标签按钮')
    page.locator(config['tagButton']).click()
    print('等待标签对话框')
    page.wait_for_selector(config['tagPanel'], state='visible')
    print('标签对话框已加载')
    print('设置标签')
    el_tag_text = page.locator(config['tagText'])
    for t in tags:
        el_tag_text.fill(t)
        el_tag_text.press('Enter')
        el_tag_text.fill('')
    page.locator(config['tagCloseButton']).click()

    print('删除已有类别')
    for el in page.query_selector_all(config['cateDelBtn']):
        page.evaluate('el => el.click()', el)
    if page.locator(config['cateText']).count() == 0:
        print('点击类别按钮')
        page.locator(config['cateBtn']).click()
        print('等待类别文本框')
        page.wait_for_selector(config['cateText'], state='visible')
    print('类别文本框已加载')
    print('设置类别')
    page.locator(config['cateText']).fill(cate)
    page.locator(config['cateCloseBtn']).click()
    for i in range(retry):
        print(f'发布：{i}')
        page.locator(config['pubBtn']).click()
        print('等待消息提示')
        notice_el = page.wait_for_selector(config['noticeBox'], state='visible')
        page.wait_for_timeout(1000)
        notice = notice_el.text_content()
        print('消息：', notice)
        if '文章标签' in notice:
            raise RuntimeError('请设置文章标签')
        if '成功' in notice or '加载中' in notice:
            print('等待成功页面')
            page.wait_for_function(
                '() => location.href.includes("/success/")',
                timeout=config['timeout'] * 1000
            )
            print('发布成功')
            break

        if i == retry - 1:
            raise Exception('发布失败')
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(prog="GPTTestTrain", description="GPTTestTrain", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fname", help="MD fname")
    parser.add_argument("-u", "--un", default=os.environ.get('CSDN_USERNAME', ''), help="username")
    parser.add_argument("-p", "--pw", default=os.environ.get('CSDN_PASSWORD', ''), help="password")
    parser.add_argument("-c", "--cate", default='默认分类', help="cate")
    parser.add_argument("-t", "--tags", default='默认标签', help="tags")
    parser.add_argument("-r", "--retry", type=int, default=20, help="retry")
    parser.add_argument("-H", "--headless", action='store_true', help="hdls")
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

    for f in fnames:
        print(f)
        md = open(f, encoding='utf8').read()
        md = re.sub(r'!\[[^\]]*\]\(([^\)]+)\)', r'<\1>', md)
        title, pos = get_md_title(md)
        if not title:
            print(f'{f} MD 文件无标题')
            return
        if len(title) < 5:
            title *= 5
        body = md[pos[1]:]
        csdn_post_retry(args, title, body)
        os.remove(f)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
