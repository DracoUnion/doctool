import fitz as pymu
from os import path
import os
from io import BytesIO
import random
import hashlib
import argparse

def ext_ppts(args):
    if not path.isdir(args.odir):
        os.makedirs(args.odir)
    if path.isdir(args.fname):
        fnames = [path.join(args.fname, f) for f in os.listdir(args.fname)]
    else:
        fnames = [args.fname]
    fnames = [f for f in fnames if f.endswith('.pdf')]
    if not fnames:
        print('请提供 PPT 的文件名或目录')
        return
    for f in fnames:
        print(f)
        doc = pymu.open("pdf", BytesIO(open(f, 'rb').read()))
        hash_ = hashlib.md5(f.encode('utf8')).hexdigest()
        n_pg = len(doc)
        n_sel = min(n_pg, args.n_pages)
        pg_nums = random.choices(list(range(n_pg)), k=n_sel)
        for i in pg_nums:
            px = doc[i].get_pixmap(dpi=400)
            img_fname = path.join(args.odir, f'{hash_}_{i}.png')
            px.save(img_fname)
            print(img_fname)
        doc.close()

def main():
    parser = argparse.ArgumentParser(prog="ext-ppt-pics", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--odir", default='.', help="output dir")
    parser.add_argument("fname", help="PDF fname or dirname")
    parser.add_argument("-n", "--n-pages", type=int, default=10, help="num of pages per file")
    parser.set_defaults(func=ext_ppts)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__': main()