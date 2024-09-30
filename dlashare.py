import os
import sys
from os import path
from Ashare import *

def dl_single(code, retry):
    for i in range(retry):
        try:
            return  get_price(
                code, frequency='1d', 
                count=1_000_000_000,
                end_date='2020-12-31'
            )
        except Exception as ex:
            print(f'{code} retry #{i+1}: {ex}')
            if i == retry - 1: raise ex
        
def main():
    st = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    ed = int(sys.argv[2]) if len(sys.argv) > 2 else 99999
    retry = int(sys.argv[3]) if len(sys.argv) > 3 else 1_000_000_000
    
    for i in range(st, ed + 1): 
        code = f'6{i:05d}.XSHG'
        print(code)
        fname = f'{code}_20201231_day.csv'      
        if path.isfile(fname):
            print(f'{code} 已存在')
            continue
        df = dl_single(code, retry)
        df.to_csv(fname, index=False)
        
if __name__ == '__main__': main()