from concurrent.futures import ThreadPoolExecutor
import shutil
import os
import argparse
import re
import json
from BookerDownloadTool.util import request_retry, fname_escape
import bencode
import copy
import subprocess as subp
from pyquery import PyQuery as pq
from urllib.parse import quote_plus

HOST = 'annas-archive.gl'

def get_bt_idx(bt_data, fname):
    bt = bencode.bdecode(bt_data)
    for idx, f in enumerate(bt['info']['files']):
        if fname in f['path']:
            return idx
    return -1

def batch(args):
    if not args.flist.endswith('.jsonl'):
        print('请提供 JSONL 文件')
        return
    
    pool = ThreadPoolExecutor(args.threads)
    hdls = []
    lines = open(args.flist, encoding='utf8').read().split('\n')
    lines = [l for l in lines if l.strip()]
    for l in lines:
        j = json.loads(l)
        args = copy.deepcopy(args)
        args.hash = j['hash']
        h = pool.submit(download, args)
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
        html = request_retry('GET', url).text
        rt = pq(html)
        el_links = rt.find('a.text-lg[href^="/md5/"]')
        if not el_links: break
        for el in el_links:
            el = pq(el)
            hash_ = el.attr('href').replace('/md5/', '')
            title = el.text().strip()
            print(f'title: {title}, hash: {hash_}')
            f.write(json.dumps({'title': title, 'hash': hash_}) + '\n')
            f.flush()
    f.close()
    


def download(args):
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
    ]
    subp.run(cmd, shell=True).check_returncode()
    os.rename(hash_, fname)
    bt_name = bencode.bdecode(bt_data)['info']['name']
    shutil.rmtree(bt_name)
    os.remove(bt_name + '.aria2')
    # aria2_fname = [f for f in os.listdir() if f.endswith('.aria2')]
    # for f in aria2_fname: os.remove(f)

def main():
    parser = argparse.ArgumentParser(prog="dl-annas", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--version", action="version", version=f"PYBP version: 0.0.0.0")
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    
    dl_parser = subparsers.add_parser("download", help="download file")
    dl_parser.add_argument("hash", help="file hash")
    dl_parser.set_defaults(func=download)

    batch_parser = subparsers.add_parser("batch", help="download file")
    batch_parser.add_argument("flist", help="JSONL list file")
    batch_parser.add_argument("-t", "--threads", type=int, default=8, help="threads num")
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
    fetch_parser.set_defaults(func=fetch)


    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__': main()