import requests
import json
from os import path
import os
from pyquery import PyQuery as pq
import sys
import argparse
import re
import time
import zipfile
import traceback
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from EpubCrawler.util import request_retry
from GenEpub import gen_epub


hdrs = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36'
}
timeout = (8, 600)

def get_only_txt(data):
    zip = zipfile.ZipFile(BytesIO(data))
    names = list(zip.namelist())
    if len(names) == 0 or not names[0].endswith('.txt'):
        return
    txt = zip.read(names[0]).decode('gbk', 'ignore')
    zip.close()
    return txt

def fmt_txt(txt):
    txt = re.sub(r'^.+?\r?\n', '', txt)
    txt = re.sub(r'^###(.+?)###$', r'<h1>\1</h1>', txt, flags=re.M)
    txt = re.sub(r'^(?:\x20{4}|\u3000{2})(.+?)$', r'<p>\1</p>', txt, flags=re.M)
    chs = re.split(r'(?=<h1>)', txt)[1:]
    chs = [
        {
            'title': re.search(r'<h1>(.+?)</h1>', ch).group(1),
            'content': re.sub(r'<h1>.+?</h1>', '', ch),
        }
        for ch in chs
    ]
    return chs

def download_safe(*args, **kw):
    try: download(*args, **kw)
    except: traceback.print_exc()

def download(id, pr):
    print(f'id: {id}')
    url = f'http://www.biqu520.net/0_{id}/'
    while True:
        r = request_retry(
            'GET', url, 
            headers=hdrs, 
            proxies = {'http': pr, 'https': pr},
            timeout=timeout,
        )
        if r.status_code // 100 == 2 or r.status_code == 404: break
    if r.status_code == 404: 
        print(f'小说 [id={id}] 不存在')
        return
    html = r.content.decode('gbk', 'ignore')
    rt = pq(html)
    title = rt('#info>h1').eq(0).text()
    au = rt('#info>h1+p').text().split('：')[-1]
    chs = rt('#list dt:nth-of-type(2) ~ dd a')
    name = f'{title} - {au} - {len(chs)}CHS'
    print(name)
    ofname = name + '.epub'
    if path.isfile(ofname):
        print(f'{name} 已存在')
        return
    ts = int(time.time() * 1000)
    dl_url = f'http://d.downnovel.com/dn/{id}/a{ts}'
    while True:
        r = request_retry(
            'GET', dl_url, 
            headers=hdrs, 
            proxies = {'http': pr, 'https': pr},
            timeout=timeout,
        )
        if r.status_code // 100 == 2 or r.status_code == 404: break
    txt = get_only_txt(r.content)
    if not txt:
        print('下载失败')
        return
    chs = fmt_txt(txt)
    articles = [{
        'title': name,
        'content': f'来源：{url}'
    }] + chs
    gen_epub(articles, {})


def main():

    parser = argparse.ArgumentParser(prog="crawl-biquge", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--version", action="version", version=f"PYBP version: 0.0.0")
    parser.add_argument("-s", "--start", type=int, default=1, help="starting id")
    parser.add_argument("-e", "--end", type=int, default=1_000_000, help="ending id")
    parser.add_argument("-t", "--threads", type=int, default=1, help="thread count")
    parser.add_argument("-p", "--proxy", default='', help="proxy url")
        
    args = parser.parse_args()
    st, ed = args.start, args.end
    args.proxy = args.proxy.split(';')

    pool = ThreadPoolExecutor(args.threads)
    hdls = []
    for i in range(st, ed + 1):
        pr = args.proxy[i % len(args.proxy)]
        h = pool.submit(download, i, pr)
        hdls.append(h)
    for h in hdls: h.result()
    
if __name__ == '__main__': main()
