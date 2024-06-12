import sys
import os
from os import path

BS = 1000
ST = 1
ED = 13981

def main():
    global ST, ED
    
    dir = sys.argv[1]
    ST = ST // BS * BS
    ED = ED // BS * BS + BS - 1
    for i in range(ST, ED + 1, BS):
        ofname = path.join(dir, 
            f'{i:09d}-{i+BS-1:09d}.md')
        if path.isfile(ofname):
            print(f'{ofname} 已存在')
            continue
        fnames = [
            path.join(dir, f'{j:09d}.md')
            for j in range(i, i + BS)
        ]
        fnames = [f for f in fnames if path.isfile(f)]
        print(fnames[:10])
        if not fnames:
            print(f'{i:09d}-{i+BS-1:09d} 无文件')
            continue
        
        mds = [open(f, encoding='utf8').read() for f in fnames]
        md = f'# StackOverflow 问答 {i}-{i+BS-1}\n\n' + '\n\n'.join(mds)
        open(ofname, 'w', encoding='utf8').write(md)
        print(ofname)
        for f in fnames:
            os.remove(f)
            
if __name__ == '__main__': main()