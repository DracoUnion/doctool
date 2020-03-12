# coding: utf-8

# 四阶灰度扩散仿色
# python diffdither.py <file> [-m <trunc|grid|noise>]

import sys
import cv2
import numpy as np
import re
from argparse import ArgumentParser

pts = [
    [0, 0], # 1/16
    [2, 2],
    [0, 2],
    [2, 0],
    [1, 1],
    [3, 3],
    [3, 1],
    [1, 3],
    [2, 3],
    [0, 1],
    [0, 3],
    [2, 1],
    [1, 0],
    [3, 2],
    [1, 2],
    [3, 1], # 16/16
]

def make_noise(size, fc=0, bc=255, k=8):
    # P(fc) = k/16, P(bc) = (16-k)/16
    if k == 0: return np.zeros(size) + bc
    idx = np.random.random(size) < k/16
    img = np.where(idx, fc, bc)
    return img

def make_grid(size, fc=0, bc=255, k=8):
    img = np.zeros(size) + bc
    for i in range(k):
        r, c = pts[i]
        img[r::4, c::4] = fc
    return img
    

modes = {
    'grid': make_grid,
    'noise': make_noise,
}

def greyl4(img, l=4):
    assert img.ndim == 2
    
    colors = np.linspace(0, 255, l).astype(int)
    
    img_3d = np.expand_dims(img, 2)
    dist = np.abs(img_3d - colors)
    idx = np.argmin(dist, axis=2)
    img = colors[idx]
    
    return img

def diffdither(img, mode='grid'):
    assert img.ndim == 2
    
    '''
    h, w = img.shape
    if size and w > size:
        nw = size
        rate = nw / w
        nh = round(h * rate)
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_CUBIC)
    '''
    
    # b=0, c11, c12, c13, c14,
    # c1=85, c21, c22, c23, c24,
    # c2=170, c31, c32, c33, c34, w=255
    clrs = np.linspace(0, 255, 16).astype(int)

    settings = [
        {'fc': 0, 'bc': 0, 'k': 0}, # b
        {'fc': 85, 'bc': 0, 'k': 3}, # c11
        {'fc': 85, 'bc': 0, 'k': 6}, # c12
        {'fc': 85, 'bc': 0, 'k': 10}, # c13
        {'fc': 85, 'bc': 0, 'k': 13}, # c14
        {'fc': 0, 'bc': 85, 'k': 0}, # c1
        {'fc': 85, 'bc': 170, 'k': 13}, # c21
        {'fc': 85, 'bc': 170, 'k': 10}, # c22
        {'fc': 85, 'bc': 170, 'k': 8}, # c23
        {'fc': 85, 'bc': 170, 'k': 4}, # c24
        {'fc': 0, 'bc': 170, 'k': 0}, # c2
        {'fc': 255, 'bc': 170, 'k': 3}, # c31
        {'fc': 255, 'bc': 170, 'k': 6}, # c32
        {'fc': 255, 'bc': 170, 'k': 10}, # c33
        {'fc': 255, 'bc': 170, 'k': 13}, # c34
        {'fc': 0, 'bc': 255, 'k': 0}, # w
    ]

    
    delims = (clrs[1:] + clrs[:-1]) // 2
    delims = np.asarray([0, *delims, 255])
                       
    idcs = [((img >= st) & (img < ed)) for st, ed in zip(delims[:-1], delims[1:])]
    
    for idx, kwargs in zip(idcs, settings):
        pt = modes[mode](img.shape, **kwargs)
        img = img * (1 - idx) + pt * idx
    
    return img

def main():
    parser = ArgumentParser()
    parser.add_argument('fname')
    parser.add_argument('--mode', '-m', default='grid', \
                        choices=[*modes.keys(), 'trunc'])
    args = parser.parse_args()

    fname = args.fname
    print(fname)
    img = cv2.imdecode(np.fromfile(fname, np.uint8), cv2.IMREAD_GRAYSCALE)
    if args.mode == 'trunc':
        img = greyl4(img)
    else:
        img = diffdither(img, args.mode)
    fname = re.sub(r'\.\w+$', '', fname) + '.png'
    cv2.imwrite(fname, img, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    
if __name__ == '__main__': main()
