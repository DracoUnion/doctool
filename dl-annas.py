import traceback
import tqdm
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import shutil
import os
import argparse
import re
import json
from BookerDownloadTool.util import request_retry, fname_escape
from BookerGptTool.util import to_kebab
import bencode
import copy
import subprocess as subp
from pyquery import PyQuery as pq
import random
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

lock = Lock()

HOST = 'annas-archive.gl'

PATCH_ENV_JS = '''
const patch = () => {
  // 1. webdriver标记（最核心）
  Object.defineProperty(navigator, 'webdriver', {
    get: () => false,
  });

  // 2. plugins列表（真实浏览器有2–5个，Headless为0）
  const mockPlugins = [
    { name: "Chrome PDF Plugin", filename: "internal-pdf-viewer" },
    { name: "Chrome PDF Viewer", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai" }
  ];
  Object.defineProperty(navigator, 'plugins', {
    get: () => mockPlugins,
  });

  // 3. mimeTypes（必须与plugins数量一致）
  const mockMimeTypes = [
    { type: "application/pdf", suffixes: "pdf", description: "" }
  ];
  Object.defineProperty(navigator, 'mimeTypes', {
    get: () => mockMimeTypes,
  });

  // 4. 外部窗口尺寸（需与实际屏幕匹配，否则触发二次验证）
  const screenWidth = window.screen.width;
  const screenHeight = window.screen.height;
  Object.defineProperty(window, 'outerWidth', {
    get: () => screenWidth,
  });
  Object.defineProperty(window, 'outerHeight', {
    get: () => screenHeight,
  });

  // 5. documentMode（IE遗留，但Cloudflare仍检查）
  Object.defineProperty(document, 'documentMode', {
    get: () => undefined,
  });

  // 6. chrome对象（Headless Chrome无此对象）
  window.chrome = { runtime: {} };
};

// 确保在所有上下文执行
if (typeof window !== 'undefined') {
  patch();
} else if (typeof self !== 'undefined') {
  self.patch = patch;
  self.patch();
}
'''
 
MOCK_WASM_JS = '''
const wasmBytes = new Uint8Array([
  0x00, 0x61, 0x73, 0x6d, // magic header
  0x01, 0x00, 0x00, 0x00, // version
  // ... 省略具体字节，实际需生成合法WASM二进制
]);
const wasmModule = new WebAssembly.Module(wasmBytes);
const wasmInstance = new WebAssembly.Instance(wasmModule);

// 模拟原模块的导出函数
wasmInstance.exports._calculate_hash = (input_ptr, input_len, output_ptr) => {
  // 输入是内存地址，需从wasm memory中读取
  const memory = wasmInstance.exports.memory;
  const inputArray = new Uint8Array(memory.buffer, input_ptr, input_len);
  const inputStr = new TextDecoder().decode(inputArray);
  
  // 执行JS版SHA256（使用crypto.subtle或第三方库）
  const hashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(inputStr));
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  
  // 写回output_ptr指向的内存
  const outputArray = new Uint8Array(memory.buffer, output_ptr, 32);
  outputArray.set(hashArray);
};
'''

dft_hdr = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0',
    'Referer': f'https://{HOST}',
}

def plrt_new_context(browser):
    context =  browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width":1920,"height":1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai"
        )
    context.add_init_script(PATCH_ENV_JS)
    context.add_init_script(MOCK_WASM_JS)
    return context

def plrt_new_browser(plrt, headless=True):
    return plrt.chromium.launch(
        headless=headless,
        args=[
            # 禁用AutomationControlled自动化标记（Chrome94+核心参数）
            "--disable-blink-features=AutomationControlled", 
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            # 模拟真人最大化打开浏览器
            "--start-maximized",
        ],
    )

def plrt_get_html(page, url: str, el_chk: str = None) -> str:
    """
    使用 Playwright 启动浏览器，访问页面，等待验证通过后获取 Cookies。
    """  
    # 2. 访问目标网站，等待网络空闲，让验证有机会完成
    page.goto(url)
    page.wait_for_load_state("networkidle")
    
    # 3. 尝试等待关键的 el_chk ，最多等待 20 秒
    #    这比单纯等待timeout更智能
    if el_chk:
        page.wait_for_selector(el_chk, timeout=50000)
    # 4. 获取HTML并关闭浏览器
    html = page.content()
    return html

def get_bt_idx(bt_data, fname):
    bt = bencode.bdecode(bt_data)
    for idx, f in enumerate(bt['info']['files']):
        if fname in f['path']:
            return idx
    return -1

def tr_download_safe(args):
    try:
        dl_func = (
            download_bt if args.site == 'bt' else 
            download_lgli if args.site == 'lgli' else
            download_slow
        )
        dl_func(args)
    except:
        traceback.print_exc()


def batch(args):
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
            for h in hdls: h.result()
            hdls = []

    for h in hdls: 
        h.result()

def fetch(args):
    # https://annas-archive.gl/search
    # ?index=&page=1&sort=newest&content=book_nonfiction
    # &content=book_unknown&ext=pdf&ext=epub&lang=en&display=&q=tarot
    with sync_playwright() as p:
        browser = plrt_new_browser(p, args.headless)
        context = plrt_new_context(browser)
        page = context.new_page()
    
        f = open(args.ofname, 'a', encoding='utf8')
        qry_ext = ''.join(f'&ext={e}' for e in args.ext)
        qry_cont = ''.join(f'&content={c}' for c in args.content)
        qry_lang = ''.join(f'&lang={l}' for l in args.lang)
        for i in range(args.start, args.end + 1):
            url = (
                f'https://{HOST}/search' + 
                f'?page={i}&sort={args.sort}&q={quote_plus(args.query)}' + 
                f'{qry_ext}{qry_cont}{qry_lang}'
            )
            print(url)
            for _ in range(args.retry):
                html = plrt_get_html(page, url, '.header-inner-top')
                rt = pq(html)
                el_links = rt.find('a.text-lg[href^="/md5/"]')
                if el_links: break
            if not el_links: break
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
        browser.close()
    
def download_lgli(args):
    url = f'https://libgen.li/ads.php?md5={args.hash}'
    print(url)
    html = request_retry('GET', url, headers=dft_hdr).text
    # print(html)
    rt = pq(html)
    msg = rt.find('.alert-danger').text()
    if msg:
        print(f'{args.hash} 下载失败：{msg}')
        return
    info = rt.find('#bibtext').text()
    m = re.search(r'title\x20=\x20+\{(.+?)\}', info)
    if not m:
        print('标题获取失败')
        return
    title = m.group(1)
    link = rt.find('a[href^=get]').attr('href')
    link = f'https://libgen.li/{link}'
    r = request_retry('GET', link, headers=dft_hdr, stream=True)
    ext = r.headers['Content-Disposition']
    ext = re.search(r'filename="(.+?)"', ext).group(1).split('.')[-1]
    fsize = int(r.headers['Content-Length'])
    fname = fname_escape(f'{title}.{ext}')
    fname_bak = fname_escape(f'{fname}.bak')
    if os.path.isfile(fname):
        print(f'{fname} 已存在')
        return
    print(fname)
    chunk_size = 8192
    num_chunks = (fsize + chunk_size - 1) // chunk_size 
    with open(fname_bak, 'wb') as f:
        for data in tqdm.tqdm(
            r.iter_content(chunk_size),
            total=num_chunks,
            unit='chunk', 
        ):
            f.write(data)
            f.flush()
    os.rename(fname_bak, fname)

def download_slow(args):
    with sync_playwright() as p:
        browser = plrt_new_browser(p, args.headless)
        context = plrt_new_context(browser)
        page = context.new_page()

        hash_ = args.hash
        url = f'https://{HOST}/md5/{hash_}'
        # html = request_retry('GET', url).text
        html = plrt_get_html(page, url, '.text-gray-800')
        rt = pq(html)
        title = rt.find('div.font-semibold:nth-child(4)') \
            .text().strip().replace(' 🔍', '')
        ext = rt.find('.text-gray-800').text().split(' · ')[1].lower()
        fname = fname_escape(f'{title[:200]}.{ext}')
        fname_bak = fname_escape(f'{fname}.bak')
        if os.path.isfile(fname):
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
        html = plrt_get_html(page, url, '.bg-gray-200')
        rt = pq(html)
        link = rt.find('.bg-gray-200').text().strip()
        r = request_retry('GET', link, headers=dft_hdr, stream=True)
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
        browser.close()

    


def download_bt(args):
    hash_ = args.hash
    url = f'https://{HOST}/md5/{hash_}'
    html = request_retry('GET', url).text
    rt = pq(html)
    bt_link = rt.find('div.text-gray-500:nth-child(2) > a:nth-child(2)').attr('href')
    bt_link = f'https://{HOST}{bt_link}'
    bt_desc = rt.find('div.text-gray-500:nth-child(2)').text()
    title = fname_escape(rt.find('div.font-semibold:nth-child(4)').text().strip().replace(' 🔍', ''))
    bt_sub_fname = re.search(r'file “(.+?)”', bt_desc).group(1)
    bt_fname = f'{hash_}.torrent'
    ext = rt.find('.text-gray-800').text().split(' · ')[1].lower()
    fname = title + '.' + ext
    if os.path.isfile(fname):
        print(f'{fname} 已存在')
        return
    print(f'fname: {fname}')
    print(f'bt_fname: {bt_fname}')
    print(f'bt_link: {bt_link}')
    print(f'bt_sub_fname: {bt_sub_fname}')

    bt_data = request_retry('GET', bt_link).content
    bt_idx = get_bt_idx(bt_data, bt_sub_fname)
    if bt_idx == -1:
        raise ValueError('BT 种子内未找到文件')
    print(f'bt_idx: {bt_idx}')
    open(bt_fname, 'wb').write(bt_data)

    cmd = [
        'aria2c', bt_fname, 
        '--file-allocation=none',  
        '--seed-time=0',
        '--allow-overwrite=true',
        f'--select-file={bt_idx+1}',
        f'--index-out={bt_idx+1}={hash_}',
        '--bt-tracker-timeout=30', 
        '--bt-tracker-connect-timeout=15',
        '--max-tries=5',
        '--retry-wait=5',
    ]
    subp.run(cmd, shell=True).check_returncode()
    os.rename(hash_, fname)
    bt_name = bencode.bdecode(bt_data)['info']['name']
    shutil.rmtree(bt_name)
    os.remove(bt_name + '.aria2')
    # aria2_fname = [f for f in os.listdir() if f.endswith('.aria2')]
    # for f in aria2_fname: os.remove(f)

def dedup(args):
    if not args.flist.endswith('.jsonl'):
        print('请提供 JSONL 文件')
        return
    li = open(args.flist, encoding='utf8').read().split('\n')
    li = [l for l in li if l.strip()]
    li = [json.loads(it) for it in li]
    slug_file_map = {
        it['slug']:it
        for it in li
    }
    li = list(slug_file_map.values())
    li = [json.dumps(it) for it in li]
    li = '\n'.join(li)
    open(args.flist, 'w', encoding='utf8').write(li)
    print('done...')

def main():
    parser = argparse.ArgumentParser(prog="dl-annas", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--version", action="version", version=f"PYBP version: 0.0.0.0")
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    
    dl_parser = subparsers.add_parser("dl-bt", help="download file")
    dl_parser.add_argument("hash", help="file hash")
    dl_parser.set_defaults(func=download_bt)

    dl_slow_parser = subparsers.add_parser("dl-slow", help="download file")
    dl_slow_parser.add_argument("hash", help="file hash")
    dl_slow_parser.add_argument("-H", "--headless", action='store_true', help="headless")
    dl_slow_parser.set_defaults(func=download_slow)


    dl_li_parser = subparsers.add_parser("dl-lgli", help="download file")
    dl_li_parser.add_argument("hash", help="file hash")
    dl_li_parser.set_defaults(func=download_lgli)

    batch_parser = subparsers.add_parser("batch", help="download file")
    batch_parser.add_argument("flist", help="JSONL list file")
    batch_parser.add_argument("-t", "--threads", type=int, default=8, help="threads num")
    batch_parser.add_argument("-s", "--site", default='annas', choices=['slow', 'bt', 'lgli'],  help="site")
    batch_parser.add_argument("-st", "--start", type=int, default=0,  help="start")
    batch_parser.add_argument("-H", "--headless", action='store_true', help="headless")
    batch_parser.set_defaults(func=batch)


    fetch_parser = subparsers.add_parser("fetch", help="download file")
    fetch_parser.add_argument("-s", "--start", type=int, default=1, help="start page")
    fetch_parser.add_argument("query", help="query kw")
    fetch_parser.add_argument("ofname", help="output file name")
    fetch_parser.add_argument("-e", "--end", type=int, default=1_000_000, help="end page")
    fetch_parser.add_argument("-r", "--sort", default='newest', help="sort by")
    fetch_parser.add_argument("-c", "--content", default=[], nargs='+', help="content")
    fetch_parser.add_argument("-l", "--lang", default=[], nargs='+', help="lang")
    fetch_parser.add_argument("-x", "--ext", default=[], nargs='+', help="ext name")
    fetch_parser.add_argument("-H", "--headless", action='store_true', help="headless")
    fetch_parser.add_argument("-R", "--retry", type=int, default=10, help="retry")
    fetch_parser.set_defaults(func=fetch)

    dedup_parser = subparsers.add_parser("dedup", help="dedup file")
    dedup_parser.add_argument("flist", help="JSONL list file")
    dedup_parser.set_defaults(func=dedup)


    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__': main()