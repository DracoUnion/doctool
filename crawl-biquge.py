import requests
import json
from os import path
import os
from pyquery import PyQuery as pq
import sys
import argparse

hdrs = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36'
}

parser = argparse.ArgumentParser(prog="crawl-biquge", formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("-v", "--version", action="version", version=f"PYBP version: 0.0.0")
parser.add_argument("-s", "--start", type=int, default=1, help="starting id")
parser.add_argument("-e", "--end", type=int, default=1_000_000, help="ending id")
parser.add_argument("-t", "--threads", type=int, default=1, help="thread count")
parser.add_argument("-p", "--proxy", help="proxy url")
    
args = parser.parse_args()
if args.proxy:
    args.proxy = {'http': args.proxy, 'https': args.proxy}
st, ed = args.start, args.end

for i in range(st, ed + 1):
    url = f'http://www.biqu520.net/0_{i}/'
    while True:
        r = requests.get(url, headers=hdrs)
        if r.status_code // 100 != 5: break
    if r.status_code == 404: continue
    html = r.content.decode('gbk', 'ignore')
    # print(html)
    rt = pq(html)
    title = rt('#info>h1').eq(0).text()
    au = rt('#info>h1+p').text().split('：')[-1]
    chs = rt('#list dt:nth-of-type(2) ~ dd a')
    name = f'{title} - {au} - {len(chs)}CHS'
    print(name)
    ofname = name + '.epub'
    if path.isfile(ofname):
        print(f'{name} 已存在')
        continue
    cfg = {
        "name": name,
        "url": url,
        "link": "#list dt:nth-of-type(2) ~ dd a",
        "title": ".bookname>h1",
        "content": "#content",
        "textThreads": args.threads,
        "retry": 1000,
        "encoding": "gbk",
        "proxy": args.proxy,
        "optiMode": "thres",
    }
    open('config_biquge.json', 'w').write(json.dumps(cfg))
    os.system('crawl-epub config_biquge.json')
    