import openai
import httpx
import os
import traceback
import yaml
import argparse
from os import path
import json

__version__ = '2023.12.11.0'

DFT_PROMPT = '请把以下文本翻译成中文，不要输出原文：{en}'

def trans_one(model_name, totrans, prompt, limit=4000):
    for it in totrans:
        if not it.get('en') or it.get('zh'):
            continue
        if it.get('type') in ['TYPE_PRE', 'TYPE_IMG']:
            continue
        ques = prompt.replace('{en}', it['en'])
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
        ).choices[0].message.content
        it['zh'] = ans
        print(f'ques: {json.dumps(ques, ensure_ascii=False)}\nans: {json.dumps(ans, ensure_ascii=False)}')
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
        totrans = trans_one(args.model, totrans, args.prompt, args.limit)
        open(f, 'w', encoding='utf8') \
            .write(yaml.safe_dump(totrans, allow_unicode=True))
    
def test_handle(args):
    print(args)
    openai.api_key = args.key
    openai.proxy = args.proxy
    ques = args.prompt.replace('{en}', args.en)
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
        model=args.model,
    ).choices[0].message.content
    print(ans)
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
    trans_parser.set_defaults(func=trans_handle)
    
    test_parser = subparsers.add_parser("test", help="testing model with YAML files")
    test_parser.add_argument("en", help="en text")
    test_parser.add_argument("-p", "--prompt", default=DFT_PROMPT, help="prompt for trans")
    test_parser.add_argument("-P", "--proxy", help="proxy")
    test_parser.add_argument("-m", "--model", default='gpt-3.5-turbo', help="model name")
    test_parser.add_argument("-l", "--limit", type=int, default=4000, help="max token limit")
    test_parser.add_argument("-k", "--key", default=os.environ.get('OPENAI_API_KEY', ''), help="OpenAI API key")
    test_parser.set_defaults(func=test_handle)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__': main()