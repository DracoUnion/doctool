import os
import argparse
import re
from BookerDownloadTool.util import request_retry, fname_escape
import bencode
import subprocess as subp
from pyquery import PyQuery as pq

HOST = 'annas-archive.gl'

def get_bt_idx(bt_data, fname):
    bt = bencode.bdecode(bt_data)
    for idx, f in enumerate(bt['info']['files']):
        if fname in f['path']:
            return idx
    return -1

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
    subp.run(cmd, shell=True)
    os.rename(hash_, fname)

def main():
    parser = argparse.ArgumentParser(prog="dl-annas", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--version", action="version", version=f"PYBP version: 0.0.0.0")
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    
    trans_parser = subparsers.add_parser("download", help="download file")
    trans_parser.add_argument("hash", help="file hash")
    trans_parser.set_defaults(func=download)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__': main()