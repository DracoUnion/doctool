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
import itertools
import json
import os
import random
import re
import shutil
import subprocess as subp
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from difflib import SequenceMatcher
from urllib.parse import quote_plus

import requests
import tqdm
from pyquery import PyQuery as pq

try:
    import websocket
except ImportError:
    raise SystemExit('缺少 websocket-client 库：pip install websocket-client')

HOST = 'annas-archive.gl'

dft_hdr = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0',
    'Referer': f'https://{HOST}',
}


# ───────────────────────────── 通用小工具 ─────────────────────────────

def request_retry(method, url, retry=10, check_status=False, **kw):
    kw.setdefault('timeout', 10)
    for i in range(retry):
        try:
            r = requests.request(method, url, **kw)
            if check_status:
                r.raise_for_status()
            return r
        except KeyboardInterrupt as e:
            raise e
        except Exception as e:
            print(f'{url} retry {i}')
            if i == retry - 1:
                raise e


def fname_escape(name: str) -> str:
    return name.replace('\\', '＼') \
               .replace('/', '／') \
               .replace(':', '：') \
               .replace('*', '＊') \
               .replace('?', '？') \
               .replace('"', '＂') \
               .replace('<', '＜') \
               .replace('>', '＞') \
               .replace('|', '｜')


def to_kebab(name: str) -> str:
    """将标题转为 kebab-case slug。"""
    s = re.sub(r"[^\w\s\u4e00-\u9fff\-]", "", name)
    s = re.sub(r"[\s_]+", "-", s).strip("-").lower()
    return s[:60] or "unnamed"


# ─────────────────────────── Chrome CDP 封装 ───────────────────────────

class CdpError(RuntimeError):
    pass


class CdpConnection:
    """一个同步的 CDP WebSocket 连接（请求/响应按 id 配对）。"""

    def __init__(self, ws, timeout_ms=60_000):
        self.ws = ws
        self.timeout_ms = timeout_ms
        self._id_gen = itertools.count(1)
        self._lock = threading.Lock()

    @classmethod
    def connect(cls, url, timeout_ms=30_000):
        # timeout 同时作用于握手与 recv：recv 每 N 秒返回一次，便于外层按
        # 自己的 deadline 判断超时，而不是被一条永远等不到的消息卡死。
        ws = websocket.create_connection(url, timeout=15, origin=None)
        return cls(ws, timeout_ms=timeout_ms)

    def send(self, method, params=None, session_id=None, timeout_ms=None):
        msg_id = next(self._id_gen)
        payload = {'id': msg_id, 'method': method}
        if params is not None:
            payload['params'] = params
        if session_id:
            payload['sessionId'] = session_id
        timeout_ms = timeout_ms or self.timeout_ms
        with self._lock:
            self.ws.send(json.dumps(payload))
        deadline = time.time() + timeout_ms / 1000.0
        while True:
            if time.time() > deadline:
                raise TimeoutError(f'CDP 超时：{method}')
            try:
                data = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue  # recv 定时返回，检查 deadline
            except websocket.WebSocketConnectionClosedException as e:
                raise CdpError(f'CDP 连接已关闭：{e}')
            if data.get('id') == msg_id:
                if data.get('error'):
                    raise CdpError(
                        f'{method}: {data["error"].get("message", data["error"])}')
                return data.get('result', {})
            # id 不匹配的是事件通知，这里不订阅事件，直接丢弃

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


class CdpPage:
    """绑定到单个 Chrome tab 的 CDP 会话，等价于原 annas.py 的 page 对象。"""

    def __init__(self, cdp, session_id, target_id, proc=None, profile=None):
        self.cdp = cdp
        self.session_id = session_id
        self.target_id = target_id
        self.proc = proc          # Chrome 主进程（用于清理）
        self.profile = profile    # 临时 user-data-dir（用于清理）

    def send(self, method, params=None, timeout_ms=None):
        return self.cdp.send(method, params,
                             session_id=self.session_id, timeout_ms=timeout_ms)

    # ── 页面操作 ──

    def evaluate(self, expression, timeout_ms=15_000):
        res = self.send('Runtime.evaluate', {
            'expression': expression,
            'returnByValue': True,
        }, timeout_ms=timeout_ms)
        if res.get('exceptionDetails'):
            raise CdpError(f'Runtime.evaluate 异常：'
                           f'{json.dumps(res["exceptionDetails"], ensure_ascii=False)[:500]}')
        return res.get('result', {}).get('value')

    def html(self) -> str:
        """等价于 page.content()。"""
        return self.evaluate('document.documentElement.outerHTML')

    def goto(self, url, timeout_ms=60_000):
        self.send('Page.navigate', {'url': url})
        self.wait_ready(timeout_ms)

    def reload(self, timeout_ms=60_000):
        try:
            self.send('Page.reload', {'ignoreCache': True})
            self.wait_ready(timeout_ms)
        except CdpError:
            # 页面导航中/上下文销毁时 reload 会失败，交给后续 goto 兜底
            pass

    def wait_ready(self, timeout_ms=60_000):
        """等价于 wait_for_load_state('domcontentloaded')。"""
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            try:
                rs = self.evaluate('document.readyState')
            except Exception:
                time.sleep(0.2)
                continue
            if rs in ('interactive', 'complete'):
                return True
            time.sleep(0.2)
        return False

    def wait_for_selector(self, selector, timeout_ms=50_000):
        """轮询直到元素出现（如验证通过后页面关键选择器），等价于
        page.wait_for_selector(selector, timeout=50000)。"""
        expr = f'!!document.querySelector({json.dumps(selector)})'
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            try:
                if self.evaluate(expr):
                    return True
            except Exception:
                pass  # 页面正在跳转，继续轮询
            time.sleep(0.5)
        raise TimeoutError(f'等待选择器超时（{timeout_ms}ms）：{selector}')


# ─────────────────────────── Chrome 启动 / 清理 ───────────────────────────

def find_chrome_executable():
    override = os.environ.get('DL_ANNAS_CHROME', '').strip()
    if override and os.path.exists(override):
        return override
    candidates = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    for cmd in ('chrome', 'chromium', 'msedge'):
        p = shutil.which(cmd)
        if p:
            return p
    raise FileNotFoundError('未找到 Chrome/Edge，请设置 DL_ANNAS_CHROME 环境变量')


def _wait_for_port_file(profile, proc, timeout_ms):
    """--remote-debugging-port=0 时 Chrome 会把实际端口写入
    <user-data-dir>/DevToolsActivePort，读取第一行即为端口号。"""
    pf = os.path.join(profile, 'DevToolsActivePort')
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if proc.poll() is not None:
            raise CdpError(f'Chrome 意外退出，code={proc.returncode}')
        if os.path.exists(pf):
            try:
                with open(pf) as f:
                    return int(f.read().splitlines()[0].strip())
            except (ValueError, IndexError):
                pass
        time.sleep(0.15)
    raise TimeoutError(f'Chrome 调试端口未就绪（{timeout_ms}ms）')


def _wait_for_ws_url(port, timeout_ms):
    url = f'http://127.0.0.1:{port}/json/version'
    deadline = time.time() + timeout_ms / 1000.0
    last_err = None
    while time.time() < deadline:
        try:
            # 强制不走代理，localhost 无需代理
            r = requests.get(url, timeout=2, proxies={'http': None, 'https': None})
            data = r.json()
            if data.get('webSocketDebuggerUrl'):
                return data['webSocketDebuggerUrl']
        except Exception as e:
            last_err = e
        time.sleep(0.15)
    raise TimeoutError(f'Chrome CDP 端点未就绪：{last_err}')


def _kill_chrome_tree(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == 'nt':
            subp.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                     stdout=subp.DEVNULL, stderr=subp.DEVNULL)
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _launch_chrome(headless, timeout_ms=60_000):
    chrome = find_chrome_executable()
    profile = tempfile.mkdtemp(prefix='dl-annas-cdp-')
    args = [
        chrome,
        '--remote-debugging-port=0',          # 自动分配空闲端口，多实例不冲突
        f'--user-data-dir={profile}',          # 独立 profile，避免与已开的 Chrome 冲突
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-blink-features=AutomationControlled',
        '--disable-dev-shm-usage',
        '--window-size=1920,1080',
    ]
    if headless:
        args += ['--headless=new', '--disable-gpu']
    proc = subp.Popen(args, stdout=subp.DEVNULL, stderr=subp.DEVNULL)
    try:
        port = _wait_for_port_file(profile, proc, timeout_ms)
        ws_url = _wait_for_ws_url(port, timeout_ms)
        cdp = CdpConnection.connect(ws_url, timeout_ms=timeout_ms)
        page = _attach_page(cdp, proc, profile)
    except Exception:
        _kill_chrome_tree(proc)
        shutil.rmtree(profile, ignore_errors=True)
        raise
    return page


def _attach_page(cdp, proc, profile):
    target_id = cdp.send('Target.createTarget', {'url': 'about:blank'})['targetId']
    res = cdp.send('Target.attachToTarget', {'targetId': target_id, 'flatten': True})
    page = CdpPage(cdp, session_id=res['sessionId'], target_id=target_id,
                   proc=proc, profile=profile)
    page.send('Page.enable', timeout_ms=10_000)
    page.send('Runtime.enable', timeout_ms=10_000)
    page.send('DOM.enable', timeout_ms=10_000)
    page.send('Page.bringToFront', timeout_ms=10_000)
    return page


@contextmanager
def cdp_create_driver(headless=True, timeout_ms=60_000):
    """等价于 plrt_create_driver()，yield 一个 CdpPage，退出时杀掉 Chrome。"""
    page = _launch_chrome(headless, timeout_ms)
    try:
        yield page
    finally:
        page.cdp.close()
        _kill_chrome_tree(page.proc)
        # Chrome 释放 profile 文件是异步的，稍等片刻再清，清不掉也无妨
        for _ in range(10):
            try:
                shutil.rmtree(page.profile)
                break
            except Exception:
                time.sleep(0.3)


# ─────────────────────────── 原 annas.py 的逻辑（仅替换 driver） ───────────────────────────

def cdp_get_html(page, url: str, el_chk: str = None) -> str:
    """等价于 plrt_get_html()：导航访问页面，等待验证通过后返回 HTML。"""
    page.goto(url)
    if el_chk:
        # 最多等待 50 秒，比单纯等待 timeout 更智能
        page.wait_for_selector(el_chk, timeout_ms=50_000)
    return page.html()


def cdp_get_html_retry(page, url: str, el_chk: str = None, retry: int = 10) -> str:
    for i in range(retry):
        try:
            page.reload()
            return cdp_get_html(page, url, el_chk)
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
            html = cdp_get_html_retry(page, url, '.header-inner-top', args.retry)
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
        html = cdp_get_html_retry(page, url, '.text-gray-800', args.retry)
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
        html = cdp_get_html_retry(page, url, '.bg-gray-200', args.retry)
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
    dl_annas_parser.set_defaults(func=download_annas)

    annas_batch_parser = subparsers.add_parser("annas-batch", help="下载文件")
    annas_batch_parser.add_argument("flist", help="JSONL 列表文件")
    annas_batch_parser.add_argument("-t", "--threads", type=int, default=8, help="线程数")
    annas_batch_parser.add_argument("-s", "--site", default='annas',
                                    choices=['slow', 'bt', 'lgli'], help="站点")
    annas_batch_parser.add_argument("-st", "--start", type=int, default=0, help="起始")
    annas_batch_parser.add_argument("-r", "--retry", type=int, default=10, help="重试")
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
    args.func(args)


if __name__ == '__main__':
    main()