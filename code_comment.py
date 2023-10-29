import re
import os
import argparse
from os import path
import sys
import subprocess as subp

def code_comment(code, args):
    cmd = [
        'chatglm', '-m', args.model, 
        '-p', args.prompt + code
    ]
    print(cmd)
    r = subp.Popen(
        cmd, 
        stdout=subp.PIPE, 
        stderr=subp.PIPE,
        shell=sys.platform == 'win32',
    ).communicate()
    comment = r[0].decode('utf8', 'ignore')
    if not comment:
        raise Exception(r[1].decode('utf8', 'ignore'))
    return comment.replace('```', '')

def process_dir(args):
    dir = args.fname
    for base, _, fnames in os.walk(dir):
        for f in fnames:
            args.fname = path.join(base, f)
            process_file(args)

def process_file(args):
    fname = args.fname
    ext = extname(fname)
    if ext not in ['c', 'h', 'cpp', 'cxx', 'java', 'cs', 'php', 'go', 'js', 'ts', 'py']:
        print('代码类型不支持')
        return
    ofname = re.sub(r'\.\w+$', '', fname) + '.md'
    if path.isfile(ofname):
        print('已存在')
        return
    code = open(fname, encoding='utf8').read()
    blocks = chunk_code(code)
    res = []
    for b in blocks:
        code = '\n'.join(b)
        comment = code_comment(code, args)
        res.append(comment)
        
    res = f'# `{fname}`\n\n```\n' + '\n'.join(res) + '\n```'
    open(ofname, 'w', encoding='utf8').write(res)
    

def extname(name):
    m = re.search(r'\.(\w+)$', name)
    return m.group(1) if m else ''

def chunk_code(lines):
    if isinstance(lines, str):
        lines = lines.split('\n')
        
    class_mode = False
    blocks = [[]]

    for l in lines:
        if l.startswith('^class '):
            class_mode = True
        elif re.search(r'^[^\(\)\[\]{}\s]', l):
            class_mode = False
        
        RE_NEW_BLOCK = (
            r'^(\x20{4}|\t)?[^\(\)\[\]{}\s]'
            if class_mode
            else r'^[^\(\)\[\]{}\s]'
        )
        if re.search(RE_NEW_BLOCK, l):
            blocks.append([])
        blocks[-1].append(l)
        

    for i in range(0, len(blocks) - 1):
        if len(blocks[i]) < 15:
            blocks[i + 1] = blocks[i] + blocks[i + 1]
            blocks[i] = []
            
    blocks = [b for b in blocks if b]
    return blocks
    
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('fname', help='file or dir name')
    parser.add_argument('-p', '--prompt', default='请给以下代码的每一行添加注释，输出带有注释的代码：', help='prompt for code comment')
    parser.add_argument('model', help='chatglm-cpp model')
    
    args = parser.parse_args()
    
    if path.isdir(args.fname):
        process_dir(args)
    else:
        process_file(args)
        
if __name__ == '__main__': main()