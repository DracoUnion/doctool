# -*- coding: utf-8 -*-
"""dl-annas-cdp.py — annas-archive 下载器（Chrome CDP 版）。

将 annas.py 里的 Playwright 依赖全部移除，改为通过 Chrome DevTools
Protocol（CDP）驱动真实的 Chrome：脚本自己拉起一个带调试端口的 Chrome，
用 WebSocket 连接 CDP 端点，完成导航 / 等待验证通过 / 抓取 HTML，
等价于原 plrt_get_html() / plrt_get_html_retry()。

子命令与原 annas.py 保持一致：

    python dl-annas-cdp.py annas <hash> [-H] [-r 10]        # 单文件下载
    python dl-annas-cdp.py annas-batch list.jsonl [-t 8]    # 批量
    python dl-annas-cdp.py annas-fetch kw out.jsonl ...     # 抓取搜索列表
    python dl-annas-cdp.py annas-dedup list.jsonl [-s 0.8]  # 去重

找不到 Chrome 时用 DL_ANNAS_CHROME 环境变量指定 chrome.exe 路径。
"""
import argparse
import copy
import json
import os
import random
import re
import subprocess as subp
import base64
import sys
import time
import traceback

from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from urllib.parse import quote_plus

import tqdm
from pyquery import PyQuery as pq
from BookerDownloadTool.openai import OpenAIClient
from BookerDownloadTool.util import to_kebab, request_retry, fname_escape
from BookerDownloadTool.cdp import cdp_create_driver, CdpPage

HOST = 'annas-archive.gl'

dft_hdr = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0',
    'Referer': f'https://{HOST}',
}

selectors = {
    'captcha_iframe': 'iframe#ddg-iframe',
    'captcha_div': 'div.ddg-captcha',
    'captcha_cb': 'div.ddg-captcha__checkbox',
    'captcha_img': 'img.ddg-modal__captcha-image',
    'captcha_btn': 'button.ddg-modal__submit',
    'captcha_tb': 'input.ddg-modal__input',
    'captcha_load_img': 'img#ddg-img-loading',
}

_DDOS_DETECT_JS = """(() => {
    const title = (document.title || '').toLowerCase();
    const path = ((location.host || '') + (location.pathname || '')).toLowerCase();
    return title.includes('ddos-guard') || path.includes('ddos-guard') ||
           !!document.querySelector('#ddg-captcha, #ddg-iframe, #request-info');
})()"""

CAPTCHA_OCR_PROMPT = (
    '请识别这张验证码图片中的字符，可能包含大小写字母和数字，'
    '可能有少量干扰线/噪点，请忽略它们。'
    '直接输出识别到的字符序列，不要加引号、空格或任何解释。'
)

def build_vlm_args(args):
    """构造 call_vlm_retry 需要的参数 Namespace（缺失字段给默认值）。"""
    return argparse.Namespace(
        retry=getattr(args, 'retry', 5),
        temp=getattr(args, 'temp', 0.1),
        top_p=getattr(args, 'top_p', None),
        frequency_penalty=getattr(args, 'frequency_penalty', None),
        presence_penalty=getattr(args, 'presence_penalty', None),
        max_tokens=getattr(args, 'max_tokens', None),
        extra_body=getattr(args, 'extra_body', ''),
    )

def recognize_captcha(img_data, args):
    """调用大模型视觉接口识别验证码图片。"""
    vmodel = getattr(args, 'vmodel', None) or os.environ.get('OPENAI_VIS_MODEL', '')
    if not vmodel:
        raise ValueError(
            '未配置视觉模型：请设置 OPENAI_VIS_MODEL 环境变量，'
            '或在命令行用 -vm/--vmodel 指定'
        )
    client = OpenAIClient(
        api_key=getattr(args, 'key', None) or os.environ.get('OPENAI_API_KEY'),
        base_url=getattr(args, 'host', None) or os.environ.get('OPENAI_BASE_URL'),
    )
    return client.call_vlm_retry(
        img_data, CAPTCHA_OCR_PROMPT, vmodel, build_vlm_args(args),
        parse_output=lambda s: re.sub(r'[^0-9A-Za-z]', '', s.strip()),
    )

def is_captcha_challenge(page: CdpPage, el_chk: str):
    page.wait_for_selector(selectors['captcha_iframe'] + ', ' + el_chk)
    return bool(page.evaluate(_DDOS_DETECT_JS))


def wait_for_captcha_img(page: CdpPage):
    while True:
        img_url = page.evaluate(f'''
            (() => {{
                const iframe = document.querySelector("{selectors['captcha_iframe']}");
                const innerDoc = iframe.contentDocument || iframe.contentWindow.document;
                return innerDoc.querySelector("{selectors["captcha_img"]}").src;
            }})()
        ''')
        if img_url.startswith('data:'):
            return img_url
        time.sleep(0.5)

def wait_for_captcha_clear(page: CdpPage, el_chk: str, timeout_ms=600_000, args=None):
    """等待用户在可见 Chrome 窗口中完成人工验证。"""
    # self.send('Page.bringToFront', timeout_ms=10_000)
    print(f'等待验证码模块加载...')
    page.wait_for_iframe_selector(
        selectors['captcha_iframe'], 
        selectors['captcha_div'],
    )
    time.sleep(1)
    print(f'点击人机验证按钮...')
    page.evaluate(f'''
        (() => {{
            const iframe = document.querySelector("{selectors['captcha_iframe']}");
            const innerDoc = iframe.contentDocument || iframe.contentWindow.document;
            innerDoc.querySelector("{selectors["captcha_div"]}").click();
        }})()
    ''')
    time.sleep(1)
    print(f'等待验证码图片加载...')
    page.wait_for_iframe_selector(
        selectors['captcha_iframe'], 
        selectors['captcha_img'],
    )
    img_url = wait_for_captcha_img(page)
    print('img_url: ' + img_url[:50] + '...')
    img_data = img_url[len('data:image/png;base64,'):]
    img_data = base64.b64decode(img_data)
    res = recognize_captcha(img_data, args)
    print(f'识别结果：{res}')
    print('提交验证码...')
    page.evaluate(f'''
        (() => {{
            const iframe = document.querySelector("{selectors['captcha_iframe']}");
            const innerDoc = iframe.contentDocument || iframe.contentWindow.document;
            innerDoc.querySelector("{selectors["captcha_tb"]}").value = {json.dumps(res)};
            innerDoc.querySelector("{selectors["captcha_btn"]}").click();
        }})()
    ''')
    time.sleep(3)
    page.reload()





# ─────────────────────────── 原 annas.py 的逻辑（仅替换 driver） ───────────────────────────

def cdp_get_html(page: CdpPage, url: str, el_chk: str = None,
                 ddos_timeout_ms=600_000, label='', headless=False,
                 args=None) -> str:
    """导航页面，必要时等待用户完成 DDoS-Guard 人工验证。"""
    page.goto(url)
    while is_captcha_challenge(page, el_chk):
        wait_for_captcha_clear(page, el_chk, ddos_timeout_ms, args)
    if el_chk:
        page.wait_for_selector(el_chk)
    return page.html()


def cdp_get_html_retry(page: CdpPage, url: str, el_chk: str = None, retry: int = 10,
                       ddos_timeout_ms=600_000, label='', headless=False,
                       args=None) -> str:
    for i in range(retry):
        try:
            return cdp_get_html(page, url, el_chk, ddos_timeout_ms, label, headless, args)
        except KeyboardInterrupt:
            raise
        except Exception:
            print(f'cdp_get_html retry #{i + 1}')
            traceback.print_exc()
            if i == retry - 1:
                raise


def tr_download_safe(args):
    try:
        download_annas(args)
    except KeyboardInterrupt:
        raise
    except Exception:
        traceback.print_exc()


def annas_batch(args):
    if not args.flist.endswith('.jsonl'):
        print('请提供 JSONL 文件')
        return

    pool = ThreadPoolExecutor(args.threads)
    hdls = []
    lines = open(args.flist, encoding='utf8').read().split('\n')
    lines = [l for l in lines if l.strip()]
    for l in lines[args.start:]:
        j = json.loads(l)
        args = copy.deepcopy(args)
        args.hash = j['hash']
        h = pool.submit(tr_download_safe, args)
        hdls.append(h)
        if len(hdls) > args.threads:
            for h in hdls:
                h.result()
            hdls = []

    for h in hdls:
        h.result()


def annas_fetch(args):
    # https://annas-archive.gl/search
    # ?index=&page=1&sort=newest&content=book_nonfiction
    # &content=book_unknown&ext=pdf&ext=epub&lang=en&display=&q=tarot
    with cdp_create_driver(not args.no_headless) as page:
        f = open(args.ofname, 'a', encoding='utf8')
        qry_ext = ''.join(f'&ext={e}' for e in args.ext)
        qry_cont = ''.join(f'&content={c}' for c in args.content)
        qry_lang = ''.join(f'&lang={l}' for l in args.lang)
        qry_yr = f'&termtype_1=year&termval_1={args.year}' if args.year else ''
        for i in range(args.start, args.end + 1):
            url = (
                f'https://{HOST}/search' +
                f'?page={i}&sort={args.sort}&q={quote_plus(args.query)}' +
                f'{qry_ext}{qry_cont}{qry_lang}{qry_yr}'
            )
            print(url)
            html = cdp_get_html_retry(page, url, '.header-inner-top', args.retry,
                                      args.ddos_timeout, f'search:{i}', not args.no_headless, args)
            rt = pq(html)
            el_links = rt.find('a.text-lg[href^="/md5/"]')
            if not el_links:
                break
            for el in el_links:
                el = pq(el)
                hash_ = el.attr('href').replace('/md5/', '')
                title = el.text().strip()
                print(f'title: {title}, hash: {hash_}')
                f.write(json.dumps({
                    'title': title,
                    'hash': hash_,
                    'slug': to_kebab(title)
                }) + '\n')
                f.flush()
        f.close()


def download_annas(args):
    with cdp_create_driver(not args.no_headless) as page:
        hash_ = args.hash
        url = f'https://{HOST}/md5/{hash_}'
        html = cdp_get_html_retry(page, url, '.text-gray-800', args.retry,
                                  args.ddos_timeout, f'md5:{hash_}', not args.no_headless, args)
        rt = pq(html)
        title = rt.find('div.font-semibold:nth-child(4)') \
            .text().strip().replace(' 🔍', '')
        ext = rt.find('.text-gray-800').text().split(' · ')[1].lower()
        fname = fname_escape(f'{title[:200]}.{ext}')
        fname_bak = fname_escape(f'{fname}.bak')
        skip_fname = re.sub(r'\.\w+$', '', fname) + '.skip'
        if os.path.isfile(fname) or os.path.isfile(skip_fname):
            print(f'{fname} 已存在')
            return
        print(f'fname: {fname}')

        el_links_li = rt('#md5-panel-downloads > div:nth-child(2) li.list-disc') \
            .filter(lambda i, el: 'no waitlist' in pq(el).text())
        if not el_links_li:
            print(f'{fname} 未找到下载链接')
            return

        url = pq(random.choice(el_links_li)).children('a').attr('href')
        url = f'https://{HOST}{url}'
        # url = f'https://{HOST}/slow_download/{hash_}/0/{idx}'
        html = cdp_get_html_retry(page, url, '.bg-gray-200', args.retry,
                                  args.ddos_timeout, f'slow:{hash_}', not args.no_headless, args)
        rt = pq(html)
        link = rt.find('.bg-gray-200').eq(0).text().strip()
        r = request_retry('GET', link, headers=dft_hdr, stream=True,
                          timeout=(60, 600))
        r.raise_for_status()
        fsize = int(r.headers['Content-Length'])
        chunk_size = 8192
        num_chunks = (fsize + chunk_size - 1) // chunk_size
        with open(fname_bak, 'wb') as f:
            for data in tqdm.tqdm(
                r.iter_content(chunk_size),
                total=num_chunks,
            ):
                f.write(data)
                f.flush()
        os.rename(fname_bak, fname)


def annas_dedup(args):
    if not args.flist.endswith('.jsonl'):
        print('请提供 JSONL 文件')
        return
    li = open(args.flist, encoding='utf8').read().split('\n')
    li = [l for l in li if l.strip()]
    li = [json.loads(it) for it in li]

    norm = lambda s: s.split(':')[0].split('：')[0]
    calc_sim = lambda s1, s2: SequenceMatcher(None, s1, s2).ratio()
    kept_name = []
    kept = []
    for it in li:
        name = norm(it['title'])
        print(name)
        if any(calc_sim(name, k) >= args.sim for k in kept_name):
            continue
        kept_name.append(name)
        kept.append(it)

    li = [json.dumps(it) for it in kept]
    open(args.flist, 'w', encoding='utf8').write('\n'.join(li))
    print('done...')


# ─────────────────────────── CLI ───────────────────────────

def add_vlm_args(parser):
    """验证码识别（大模型视觉）相关参数。"""
    parser.add_argument("--key", default=None, help="OpenAI API Key（默认取 OPENAI_API_KEY）")
    parser.add_argument("--host", default=None, help="API 地址（默认取 OPENAI_BASE_URL）")
    parser.add_argument("-vm", "--vmodel", default=None,
                        help="视觉模型名称（默认取 OPENAI_VIS_MODEL）")


def reg_subparser(subparsers):
    dl_annas_parser = subparsers.add_parser("annas", help="下载文件")
    dl_annas_parser.add_argument("hash", help="文件哈希")
    dl_annas_parser.add_argument("-H", "--no_headless", action='store_true', help="有头模式")
    dl_annas_parser.add_argument("-r", "--retry", type=int, default=10, help="重试")
    dl_annas_parser.add_argument("--ddos-timeout", type=int, default=600,
                                 help="人工验证最长等待秒数")
    add_vlm_args(dl_annas_parser)
    dl_annas_parser.set_defaults(func=download_annas)

    annas_batch_parser = subparsers.add_parser("annas-batch", help="下载文件")
    annas_batch_parser.add_argument("flist", help="JSONL 列表文件")
    annas_batch_parser.add_argument("-t", "--threads", type=int, default=4, help="线程数")
    annas_batch_parser.add_argument("-s", "--site", default='annas',
                                    choices=['slow', 'bt', 'lgli'], help="站点")
    annas_batch_parser.add_argument("-st", "--start", type=int, default=0, help="起始")
    annas_batch_parser.add_argument("-r", "--retry", type=int, default=10, help="重试")
    annas_batch_parser.add_argument("--ddos-timeout", type=int, default=600,
                                    help="人工验证最长等待秒数")
    annas_batch_parser.add_argument("-H", "--no_headless", action='store_true', help="有头模式")
    add_vlm_args(annas_batch_parser)
    annas_batch_parser.set_defaults(func=annas_batch)

    annas_fetch_parser = subparsers.add_parser("annas-fetch", help="抓取搜索列表")
    annas_fetch_parser.add_argument("-st", "--start", type=int, default=1, help="起始页")
    annas_fetch_parser.add_argument("query", help="查询关键词")
    annas_fetch_parser.add_argument("ofname", help="输出文件名")
    annas_fetch_parser.add_argument("-ed", "--end", type=int, default=1_000_000,
                                    help="结束页码")
    annas_fetch_parser.add_argument("-sr", "--sort", default='newest', help="排序方式")
    annas_fetch_parser.add_argument("-c", "--content", default=[], nargs='+', help="内容")
    annas_fetch_parser.add_argument("-l", "--lang", default=[], nargs='+', help="语言")
    annas_fetch_parser.add_argument("-x", "--ext", default=[], nargs='+', help="扩展名")
    annas_fetch_parser.add_argument("-r", "--retry", type=int, default=10, help="重试")
    annas_fetch_parser.add_argument("--ddos-timeout", type=int, default=600,
                                    help="人工验证最长等待秒数")
    annas_fetch_parser.add_argument("-y", "--year", type=int, help="年份")
    annas_fetch_parser.add_argument("-H", "--no_headless", action='store_true', help="有头模式")
    add_vlm_args(annas_fetch_parser)
    annas_fetch_parser.set_defaults(func=annas_fetch)

    annas_dedup_parser = subparsers.add_parser("annas-dedup", help="去重文件")
    annas_dedup_parser.add_argument("flist", help="JSONL 列表文件")
    annas_dedup_parser.add_argument("-s", "--sim", type=float, default=0.8, help="相似度")
    annas_dedup_parser.set_defaults(func=annas_dedup)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(prog='dl-annas-cdp',
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    reg_subparser(subparsers)
    args = parser.parse_args()
    args.no_headless = getattr(args, 'no_headless', False)
    args.ddos_timeout = getattr(args, 'ddos_timeout', 600) * 1000
    args.func(args)


if __name__ == '__main__':
    main()