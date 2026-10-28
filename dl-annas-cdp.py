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
import string

from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from urllib.parse import quote_plus

import cv2
import numpy as np
import ddddocr
import tqdm
from pyquery import PyQuery as pq
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

def preprocess_captcha(img_data):
    # 1. 读取图像
    img = cv2.imdecode(
        np.frombuffer(img_data, np.uint8),
        cv2.IMREAD_COLOR,
    )
    
    # 2. 裁剪边缘（去除可能存在的外边框干扰，建议按需留出 2px 边距）
    h, w = img.shape[:2]
    img_cropped = img[2:h-2, 2:w-2]

    # 3. 灰度化
    gray = cv2.cvtColor(img_cropped, cv2.COLOR_BGR2GRAY)

    # 4. 滤波降噪（中值滤波保护边缘）
    blurred = cv2.medianBlur(gray, 3)

    # 5. 自适应二值化（应对不均匀光照，抗干扰能力更强）
    # blockSize 可依据字符像素粗细在 11~31 间微调
    thresh = cv2.adaptiveThreshold(
        blurred, 255, 
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 15, 8
    )

    # 6. 形态学开运算（断开图中细小的红紫干扰线）
    kernel = np.ones((2, 2), np.uint8)
    processed = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    # 7. 编码为字节流供 ddddocr 使用
    is_success, buffer = cv2.imencode(".png", processed)
    if not is_success:
        return None
    return buffer.tobytes()

def recognize_captcha(img_data):
    # 初始化 OCR，开启新版模型并指定模型下载目录
    ocr = ddddocr.DdddOcr(old=False, show_ad=False)

    # 限定可能出现的字母数字范围（如纯小写字母或指定数字），减少同类字符误判
    # 例如：若目标只含字母和数字，可设为 "abcdefghijklmnopqrstuvwxyz0123456789"
    ocr.set_ranges(string.ascii_letters + string.digits)

    processed_bytes = preprocess_captcha(img_data)

    # 执行识别
    result = ocr.classification(processed_bytes)
    return result

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

def wait_for_captcha_clear(page: CdpPage, el_chk: str, timeout_ms=600_000):
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
    res = recognize_captcha(img_data)
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
                 ddos_timeout_ms=600_000, label='', headless=False) -> str:
    """导航页面，必要时等待用户完成 DDoS-Guard 人工验证。"""
    page.goto(url)
    while is_captcha_challenge(page, el_chk):
        wait_for_captcha_clear(page, el_chk, ddos_timeout_ms)
    if el_chk:
        page.wait_for_selector(el_chk)
    return page.html()


def cdp_get_html_retry(page: CdpPage, url: str, el_chk: str = None, retry: int = 10,
                       ddos_timeout_ms=600_000, label='', headless=False) -> str:
    for i in range(retry):
        try:
            return cdp_get_html(page, url, el_chk, ddos_timeout_ms, label, headless)
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
    with cdp_create_driver(args.headless) as page:
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
                                      args.ddos_timeout, f'search:{i}', args.headless)
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
    with cdp_create_driver(args.headless) as page:
        hash_ = args.hash
        url = f'https://{HOST}/md5/{hash_}'
        html = cdp_get_html_retry(page, url, '.text-gray-800', args.retry,
                                  args.ddos_timeout, f'md5:{hash_}', args.headless)
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
                                  args.ddos_timeout, f'slow:{hash_}', args.headless)
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

def reg_subparser(subparsers):
    dl_annas_parser = subparsers.add_parser("annas", help="下载文件")
    dl_annas_parser.add_argument("hash", help="文件哈希")
    dl_annas_parser.add_argument("-H", "--headless", action='store_true', help="无头模式")
    dl_annas_parser.add_argument("-r", "--retry", type=int, default=10, help="重试")
    dl_annas_parser.add_argument("--ddos-timeout", type=int, default=600,
                                 help="人工验证最长等待秒数")
    dl_annas_parser.set_defaults(func=download_annas)

    annas_batch_parser = subparsers.add_parser("annas-batch", help="下载文件")
    annas_batch_parser.add_argument("flist", help="JSONL 列表文件")
    annas_batch_parser.add_argument("-t", "--threads", type=int, default=8, help="线程数")
    annas_batch_parser.add_argument("-s", "--site", default='annas',
                                    choices=['slow', 'bt', 'lgli'], help="站点")
    annas_batch_parser.add_argument("-st", "--start", type=int, default=0, help="起始")
    annas_batch_parser.add_argument("-r", "--retry", type=int, default=10, help="重试")
    annas_batch_parser.add_argument("--ddos-timeout", type=int, default=600,
                                    help="人工验证最长等待秒数")
    annas_batch_parser.add_argument("-H", "--headless", action='store_true', help="无头模式")
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
    annas_fetch_parser.add_argument("-H", "--headless", action='store_true', help="无头模式")
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
    args.headless = getattr(args, 'headless', False)
    args.ddos_timeout = getattr(args, 'ddos_timeout', 600) * 1000
    args.func(args)


if __name__ == '__main__':
    main()
