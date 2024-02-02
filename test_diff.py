import numpy as np
import cv2
import matplotlib.pyplot as plt
import sys

def one_diff(img):
    img_h_diff = np.abs(img[1:] - img[:-1])[:, 1:]
    img_w_diff = np.abs(img[:, 1:] - img[:, :-1])[1:]
    img_diff = (img_h_diff + img_w_diff) / 2
    img_diff_pad = np.zeros_like(img)
    img_diff_pad[:img_diff.shape[0], :img_diff.shape[1]] = img_diff
    return img_diff_pad.astype(int)

def max_2x2(img):
    h, w = img.shape
    if h % 2 == 1:
        img = img[:-1]
    if w % 2 == 1:
        img = img[:, :-1]
    img = np.maximum(img[::2], img[1::2])
    img = np.maximum(img[:, ::2], img[:, 1::2])
    return img

def main():
    fname = sys.argv[1]
    img = open(fname, 'rb').read()
    img = cv2.imdecode(
        np.frombuffer(img, np.uint8), 
        cv2.IMREAD_GRAYSCALE
    )
    # print(img)
    img = cv2.resize(img, [512, 512], interpolation=cv2.INTER_CUBIC)
    img = img.astype(int)
    while True:
        img = one_diff(img)
        img = max_2x2(img)
        if min(img.shape) < 8: break
    # print(img)
    bins = np.linspace(0, 256, 17)
    cnts, _ = np.histogram(img, bins=bins)
    freqs = cnts / np.prod(img.shape)
    print(freqs)
    x = (bins[1:] + bins[:-1]) / 2
    plt.plot(x, freqs, marker='o')
    plt.show()
    
if __name__ == '__main__': main()