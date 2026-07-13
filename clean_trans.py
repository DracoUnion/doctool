import shutil
from BookerGptTool.util import to_kebab
import os
import sys
from os import path

def main():
    dir = sys.argv[1]
    if not path.isdir(dir):
        print('请提供目录')
        return
    
    out_dir = path.join(path.dirname(__file__), 'done')
    os.makedirs(out_dir, exist_ok=True)

    ebook_fnames = [
        f
        for f in os.listdir(dir)
        if f.endswith('.pdf') or f.endswith('.epub')
    ]

    for f in ebook_fnames:
        slug = to_kebab(f[:-4] if f.endswith('.pdf') else f[:-5]) 
        if path.isfile(path.join(dir, slug, 'README.md')):
            print(f'清理 {f}')
            os.remove(path.join(dir, f))
            shutil.move(
                path.join(dir, slug),
                out_dir,
            )

if __name__ == '__main__': main()