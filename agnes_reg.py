import subprocess
import os
import shutil
import requests
import json
from time import sleep
import random
import string
import re
import cv2
import numpy as np
from imgyaso import adathres
import traceback
import subprocess
import hashlib
import time as _time
import urllib.parse
from datetime import datetime

def match_tmpl_rot(bg_img, tmpl_img, conf=0):

    best_sc = 0
    best_loc = None

    for angle in range(-45, 45, 5):
        (h, w) = tmpl_img.shape[:2]
        center = (w // 2, h // 2)
        rotmat = cv2.getRotationMatrix2D(center, angle, 1.0)

        # 执行旋转，使用白色背景填充黑边
        rotated = cv2.warpAffine(tmpl_img, rotmat, (w, h), borderValue=255)

        res = cv2.matchTemplate(bg_img, rotated, cv2.TM_CCOEFF_NORMED)

        # Find the best match
        _, sc, _, loc = cv2.minMaxLoc(res)

        # If we have a good match
        if sc > best_sc:
            best_sc = sc
            best_loc = loc
            # print(best_sc, best_loc)
    print(f'best_sc: {best_sc}, best_loc: {best_loc}')
    if best_sc > conf:
        return best_loc
    else:
        print(f"Match not found (max_val={best_sc:.4f})")
        return None

def draw_match_border(bg, sp1, sp2, sp3, loc1, loc2, loc3):
    bg = bg.copy()
    h1, w1 = sp1.shape[:2]
    h2, w2 = sp2.shape[:2]
    h3, w3 = sp3.shape[:2]
    cv2.rectangle(bg, loc1, (loc1[0] + w1, loc1[1] + h1), (0, 255, 0), 2)
    cv2.rectangle(bg, loc2, (loc2[0] + w2, loc2[1] + h2), (0, 255, 0), 2)
    cv2.rectangle(bg, loc3, (loc3[0] + w3, loc3[1] + h3), (0, 255, 0), 2)
    open('bg_gray_mark.png', 'wb').write(
        bytes(cv2.imencode('.png', bg)[1])
    )
    return bg

def find_vcode_pos(bg, sp, conf=0):
    """Find sprite position in background using template matching"""
    try:
        sp_hei, sp_wid = sp.shape[:2]
        sp = cv2.resize(
            sp, (int(sp_wid * 1.5), int(sp_hei * 1.5)), 
            interpolation=cv2.INTER_CUBIC
        )
        # Convert to grayscale
        # bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
        bg_hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
        sp_hsv = cv2.cvtColor(sp, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 0, 0])
        upper = np.array([179, 255, 50])
        bg2v = 255 - cv2.inRange(bg_hsv, lower, upper)
        sp2v = 255 - cv2.inRange(sp_hsv, lower, upper)
        '''
        bg_w_idcs = np.where(bg_mask == 0)
        sp_w_idcs = np.where(sp_mask == 0)
        bg[bg_w_idcs] = 255
        sp[sp_w_idcs] = 255
        '''
        sp_wid = sp.shape[1]
        sp_cell_wid = sp_wid // 3
        sp_pad = sp_wid // 12
        # bg2v = adathres(bg).astype(np.uint8)
        # sprite_gray = cv2.cvtColor(sprite_img, cv2.COLOR_BGR2GRAY)
        # sp2v = adathres(sp).astype(np.uint8)
        sp2v_1 = sp2v[:, sp_pad:sp_cell_wid]
        sp2v_2 = sp2v[:, sp_cell_wid:sp_cell_wid * 2]
        sp2v_3 = sp2v[:, sp_cell_wid * 2:sp_wid - sp_pad]
        '''
        open('bg_gray.png', 'wb').write(
            bytes(cv2.imencode('.png', bg2v)[1])
        )
        open('sprite_gray_1.png', 'wb').write(
            bytes(cv2.imencode('.png', sp2v_1)[1])
        )
        open('sprite_gray_2.png', 'wb').write(
            bytes(cv2.imencode('.png', sp2v_2)[1])
        )
        open('sprite_gray_3.png', 'wb').write(
            bytes(cv2.imencode('.png', sp2v_3)[1])
        )
        '''
        # Perform template matching
        loc1 = match_tmpl_rot(bg2v, sp2v_1)
        loc2 = match_tmpl_rot(bg2v, sp2v_2)
        loc3 = match_tmpl_rot(bg2v, sp2v_3)
        print(f'loc: {loc1}, {loc2}, {loc3}')
        # draw_match_border(bg, sp2v_1, sp2v_2, sp2v_3, loc1, loc2, loc3)
        return loc1, loc2, loc3
    except Exception as e:
        traceback.print_exc()
        return None, None, None

def tdc_collect(uid=""):
    """调用 tdc_collect.js 生成本地加密指纹。

    返回 dict: {collect, info, tokenid}
    collect  = /cap_union_new_verify 的 collect 参数（URL 编码的 base64, XXTEA 密文）
    info     = TDC.getInfo().info（176B base64 设备指纹）
    tokenid  = TDC.getInfo().tokenid（随机数:时间戳）
    """

    cmd = ["node", "tdc_collect.js"]
    if uid:
        cmd.append(f"--uid={uid}")
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
    if p.returncode != 0:
        raise RuntimeError(f"tdc_collect.js 执行失败: {p.stderr}")
    j = json.loads(p.stdout)
    return j


def pow_solve(prefix, leading=4, max_tries=5000000):
    """腾讯防水墙 PoW（浏览器 tcaptcha-frame 实现，非 tdc.js）。

    服务端下发 pow_cfg.prefix（如 "e8989caad44c4980#"），客户端暴力搜索 n，
    使 md5(prefix + str(n)) 的十六进制以 `leading` 个 '0' 开头。

    返回 (n, pow_answer)。pow_answer 按抓包观测的 `<md5前16hex>#<n>` 结构拼接；
    若服务端难度/格式不同，请在线对照真实请求调整。
    """
    for n in range(max_tries):
        h = hashlib.md5((prefix + str(n)).encode('ascii')).hexdigest()
        if h.startswith('0' * leading):
            return n, f"{h[:16]}#{n}"
    return None, None


def solve_captcha_retry(retry=100):
    for i in range(retry):
        try:
            print(f'solve_captcha() #{i+1}')
            vj = solve_captcha()
            if vj: return vj
        except:
            traceback.print_exc()
    return None

def solve_captcha():
    """Solve dynamic captcha point selection challenge"""
    # Get prehandle for this session
    pre_url = f"https://ca.turing.captcha.qcloud.com/cap_union_prehandle?aid=189979000&protocol=https&accver=1&showtype=popup&ua=TW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NDsgcnY6MTU4LjApIEdlY2tvLzIwMTAwMTAxIEZpcmVmb3gvMTU4LjA=&noheader=1&fb=0&aged=0&enableAged=0&isJsVersion=1&enableDarkMode=0&grayscale=1&clientype=2&userLanguage=zh-cn&cap_cd=&uid=&lang=zh-cn&entry_url=https%3A%2F%2Fplatform.agnes-ai.com%2Flogin&elder_captcha=0&js=%2Ftcaptcha-frame.211eaaf4.js&login_appid=&wb=1&subsid=3&callback=_"

    r = requests.get(pre_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://platform.agnes-ai.com/login"})
    if r.status_code != 200:
        print(f"Prehandle failed: {r.status_code}")
        return None

    # Parse response
    resp = r.text.strip()[2:-1]
    j = json.loads(resp)

    sess = j.get('sess', '')
    dyn = j.get('data', {}).get('dyn_show_info', {})
    bg_cfg = dyn.get('bg_elem_cfg', {})
    img_url = bg_cfg.get('img_url', '')
    sprite_url = dyn.get('sprite_url', '')
    comm_cfg = j.get('data', {}).get('comm_captcha_cfg', {})
    pow_cfg = comm_cfg.get('pow_cfg', {})

    # Download background and sprite
    bg_url = f"https://ca.turing.captcha.qcloud.com{img_url}"
    sprite_url = f"https://ca.turing.captcha.qcloud.com{sprite_url}"

    # Download images
    bg_img = cv2.imdecode(np.asarray(bytearray(requests.get(bg_url).content), dtype="uint8"), cv2.IMREAD_COLOR)
    sprite_img = cv2.imdecode(np.asarray(bytearray(requests.get(sprite_url).content), dtype="uint8"), cv2.IMREAD_COLOR)

    # Find position
    loc1, loc2, loc3 = find_vcode_pos(bg_img, sprite_img)
    if not loc1:
        return False

    # 点选验证码为 3 个可点击目标（ins_elem_cfg 仅声明图元，点击坐标来自 sprite 匹配）。
    # 背景图实际尺寸 == size_2d [672,480]，直接用背景像素坐标提交给服务端。
    bg_w, bg_h = bg_cfg.get('size_2d', [672, 480])
    bg_act_h, bg_act_w = bg_img.shape[:2]
    # find_vcode_pos 内部将 sprite 放大 1.5x 后按三格匹配，返回背景中的模板左上角 loc。
    # 点击中心 = loc + (放大后每格宽/2, 放大后高/2)。
    # sprite 宽 170 -> 放大后 255，每格约 85；高 50 -> 放大后 75。若服务端要求原始逻辑尺寸，缩放：
    sx = bg_w / bg_act_w
    sy = bg_h / bg_act_h
    tw, th = 170 * 1.5 / 3, 50 * 1.5   # 放大后每格宽、整格高
    def to_bg_pos(loc):
        x = loc[0] + tw / 2
        y = loc[1] + th / 2
        return int(x * sx), int(y * sy)

    cx1, cy1 = to_bg_pos(loc1)
    cx2, cy2 = to_bg_pos(loc2)
    cx3, cy3 = to_bg_pos(loc3)
    print(f"Click positions: ({cx1},{cy1}) ({cx2},{cy2}) ({cx3},{cy3})")

    # Construct verify request
    verify_url = "https://ca.turing.captcha.qcloud.com/cap_union_new_verify"

    # 生成加密指纹 collect（TDC.getData()），并从 getInfo 取 eks 候选
    tdc = tdc_collect()
    collect = tdc['collect']
    eks = tdc['info']          # eks 与 getInfo().info 等长(176B)、同框架；真实请求里 eks 为另一段动态指纹，此处用 info 兜底
    tlg = len(urllib.parse.unquote(collect))   # 抓包验证: tlg == len(decodeURIComponent(collect))

    # PoW
    pow_prefix = pow_cfg.get('prefix', '')
    pow_answer = ''
    pow_time = 0
    if pow_prefix:
        t0 = _time.time()
        n, pow_answer = pow_solve(pow_prefix)
        pow_time = int((_time.time() - t0) * 1000)
        print(f"PoW: n={n} answer={pow_answer} time={pow_time}ms")

    # Build parameters
    ans = json.dumps([
        {"elem_id": 1, "type": "DynAnswerType_POS", "data": f"{cx1},{cy1}"},
        {"elem_id": 2, "type": "DynAnswerType_POS", "data": f"{cx2},{cy2}"},
        {"elem_id": 3, "type": "DynAnswerType_POS", "data": f"{cx3},{cy3}"},
    ], separators=(',', ':'))
    params = {
        "collect": collect,
        "tlg": tlg,
        "eks": eks,
        "sess": sess,
        "ans": ans,
    }
    if pow_answer:
        params["pow_answer"] = pow_answer
        params["pow_calc_time"] = pow_time

    # Send verification
    r = requests.post(verify_url, data=params, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://platform.agnes-ai.com/login"})
    if r.status_code != 200:
        print(f"Verify failed: {r.status_code}")
        print(r.text[:500])
        return False

    # Parse response
    vj = r.json()
    if vj.get('errorCode') == "0":
        print(f"CAPTCHA solved: {cx1},{cy1} {cx2},{cy2} {cx3},{cy3}")
        print(f"  ticket={vj.get('ticket')} randstr={vj.get('randstr')}")
        return vj

    print(f"Verify response: {r.text[:500]}")
    return None

# 配置信息
WORKER_DOMAIN = "apimail.flygon.org"  # 替换为你的后台域名，比如我的，apimail.linuxdo.love
EMAIL_DOMAIN = "flygon.org" # 你的域名地址
ADMIN_PASSWORD = os.environ.get('CF_EMAIL_ADMIN_PW', '') # 你的管理员密码

def get_agnes_apikey(acckey):
    url = 'https://platform-backend.agnes-ai.com/api/token'
    data = {
        "api_key_profile":	"default",
        "name":	"dft",
    }
    hdrs = {
        "Authorization": f'Bearer {acckey}'
    }
    r = requests.post(url, json=data, headers=hdrs)
    if r.status_code >= 300:
        return None, f"HTTP {r.status_code}: {r.text}"
    j = r.json()
    if j['code'] == 200:
        return j['data']['key'], ""
    else:
        return None, j['message']

def reg_agnes(email, vcode, pwd):
    url = 'https://platform-backend.agnes-ai.com/api/user/register'
    data = {
        'code':	vcode,
        'email':	email,
        'password':	pwd,
        'password_confirm':	pwd,
    }
    r = requests.post(url, json=data)
    if r.status_code >= 300:
        return None, f"HTTP {r.status_code}: {r.text}"
    j = r.json()
    if j['code'] == 200:
        return j['data']['access_token'], ""
    else:
        return None, j['message']


def send_agnes_vcode(email):
    captcha = solve_captcha_retry()
    assert captcha is not None
    url = f'https://platform-backend.agnes-ai.com/api/verification'
    params = {
        'email': email,
        'purpose': 'register',
        'ticket': captcha['ticket'],
        'randstr': captcha['randstr'],
    }
    r = requests.get(url, params=params)
    if r.status_code >= 300:
        return f"HTTP {r.status_code}: {r.text}"
    j = r.json()
    if j['code'] == 200:
        return ''
    else:
        return j['message']


def generate_random_name():
    """生成随机邮箱名称"""
    letters1 = ''.join(random.choices(string.ascii_lowercase, k=5))  # 5个小写字母
    numbers = ''.join(random.choices(string.digits, k=random.randint(1, 3)))  # 1-3个数字
    letters2 = ''.join(random.choices(string.ascii_lowercase, k=random.randint(1, 3)))  # 1-3个小写字母
    return letters1 + numbers + letters2

def create_test_email():
    """创建测试邮箱"""
    try:
        random_name = generate_random_name()
        res = requests.post(
            f"https://{WORKER_DOMAIN}/admin/new_address",
            json={
                "enablePrefix": True,
                "name": random_name,
                "domain": EMAIL_DOMAIN,
            },
            headers={
                'x-admin-auth': ADMIN_PASSWORD,
                "Content-Type": "application/json"
            }
        )

        if res.status_code == 200:
            data = res.json()
            print("创建邮箱成功：")
            print(f"JWT: {data.get('jwt')}")
            print(f"邮箱地址: {data.get('address')}")
            return data.get('jwt'), data.get('address')
        else:
            print(f"创建邮箱失败: {res.status_code}")
            return None, None
    except Exception as e:
        print(f"创建邮箱出错: {e}")
        return None, None

def check_verification_code(jwt):
    """查看验证码"""
    limit = 10
    offset = 0
    res = requests.get(
        f"https://{WORKER_DOMAIN}/api/mails",
        params={
            "limit": limit,
            "offset": offset
        },
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json"
        }
    )

    if res.status_code != 200:
        print(f"获取邮件失败: {res.status_code}")
        return False, None

    data = res.json()
    # print("\n收到的邮件：")
    # print(json.dumps(data, indent=2))

    # 使用正则表达式提取验证码
    if not (data.get('results') and len(data['results']) > 0):
        print("邮件列表为空")
        return False, None

    raw_content = data['results'][0].get('raw', '')  # 获取最新邮件的raw内容
    # 使用更简单的正则表达式，直接匹配数字
    m = re.search(r'<div class=3D"verification-code">(\d{6})</div>', raw_content)
    if m:
        vcode = m.group(1)  # 获取第一个匹配的6位数字
        print(f"\n提取到的验证码: {vcode}")
        return True, vcode
    else:
        print("未找到验证码")
        return False, None


def reg_agnes_all():
    # 1. 创建测试邮箱
    jwt, email = create_test_email()
    if not jwt or not email:
        print("无法继续测试")
        return False

    print("\n创建的邮箱信息：")
    print(f"JWT: {jwt}")
    print(f"邮箱地址: {email}")
    open('cf_emails.txt', 'a', encoding='utf8').write(f'{email}----{jwt}\n')
    # 2. 等待一会儿，让邮件有时间送达
    errmsg = send_agnes_vcode(email)
    if errmsg:
        print(f'邮箱 {email} 发送 AGNES 验证码失败：{errmsg}')
        return False
    print("\n等待5秒钟让邮件送达...")
    sleep(5)

    # 3. 查看验证码
    success, vcode = check_verification_code(jwt)
    if success:
        print(f"成功获取验证码: {vcode}")
    else:
        print("获取验证码失败")
        return False


    pwd = generate_random_name() + generate_random_name()
    acckey, errmsg = reg_agnes(email, vcode, pwd)
    if errmsg:
        print(f'注册 AGNES 失败：{errmsg}')
        return False
    print(f'注册 AGNES 成功：{acckey}')
    apikey, errmsg = get_agnes_apikey(acckey)
    if errmsg:
        print(f'获取 APIKEY 失败：{errmsg}')
        return False
    print(f'获取 APIKEY 成功：{apikey}')
    dttmstr = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    open('agnes.txt', 'a', encoding='utf8') \
        .write(f'{dttmstr}----{email}----{pwd}----{acckey}----{apikey}\n')
    return True

def main():
    if not shutil.which('node'):
        print('请安装 NodeJS')
        return
    while True:
        succ = reg_agnes_all()
        if succ:
            sleep(10)
        else:
            sleep(600)
    # solve_captcha()


if __name__ == '__main__': main()