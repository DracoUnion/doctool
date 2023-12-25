import openai
import httpx
import os
import traceback
import yaml
import argparse
from os import path
import json
import random
import copy
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

__version__ = '2023.12.11.0'

DFT_PROMPT = '假设你是一位资深的程序员，请你为以下代码的每一行添加注释，如果遇到了函数，再为函数添加描述其完整功能、参数和返回值的注释，注意只输出带注释的代码，除此之外不要输出额外内容。\n\n{code}'

def call_openai_retry(code, prompt, model_name, retry=10):
    for i in range(retry):
        try:
            ques = prompt.replace('{code}', code)
            # print(f'ques: {json.dumps(ques, ensure_ascii=False)}')
            client = openai.OpenAI(
                base_url=openai.host,
                api_key=openai.api_key,
                http_client=httpx.Client(
                    proxies=openai.proxy,
                    transport=httpx.HTTPTransport(local_address="0.0.0.0"),
                )
            )
            ans = client.chat.completions.create(
                messages=[{
                    "role": "user",
                    "content": ques,
                }],
                model=model_name,
                temperature=0,
            ).choices[0].message.content
            return ans
        except Exception as ex:
            print(f'OpenAI retry {i+1}: {str(ex)}')
            if i == retry - 1: raise ex

def process_dir(args):
    dir = args.fname
    pool = ThreadPoolExecutor(args.threads)
    hdls = []
    for base, _, fnames in os.walk(dir):
        for f in fnames:
            args = copy.deepcopy(args)
            args.fname = path.join(base, f)
            h = pool.submit(process_file_safe, args)
            hdls.append(h)
    for h in hdls: h.result()

def process_file_safe(args):
    try:
        process_file(args)
    except:
        traceback.print_exc()

def process_file(args):
    fname = args.fname
    ext = extname(fname)
    if ext not in ['c', 'h', 'cpp', 'cxx', 'java', 'cs', 'php', 'go', 'js', 'ts', 'py']:
        print(f'{fname} 代码类型不支持')
        return
    ofname = fname + '.md'
    if path.isfile(ofname):
        print(f'{fname} 已存在')
        return
    code = open(fname, encoding='utf8').read()
    # blocks = chunk_code(code)
    # for b in blocks:
    # code = '\n'.join(b)
    comment = call_openai_retry(code, args.prompt, args.model, args.retry)
    if not comment.startswith('```'):
        comment = f'```{ext}\n' + comment
    if not comment.endswith('```'):
        comment = comment + '\n```'
    print(f'==={fname}===\n{comment}')
    res = f'# `{fname}`\n\n{comment}'
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
    parser.add_argument('-p', '--prompt', default=DFT_PROMPT, help='prompt for code comment')
    parser.add_argument("-P", "--proxy", help="proxy")
    parser.add_argument("-m", "--model", default='gpt-3.5-turbo-1106', help="model name")
    parser.add_argument("-k", "--key", default=os.environ.get('OPENAI_API_KEY', ''), help="OpenAI API key")
    parser.add_argument("-r", "--retry", type=int, default=10, help="times of retry")
    parser.add_argument("-H", "--host", help="api host")
    parser.add_argument("-t", "--threads", type=int, default=8, help="thread num")
    args = parser.parse_args()
    
    openai.api_key = args.key
    openai.proxy = args.proxy
    openai.host = args.host
 
    if path.isdir(args.fname):
        process_dir(args)
    else:
        process_file(args)
        
if __name__ == '__main__': main()