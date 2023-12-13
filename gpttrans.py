import openai
import os
import traceback
import yaml
import argparse
from os import path
import json


def trans_one(model_name, totrans, prompt, limit=4000):
    for it in totrans:
        if not it.get('en') or it.get('zh'):
            continue
        ques = prompt.replace('{en}', it['en'])
        ans = openai.Completion.create(
            engine=model_name,
            prompt=ques,
            max_tokens=limit,
            temperature=0
        ).choices[0].text
        it['zh'] = ans
        print(f'ques: {json.dumps(ques, ensure_ascii=False)}\nans: {json.dumps(ans, ensure_ascii=False)}')
    return totrans

def trans_handle(args):
    print(args)
    openai.api_key = args.key
    openai.proxy = {'http': args.proxy, 'https': args.proxy}
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
    openai.proxy = {'http': args.proxy, 'https': args.proxy}
    ques = args.prompt.replace('{en}', args.en)
    ans = openai.Completion.create(
        engine=args.model,
        prompt=ques,
        max_tokens=args.limit,
        temperature=0
    ).choices[0].text
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