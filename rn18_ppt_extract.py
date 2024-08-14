import random
import argparse
import torchvision as tv
import torch
import os
from os import path
from BookerMarkdownTool.util import *
import cv2
import numpy as np

def load_model(model_path=None, freeze_nonlast=True):
    model = tv.models.resnet18(num_classes=1)
    if model_path:
        stdc = torch.load(model_path)
        model.load_state_dict(stdc)
    model = model.half()
    if torch.cuda.is_available():
        model = model.cuda()
    if freeze_nonlast:
        for name, param in model.named_parameters():
            if not name.startswith('fc.'):
                param.requires_grad = False
            
    return model

def preproc_imgs(imgs):
    # bytes -> ndarray
    if isinstance(imgs[0], bytes):
        imgs = [
            cv2.imdecode(np.frombuffer(i, np.uint8), cv2.IMREAD_COLOR)
            for i in imgs
        ]
    # resize -> 224x224
    imgs = [
        cv2.resize(i, [224, 224], interpolation=cv2.INTER_CUBIC) 
        for i in imgs
    ]
    imgs = (
        torch.tensor(imgs) 
            # HWC -> CHW
            .permute([0, 3, 1, 2])
            # BGR -> RGB
            [:, ::-1]
            # norm
            .div(255)
    )
    imgs = imgs.half()
    if torch.cuda.is_available():
        imgs = imgs.cuda()
    return imgs

def predict_handle(args):
    print(args)
    model: tv.models.ResNet = load_model(args.model_path).eval()
    if path.isdir(args.fname):
        img_fnames = [
            path.join(args.fname, f) 
            for f in os.listdir(args.fname) 
        ]
    else:
        img_fnames = [args.fname]
    img_fnames = [f for f in img_fnames if is_pic(img_fnames)]
    if not img_fnames:
        raise ValueError('请提供图片或其目录的路径')
    for i in range(0, len(img_fnames), args.batch_size):
        imgs = (
            open(f, 'rb').read()
            for f in img_fnames
        )
        imgs = preproc_imgs(imgs)
        is_ppt = torch.sigmoid(model.forward(imgs)).gt(args.thres).flatten().tolist()
        for f, l in zip(img_fnames, is_ppt):
            print(f'{f} 是 PPT' if l else f'{f} 不是 PPT')

def print_step_info(epoch, step, img_fnames, loss):
    print(
        f'epoch: {epoch}\n' + 
        f'step: {step}'
    )
    for i, f in enumerate(img_fnames):
        print(f'img#{i}: {f}')
    print(f'loss: {loss}')
        
def train_handle(args):
    print(args)
    model: tv.models.ResNet = load_model(args.model_path)
    ds = yaml.safe_load(open(args.train_set, encoding='utf8').read())
    for it in ds:
        it['img'] = path.join(path.dirname(args.train_set), it['img'])

    if args.adam:
        optimizer = torch.optim.AdamW(
            model.parameters(), 
            lr=args.lr,
            eps=1e-3, # 防止半精度溢出
        )
    else:
        optimizer = torch.optim.SGD(
            model.parameters(), 
            lr=args.lr,
        )
    scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer, 
        step_size=args.schedule_epoch, 
        gamma=args.schedule_gamma
    )

    step = 0
    for epoch in range(args.n_epoch):

        random.shuffle(ds)
        for i in range(0, len(ds), args.batch_size):
            try:
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                optimizer.zero_grad()

                ds_part = ds[i:i+args.batch_size]
                img_fnames = [it['img'] for it in ds_part]
                imgs = (
                    open(f, 'rb').read()
                    for f in img_fnames
                )
                imgs = preproc_imgs(img_fnames)
                labels = torch.tensor([it['label'] for it in ds]).half()
                if torch.cuda.is_available():
                    labels = labels.cuda()
                
                preds = model.forward(imgs).flatten()
                loss = - torch.mean(
                    labels * torch.log(torch.sigmoid((preds)))  +
                    (1 - labels) * torch.log(1 - torch.sigmoid(preds))
                )
                print_step_info(epoch, step, img_fnames, loss)
                
                if loss >= args.loss_thres: 
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 0.1)
                    optimizer.step()
                if step % args.save_step == 0:
                    torch.save(model.state_dict(), args.save_path)
                step += 1
            except torch.cuda.OutOfMemoryError as ex:
                print(ex)
            except RuntimeError as ex:
                print(ex)
        scheduler.step()

    if step % args.save_step != 0:
        torch.save(model.state_dict(), args.save_path)

def main():
    parser = argparse.ArgumentParser(prog="RN18PPTEXT", description="RN18PPTEXT", formatter_class=argparse.RawDescriptionHelpFormatter)
    # parser.add_argument("-v", "--version", action="version", version=f"BookerMarkdownTool version: {__version__}")
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    train_parser = subparsers.add_parser("train", help="train GLM model")
    train_parser.add_argument("train_set", help="jsonl file name")
    train_parser.add_argument("--val-set", help="validation set jsonl file name")
    train_parser.add_argument("-m", "--model-path", help="path for model param (optional)")
    train_parser.add_argument("--adam", action='store_true', help="use adam")
    train_parser.add_argument("save_path", help="path to save lora param")
    train_parser.add_argument("--lr", type=float, default=5e-2, help="lr")
    train_parser.add_argument("--schedule-epoch", type=int, default=1, help="lr schedule epoch")
    train_parser.add_argument("--schedule-gamma", type=float, default=0.9, help="lr schedule gamma")
    train_parser.add_argument("--save-step", type=int, default=30, help="save_step")
    train_parser.add_argument("--val-step", type=int, default=15, help="val_step")
    train_parser.add_argument("-n", "--n-epoch", type=int, default=15, help="n_epoch")
    train_parser.add_argument("--loss-thres", type=float, default=1e-2, help="stop value for loss")
    train_parser.add_argument("-s", "--batch-size", type=int, default=1, help="batch size")
    train_parser.set_defaults(func=train_handle)

    pred_parser =  subparsers.add_parser("pred", help="pred GLM model")
    pred_parser.add_argument("fname", help="img file name or path")
    pred_parser.add_argument("-s", "--batch-size", type=int, default=1, help="batch size")
    pred_parser.add_argument("-m", "--model-path", help="path for model param (optional)")
    pred_parser.add_argument("-t", "--thres", type=float, default=0.8, help="thres")
    pred_parser.set_defaults(func=predict_handle)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__': main()