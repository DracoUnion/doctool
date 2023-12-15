import openai
import httpx
import os
import traceback
import yaml
import argparse
from os import path
import json
import random

__version__ = '2023.12.11.0'

DFT_PROMPT = '请把以下文本按行翻译成中文，不要输出原文：\n\n{en}'

def shuffle_group(g):
    count = len(g['ids'])
    idcs = list(range(count))
    random.shuffle(idcs)
    g['ids'] = [g['ids'][i] for i in idcs]
    g['ens'] = [g['ens'][i] for i in idcs]

def trans_openai_retry(en, prompt, model_name, retry=10):
    for i in range(retry):
        try:
            ques = prompt.replace('{en}', en)
            print(f'ques: {json.dumps(ques, ensure_ascii=False)}')
            client = openai.OpenAI(
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
    
def group_totrans(totrans, limit):
    groups = [] # [{ids: [str], ens: [str]}]
    for it in totrans:
        if not it.get('en') or it.get('zh'):
            continue
        if it.get('type') in ['TYPE_PRE', 'TYPE_IMG']:
            continue
        if len(groups) == 0:
            groups.append({
                'ids': [it['id']],
                'ens': [it['en']]
            })
        else:
            total = len('\n'.join(groups[-1]['ens']))
            if total + len(it['en']) <= limit:
               groups[-1]['ids'].append(it['id']) 
               groups[-1]['ens'].append(it['en']) 
            else:
                groups.append({
                    'ids': [it['id']],
                    'ens': [it['en']]
                })
    return groups

def preproc_totrans(totrans):
    for i, it in enumerate(totrans):
        if not it.get('id'):
            it['id'] = f'totrans-{i}'
        if it.get('en'):
            it['en'] = it['en'].replace('\n', '')

def trans_one(totrans, args, write_callback=None):
    # totrans: [{id?: str, en?: str, zh?: str, type: str, ...}]
    preproc_totrans(totrans)
    groups = group_totrans(totrans, args.limit)
    totrans_id_map = {it['id']:it for it in totrans}
    for g in groups:
        for i in range(args.retry):
            try:
                shuffle_group(g)    
                en = '\n'.join(g['ens'])
                ans = trans_openai_retry(en, args.prompt, args.model, args.retry)
                print(f'ans: {json.dumps(ans, ensure_ascii=False)}')
                zhs = [zh for zh in ans.split('\n') if zh]
                assert len(g['ids']) == len(zhs)
                break
            except Exception as ex:
                print(f'en-zh match retry {i+1}')
                if i == args.retry - 1: raise ex
        for id, zh in zip(g['ids'], zhs):
            totrans_id_map.get(id, {})['zh'] = zh
        # 及时保存已翻译文本
        if write_callback: write_callback(totrans)
    return totrans

def trans_handle(args):
    print(args)
    openai.api_key = args.key
    openai.proxy = args.proxy
    fname = args.fname
    if path.isfile(fname):
        fnames = [fname]
    elif path.isdir(fname):
        fnames = [
            path.join(fname, f) 
            for f in os.listdir(fname) 
            if f.endswith('.yaml')
        ]
    else:
        raise Exception('请提供 YAML 文件或其目录')
        
    for f in fnames:
        print(f)
        totrans = yaml.safe_load(open(f, encoding='utf8').read())
        write_callback = lambda totrans: \
            open(f, 'w', encoding='utf8') \
                .write(yaml.safe_dump(totrans, allow_unicode=True))
        trans_one(totrans, args, write_callback)
        
    
def test_handle(args):
    print(args)
    openai.api_key = args.key
    openai.proxy = args.proxy
    ans = trans_openai_retry(args.en, args.prompt, args.model)
    print(f'ques: {json.dumps(ques, ensure_ascii=False)}\nans: {json.dumps(ans, ensure_ascii=False)}')
    
     
def main():
    parser = argparse.ArgumentParser(prog="GPTTrans", description="ChatGPT training and translation tool for GLM", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--version", action="version", version=f"BookerMarkdownTool version: {__version__}")
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    
    trans_parser = subparsers.add_parser("trans", help="translate YAML files")
    trans_parser.add_argument("fname", help="yaml file name of dir")
    trans_parser.add_argument("-p", "--prompt", default=DFT_PROMPT, help="prompt for trans")
    trans_parser.add_argument("-P", "--proxy", help="proxy")
    trans_parser.add_argument("-m", "--model", default='gpt-3.5-turbo', help="model name")
    trans_parser.add_argument("-l", "--limit", type=int, default=4000, help="max token limit")
    trans_parser.add_argument("-k", "--key", default=os.environ.get('OPENAI_API_KEY', ''), help="OpenAI API key")
    trans_parser.add_argument("-r", "--retry", type=int, default=10, help="times of retry")
    trans_parser.set_defaults(func=trans_handle)
    
    test_parser = subparsers.add_parser("test", help="testing model with YAML files")
    test_parser.add_argument("en", help="en text")
    test_parser.add_argument("-p", "--prompt", default=DFT_PROMPT, help="prompt for trans")
    test_parser.add_argument("-P", "--proxy", help="proxy")
    test_parser.add_argument("-m", "--model", default='gpt-3.5-turbo', help="model name")
    test_parser.add_argument("-l", "--limit", type=int, default=4000, help="max token limit")
    test_parser.add_argument("-k", "--key", default=os.environ.get('OPENAI_API_KEY', ''), help="OpenAI API key")
    test_parser.add_argument("-r", "--retry", type=int, default=10, help="times of retry")
    test_parser.set_defaults(func=test_handle)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__': main()