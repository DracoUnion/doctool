import os
import sys
from os import path
from Ashare import *
from concurrent.futures import ThreadPoolExecutor
import argparse

def get_single(code, retry, freq):
    for i in range(retry):
        try:
            return  get_price(
                code, frequency=f'1{freq}', 
                count=1_000_000_000,
                end_date='2020-12-31'
            )
        except Exception as ex:
            print(f'{code} retry #{i+1}: {ex}')
            if i == retry - 1: raise ex
        
def tr_dl_single(code, retry, freq):
    print(code)
    freq_txt = 'day' if freq == 'd' else 'min'
    fname = f'{code}_20201231_{freq_txt}.csv'      
    if path.isfile(fname):
        print(f'{code} 已存在')
        return
    df = get_single(code, retry, freq)
    df.to_csv(fname)

        
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', type=int, default=1)
    parser.add_argument('-e', '--end', type=int, default=3999)
    parser.add_argument('-r', '--retry', type=int, default=1_000_000_000)
    parser.add_argument('-t', '--threads', type=int, default=8)
    parser.add_argument('-f', '--freq', choices=['m', 'd'], default='d')
    args = parser.parse_args()

    st, ed, retry, threads = args.start, args.end, args.retry, args.threads
    
    pool = ThreadPoolExecutor(threads)
    hdls = []
    for i in range(st, ed + 1): 
        code = f'6{i:05d}.XSHG'
        h = pool.submit(tr_dl_single, code , retry, args.freq)
        hdls.append(h)
        if len(hdls ) >= threads:
            for h in hdls: h.result()
            hdls.clear()
    
    for h in hdls: h.result()

        
if __name__ == '__main__': main()