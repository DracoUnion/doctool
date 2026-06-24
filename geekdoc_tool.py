import subprocess as subp
import os
from os import path
import sys
from BookerMarkdownTool.util import get_md_title

def process_doc(d):
    rt = os.listdir(d)
    if 'README.md' not in rt or \
       'SUMMARY.md' not in rt:
       return

    mds = [
        f for f in rt 
        if f.endswith('.md') and
           f != 'README.md' and 
           f != 'SUMMARY.md'
    ]
    if len(mds) == 2:
        sorted(mds)
        if not mds[1].startswith(mds[0]): return
        os.remove(path.join(d, mds[1]))
        mds.pop()
    if len(mds) == 1:
        fname = path.join(d, mds[0])
        print(f'处理 {fname}')
        readme = open(path.join(d, 'README.md'), encoding='utf8').read()
        body = open(fname, encoding='utf8').read()
        readme_title = get_md_title(readme)[0]
        body_title = get_md_title(body)[0]
        if readme_title == body_title: 
            print(f'{fname} 已处理')
            return
        subp.run(f'gpt-tool -st clean-heading "{fname}"')
        body = open(fname, encoding='utf8').read()
        body = f'# {readme_title}\n\n{body}'
        open(fname, 'w', encoding='utf8').write(body)
        subp.run(f'md-tool summary "{d}"')
        




def main():
    pj_dir = sys.argv[1]
    print(pj_dir)
    rt = os.listdir(pj_dir)
    if 'README.md' not in rt or \
       'SUMMARY.md' not in rt or \
       'index.html' not in rt:
       print('请提供项目目录')
       return
    docs = [path.join(pj_dir, 'docs', d) for d in os.listdir(path.join(pj_dir, 'docs'))]
    docs = [d for d in docs if path.isdir(d)]
    for d in docs:
        process_doc(d)
    
if __name__ == '__main__': main()