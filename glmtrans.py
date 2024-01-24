import torch
from transformers import AutoTokenizer, AutoModel, AutoConfig
import yaml
import argparse
import os
from os import path
import json

__version__ = '2023.12.11.0'

DFT_PROMPT = '请把以下文本翻译成中文：{en}'

def load_pytorch_llm(base_path, model_path=None, lora_path=None):
    model_path = model_path or path.join(base_path, 'pytorch_model.bin')
    # 加载问答模型
    tokenizer =  AutoTokenizer.from_pretrained(base_path, trust_remote_code=True)
    # 模型定义和参数没有放到一起，要分开加载
    conf = AutoConfig.from_pretrained(base_path, trust_remote_code=True)
    llm = AutoModel.from_config(conf, trust_remote_code=True)
    stdc = torch.load(model_path)
    llm.load_state_dict(stdc, False)
    if lora_path is not None:
        lora_stdc = torch.load(lora_path)
        llm.attach_lora()
        llm.load_state_dict(lora_stdc, False)
    llm = llm.cuda()
    return llm, tokenizer

def trans_one(llm, tokenizer, totrans, prompt):
    for it in totrans:
        if not it.get('en') or it.get('zh'):
            continue
        ques = prompt.replace('{en}', it['en'])
        ans = llm.chat(tokenizer, ques)[0]
        it['zh'] = ans
        print(f'ques: {json.dumps(ques, ensure_ascii=False)}\nans: {json.dumps(ans, ensure_ascii=False)}')
    return totrans

def trans_handle(args):
    print(args)
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
        
    llm, tokenizer = load_pytorch_llm(
        args.base_path, args.model_path, args.lora_path)
    for f in fnames:
        print(f)
        totrans = yaml.safe_load(open(f, encoding='utf8').read())
        totrans = trans_one(llm, tokenizer, totrans, args.prompt)
        open(f, 'w', encoding='utf8') \
            .write(yaml.safe_dump(totrans, allow_unicode=True))
    
def test_handle(args):
    print(args)
    llm, tokenizer = load_pytorch_llm(
        args.base_path, args.model_path, args.lora_path)
    ques = args.prompt.replace('{en}', args.en)
    ans = llm.chat(tokenizer, ques)[0]
    print(f'ques: {json.dumps(ques, ensure_ascii=False)}\nans: {json.dumps(ans, ensure_ascii=False)}')


def load_train_data(fname):
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
        ds = yaml.safe_load(open(f, encoding='utf8').read())
        for dit in ds:
            if not(dit.get('en') and dit.get('zh')):
                continue
            yield dit

def train_handle(args):
    print(args)
    # 如果没有指定 LORA 参数并且保存参数已存在
    # 将保存参数加载为 LORA 以便继续训练
    if path.isfile(args.save_path) and not args.lora_path:
        args.lora_path = args.save_path
    llm, tokenizer = load_pytorch_llm(
        args.base_path, args.model_path, args.lora_path)
    llm.attach_lora()
    torch.autograd.set_detect_anomaly(True)
    optimizer = torch.optim.SGD(llm.parameters(), lr=args.lr)
    step = 0
    skipset = set()
    for epoch in range(args.n_epoch):
        ds = load_train_data(args.fname)
        for i, dit in enumerate(ds):
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            # 组装问答和问答提示词
            ques = args.prompt.replace('{en}', dit['en'])
            if hasattr(tokenizer, 'build_prompt'): 
                # ChatGLM2
                ques = tokenizer.build_prompt(ques)
            ans = dit['zh']
            hash_ = (hash(ques), hash(ans))
            if hash_ in skipset: continue
            # 问答转成问答 ID
            if hasattr(tokenizer, 'build_chat_input'):
                # ChatGLM2
                ques_ids = tokenizer.build_chat_input(ques)['input_ids'][0].tolist()
            else:
                # ChatGLM2
                ques_ids = tokenizer.encode(text=ques, add_special_tokens=True, truncation=True)
            ans_ids = tokenizer.encode(text=ans, add_special_tokens=False, truncation=True)
            # 问答 ID 拼接输入 ID
            input_ids = ques_ids + ans_ids + [tokenizer.eos_token_id]
            output_ids = [tokenizer.pad_token_id] * len(ques_ids) + ans_ids + [tokenizer.eos_token_id] 
            # 忽略 <PAD>
            output_ids = [(oid if oid != tokenizer.pad_token_id else -100) for oid in output_ids]
            # 因为批量大小为 1，无需填充
            optimizer.zero_grad()
            input_ids = torch.tensor([input_ids]).cuda()
            output_ids = torch.tensor([output_ids]).cuda()
            with torch.autograd.detect_anomaly(): 
                loss = llm.forward(input_ids=input_ids, labels=output_ids, return_dict=True).loss
                print(
                    f'epoch: {epoch}\n' + 
                    f'step: {step}\n' + 
                    f'ques: {json.dumps(ques, ensure_ascii=False)}\n' + 
                    f'ans: {json.dumps(ans, ensure_ascii=False)}\n' + 
                    f'loss: {loss}'
                )
                if loss < args.loss_thres: 
                    skipset.add(hash_)
                    continue
                loss.backward()
            # 更新梯度
            torch.nn.utils.clip_grad_norm_(llm.parameters(), 0.1)
            optimizer.step()
            # 一定步骤保存权重
            if step % args.save_step == 0:
                torch.save(llm.lora_state_dict(), args.save_path)
            step += 1

    if step % args.save_step != 0:
        torch.save(llm.lora_state_dict(), args.save_path)
     
def main():
    parser = argparse.ArgumentParser(prog="GLMTrans", description="GLM training and translation tool for GLM", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--version", action="version", version=f"BookerMarkdownTool version: {__version__}")
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    
    trans_parser = subparsers.add_parser("trans", help="translate YAML files")
    trans_parser.add_argument("fname", help="yaml file name of dir")
    trans_parser.add_argument("-p", "--prompt", default=DFT_PROMPT, help="prompt for trans")
    trans_parser.add_argument("-b", "--base-path", default='/data/chatglm2-6b-int4-lora/model', help="path for model code")
    trans_parser.add_argument("-m", "--model-path", help="path for model param (optional)")
    trans_parser.add_argument("-l", "--lora-path", help="path for lora param")
    trans_parser.set_defaults(func=trans_handle)
    
    train_parser = subparsers.add_parser("train", help="training model with YAML files")
    train_parser.add_argument("fname", help="yaml file name of dir")
    train_parser.add_argument("-p", "--prompt", default=DFT_PROMPT, help="prompt for trans")
    train_parser.add_argument("-b", "--base-path", default='/data/chatglm2-6b-int4-lora/model', help="path for model code")
    train_parser.add_argument("-m", "--model-path", help="path for model param (optional)")
    train_parser.add_argument("-l", "--lora-path", help="path for lora param")
    train_parser.add_argument("--lr", type=float, default=5e-2, help="lr")
    train_parser.add_argument("--save-step", type=int, default=30, help="save_step")
    train_parser.add_argument("-n", "--n-epoch", type=int, default=15, help="n_epoch")
    train_parser.add_argument("save_path", help="path to save lora param")
    train_parser.add_argument("--loss-thres", type=float, default=5e-3, help="stop value for loss")
    train_parser.set_defaults(func=train_handle)
    
    test_parser = subparsers.add_parser("test", help="testing model with YAML files")
    test_parser.add_argument("en", help="en text")
    test_parser.add_argument("-p", "--prompt", default=DFT_PROMPT, help="prompt for trans")
    test_parser.add_argument("-b", "--base-path", default='/data/chatglm2-6b-int4-lora/model', help="path for model code")
    test_parser.add_argument("-m", "--model-path", help="path for model param (optional)")
    test_parser.add_argument("-l", "--lora-path", help="path for lora param")
    test_parser.set_defaults(func=test_handle)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__': main()