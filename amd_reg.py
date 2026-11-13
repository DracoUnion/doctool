"""AMD AI 开发者计划注册机.

逆向自 https://developer.amd.com.cn/register
接口（基础 URL https://developer.amd.com.cn/api）：
  1. GET  /api/Aliyun/GetEncryptedSceneId      -> {Data:{SceneId, EncryptedSceneId, ...}}
  2. POST /api/User/SendVerificationCode       -> {TelOrEmail, Type:1, CaptchaTicket}
                                                   CaptchaTicket 需先通过阿里云滑块人机验证获得
  3. POST /api/User/Register                   -> {LastName, FirstName, PhoneNumber, Email,
                                                   VerificationMethod, VerificationCode,
                                                   CaptchaTicket:"", AcceptedPrivacyStatement,
                                                   IsEmailSubscribed, OpenId, Source, InviteCode}

流程：
  1. 通过飞鸟邮箱 worker 创建一次性邮箱（同 agnes_reg.py）
  2. Camoufox（Firefox 内核，更真实指纹）打开注册页，填邮箱、选邮箱验证、点“发送验证码”
  3. OpenCV 定位滑块缺口，模拟人类拖拽完成人机验证 -> 后台向邮箱下发 6 位验证码
     若自动拖拽被风控拦截，可手动输入已获取的 CaptchaTicket 继续
  4. 收邮件提取验证码
  5. 调 Register 接口完成注册

姓名和手机号随机生成；验证方式固定选邮箱。

用法：
    export CF_EMAIL_ADMIN_PW=你的飞鸟管理员密码
    python amd_reg.py          # 循环注册
    python -c "import amd_reg; amd_reg.reg_amd_all()"  # 跑一次
"""

from __future__ import annotations

import base64
import os
import random
import re
import string
import time
from datetime import datetime
from typing import Any, Optional

import cv2
import numpy as np
import requests

from camoufox.sync_api import Camoufox
from camoufox import launch_options as _camoufox_launch_options
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# 浏览器 profile：复用已信任 developer.amd.com.cn 证书的 cert8.db
# 该站点 DigiCert/GeoTrust 证书链在全新 Firefox profile 中 TLS 握手失败，
# 需把含证书例外的 cert8.db 注入 Camoufox 启动用的 profile 才能稳定访问。
# ---------------------------------------------------------------------------
FIREFOX_PROFILE_DIR = os.environ.get(
    "AMD_FIREFOX_PROFILE",
    os.path.join(os.path.expanduser("~"), "amd_ff_profile"),
)


def _ensure_trusted_profile() -> str:
    """确保 profile 目录里有已信任 AMD 证书的 cert8.db。

    优先从系统 Firefox 默认 profile 拷贝（那里存了证书例外）；
    若找不到，回退到环境变量 AMD_FIREFOX_PROFILE 指向的目录。
    """
    os.makedirs(FIREFOX_PROFILE_DIR, exist_ok=True)
    target = os.path.join(FIREFOX_PROFILE_DIR, "cert8.db")
    if os.path.exists(target):
        return FIREFOX_PROFILE_DIR
    # 尝试从系统 Firefox 拷贝
    candidates = [
        os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox",
                     "Profiles"),
    ]
    for base in candidates:
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            src = os.path.join(base, entry, "cert8.db")
            if os.path.exists(src):
                import shutil
                shutil.copy(src, target)
                print(f"[profile] 从 {src} 拷贝 cert8.db -> {FIREFOX_PROFILE_DIR}")
                return FIREFOX_PROFILE_DIR
    print(f"[profile] 未找到系统 cert8.db，使用空 profile {FIREFOX_PROFILE_DIR}（证书可能仍不信任）")
    return FIREFOX_PROFILE_DIR


def _launch_trusted_camoufox():
    """启动 Camoufox 持久化上下文，复用已信任证书的 profile。

    返回 (playwright, BrowserContext, page)；调用方负责 close context 与
    playwright.stop()。握手可能仍间歇失败，故内置重试。
    """
    prof = _ensure_trusted_profile()
    opts = _camoufox_launch_options(headless=False, locale="zh-CN")
    opts.pop("executable_path", None)
    opts.pop("user_data_dir", None)
    opts["no_viewport"] = True

    last_err = None
    for attempt in range(3):
        pw = sync_playwright().start()
        ctx = None
        try:
            ctx = pw.firefox.launch_persistent_context(prof, **opts)
            page = ctx.new_page()
            # 在导航前注入 ticket 拦截器（init script 先于页面 SDK 运行）
            page.add_init_script("""
            window.__amd_captcha_ticket = null;
            const _installInterceptor = () => {
                if (typeof window.initAliyunCaptcha === 'function' && !window.__amd_hooked) {
                    window.__amd_hooked = true;
                    const orig = window.initAliyunCaptcha;
                    window.initAliyunCaptcha = function(cfg) {
                        if (cfg && cfg.success) {
                            const s = cfg.success;
                            cfg.success = function(res) {
                                window.__amd_captcha_ticket =
                                    res && res.captchaTicket ? res.captchaTicket : null;
                                if (s) s(res);
                            };
                        }
                        return orig(cfg);
                    };
                }
            };
            const _poll = () => { _installInterceptor();
                if (!window.__amd_hooked) setTimeout(_poll, 200); };
            _poll();
            """)
            page.goto(
                "https://developer.amd.com.cn/register?"
                "returnUrl=https://developer.amd.com.cn/radeon/tokenfactory",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            print(f"[captcha] 页面加载成功（第 {attempt + 1} 次）")
            return pw, ctx, page
        except Exception as e:
            last_err = str(e).splitlines()[0][:120]
            print(f"[captcha] 第 {attempt + 1} 次失败: {last_err}")
            try:
                if ctx:
                    ctx.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass
            time.sleep(2)
    raise RuntimeError(f"无法访问注册页: {last_err}")


# ---------------------------------------------------------------------------
# 飞鸟邮箱配置（与 agnes_reg.py 保持一致，替换为你自己的后台域名/密码）
# ---------------------------------------------------------------------------
WORKER_DOMAIN = "apimail.flygon.org"  # 替换为你的后台域名
EMAIL_DOMAIN = "flygon.org"  # 你的域名地址
ADMIN_PASSWORD = os.environ.get('CF_EMAIL_ADMIN_PW', '')

# ---------------------------------------------------------------------------
# AMD 接口
# ---------------------------------------------------------------------------
BASE = "https://developer.amd.com.cn/api"
SEND_CODE_URL = BASE + "/api/User/SendVerificationCode"
REGISTER_URL = BASE + "/api/User/Register"
SCENE_URL = BASE + "/api/Aliyun/GetEncryptedSceneId"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0"


def http_get_json(url: str, params: dict | None = None,
                  headers: dict | None = None) -> dict[str, Any]:
    hdrs = {"User-Agent": UA, "Referer": "https://developer.amd.com.cn/register",
            "Origin": "https://developer.amd.com.cn"}
    if headers:
        hdrs.update(headers)
    r = requests.get(url, params=params, headers=hdrs, timeout=30, verify=False)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def http_post_json(url: str, data: dict[str, Any],
                   headers: dict | None = None) -> dict[str, Any]:
    hdrs = {"User-Agent": UA, "Content-Type": "application/json",
            "Referer": "https://developer.amd.com.cn/register",
            "Origin": "https://developer.amd.com.cn"}
    if headers:
        hdrs.update(headers)
    r = requests.post(url, json=data, headers=hdrs, timeout=30, verify=False)
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def get_scene_id() -> dict[str, str]:
    """获取阿里云验证码场景 ID。"""
    j = http_get_json(SCENE_URL)
    data = j.get("Data", {})
    return {
        "scene_id": data.get("SceneId", ""),
        "encrypted_scene_id": data.get("EncryptedSceneId", ""),
        "timestamp": str(data.get("Timestamp", "")),
    }


# ---------------------------------------------------------------------------
# 邮箱（同 agnes_reg.py）
# ---------------------------------------------------------------------------
def generate_random_name() -> str:
    letters1 = ''.join(random.choices(string.ascii_lowercase, k=5))
    numbers = ''.join(random.choices(string.digits, k=random.randint(1, 3)))
    letters2 = ''.join(random.choices(string.ascii_lowercase, k=random.randint(1, 3)))
    return letters1 + numbers + letters2


def create_test_email() -> tuple[Optional[str], Optional[str]]:
    """创建测试邮箱，返回 (jwt, address)。"""
    try:
        random_name = generate_random_name()
        res = requests.post(
            f"https://{WORKER_DOMAIN}/admin/new_address",
            json={"enablePrefix": True, "name": random_name, "domain": EMAIL_DOMAIN},
            headers={"x-admin-auth": ADMIN_PASSWORD, "Content-Type": "application/json"},
            timeout=30,
        )
        if res.status_code == 200:
            data = res.json()
            print(f"创建邮箱成功：{data.get('address')}")
            return data.get("jwt"), data.get("address")
        else:
            print(f"创建邮箱失败: {res.status_code} {res.text[:200]}")
            return None, None
    except Exception as e:
        print(f"创建邮箱出错: {e}")
        return None, None


def check_verification_code(jwt: str) -> tuple[bool, Optional[str]]:
    """收邮件，提取 6 位验证码。"""
    limit = 10
    offset = 0
    res = requests.get(
        f"https://{WORKER_DOMAIN}/api/mails",
        params={"limit": limit, "offset": offset},
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        timeout=30,
    )
    if res.status_code != 200:
        print(f"获取邮件失败: {res.status_code}")
        return False, None
    data = res.json()
    if not (data.get('results') and len(data['results']) > 0):
        print("邮件列表为空")
        return False, None
    raw_content = data['results'][0].get('raw', '')
    m = re.search(r'<div class=3D"verification-code">(\d{6})</div>', raw_content)
    if not m:
        m = re.search(r'(\d{6})', raw_content)
    if m:
        vcode = m.group(1)
        print(f"提取到的验证码: {vcode}")
        return True, vcode
    print("未找到验证码")
    return False, None


# ---------------------------------------------------------------------------
# 阿里云滑块人机验证（Camoufox + OpenCV，获取 CaptchaTicket 并触发发码）
# ---------------------------------------------------------------------------
def _find_gap_x(bg: np.ndarray) -> int:
    """检测背景图中拼图缺口的中心 x 坐标（原始图像素）。

    缺口是比周围更亮的拼图形状洞。用 HSV（高亮 + 低饱和）找亮区连通块，
    取中右区域（rel_x ∈ [0.45, 0.85]，0.85 封顶排除右上角天空亮块）里
    面积最大的块作为缺口。模板匹配对带暗边的滑块片不可靠（匹配到深色
    树/地面而非缺口），故改用缺口本身的亮色特征定位。
    """
    h, w = bg.shape[:2]
    hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
    v, s = hsv[:, :, 2], hsv[:, :, 1]
    mask = ((v > 180) & (s < 70)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    num, _labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, num):
        _x, _y, ww, hh, area = stats[i]
        if area < 300 or area > 3500:
            continue
        if ww < 15 or hh < 15:
            continue
        cx = cents[i][0]
        if cx < 0.45 * w or cx > 0.85 * w:
            continue
        if best is None or area > best[0]:
            best = (area, cx)
    if best:
        return int(best[1])
    return int(w * 0.65)


def solve_captcha_and_send_code(email: str,
                                manual_ticket: Optional[str] = None) -> Optional[str]:
    """用 Camoufox（Firefox 内核，更真实指纹）完成滑块验证，触发后台发码，返回 CaptchaTicket。

    流程：打开注册页 -> 填邮箱 -> 选邮箱验证 -> 点发送验证码 -> 出现滑块 ->
    OpenCV 定位缺口 -> 拖拽滑块 -> 验证成功 -> 后台自动调 SendVerificationCode 发码。

    该站点证书链由 DigiCert/GeoTrust 签发，全新 Firefox profile 在 TLS 握手阶段
    报 SSL_ERROR_UNKNOWN。解决：把已含该站点证书例外的 cert8.db 注入 Camoufox
    启动用的持久化 profile（默认 ~/.amd_ff_profile，可从系统 Firefox profile 自动
    拷贝），用 launch_persistent_context 复用该 profile 即可稳定访问。

    若自动拖拽被风控拦截（ticket 为 None），则在控制台提示并等待用户手动完成滑块验证；
    手动完成后脚本会自动读取 ticket 并继续。也可直接传入 manual_ticket 跳过浏览器验证。
    """
    # 如果用户直接提供了 ticket，跳过浏览器流程
    if manual_ticket:
        print(f"[captcha] 使用手动提供的 ticket: {manual_ticket[:20]}...")
        return manual_ticket

    # 启动 Camoufox（持久化上下文 + 已信任证书的 profile），访问注册页
    try:
        pw, ctx, page = _launch_trusted_camoufox()
    except Exception as e:
        print(f"[captcha] {e}")
        return None

    try:
        # 在 SDK 初始化前注入 ticket 拦截器（init script 在导航前运行）
        # _launch_trusted_camoufox 里已通过 add_init_script 注入；
        # 这里兜底再补一次（幂等，已挂钩则跳过）
        page.evaluate("""
        window.__amd_captcha_ticket = window.__amd_captcha_ticket || null;
        """)

        # 填邮箱
        email_input = page.locator('input[type="email"]').first
        email_input.wait_for(state="visible", timeout=15000)
        email_input.fill("")
        email_input.type(email, delay=20)

        # 选邮箱验证
        radios = page.locator('input[type="radio"][value="email"]')
        if radios.count() > 0:
            radios.first.click()

        # 点发送验证码
        btns = page.locator('button').all()
        clicked = False
        for b in btns:
            try:
                txt = b.inner_text().strip()
            except Exception:
                continue
            if '验证码' in txt or 'Send Code' in txt:
                b.click()
                clicked = True
                break
        if not clicked:
            print("[captcha] 未找到发送验证码按钮")
            return None

        # 安装 ticket 拦截器（在 SDK 可用后挂钩 initAliyunCaptcha）
        page.add_script_tag(content="""
        window.__amd_captcha_ticket = null;
        window.__amd_sdk_ready = false;
        const waitForSDK = () => {
            if (typeof window.initAliyunCaptcha === 'function' && !window.__amd_sdk_ready) {
                window.__amd_sdk_ready = true;
                const orig = window.initAliyunCaptcha;
                window.initAliyunCaptcha = function(cfg) {
                    const origGetInstance = cfg.getInstance;
                    cfg.getInstance = function(inst) {
                        window.__amd_instance = inst;
                        if (origGetInstance) origGetInstance(inst);
                    };
                    const origSuccess = cfg.success;
                    cfg.success = function(res) {
                        window.__amd_captcha_ticket = res && res.captchaTicket ? res.captchaTicket : null;
                        if (origSuccess) origSuccess(res);
                    };
                    return orig(cfg);
                };
                console.log('SDK interceptor installed');
            } else if (!window.__amd_sdk_ready) {
                setTimeout(waitForSDK, 200);
            }
        };
        waitForSDK();
        """)

        page.wait_for_timeout(5000)

        sdk_ready = page.evaluate("window.__amd_sdk_ready")
        print(f"[captcha] SDK ready: {sdk_ready}")

        # 等待滑块图片出现
        deadline = time.time() + 15
        imgs_el = []
        while time.time() < deadline:
            imgs_el = page.locator('img[src^="data:image"]').all()
            if len(imgs_el) >= 2:
                break
            page.wait_for_timeout(500)

        if len(imgs_el) < 2:
            print("[captcha] 滑块验证码图未出现")
            page.screenshot(path='amd_captcha_noimg.png')
            return None

        bg_src = imgs_el[0].get_attribute("src")
        slide_src = imgs_el[1].get_attribute("src")
        bg_b64 = bg_src.split(',', 1)[1]
        slide_b64 = slide_src.split(',', 1)[1]
        bg = cv2.imdecode(np.frombuffer(base64.b64decode(bg_b64), np.uint8), cv2.IMREAD_COLOR)
        slide = cv2.imdecode(np.frombuffer(base64.b64decode(slide_b64), np.uint8), cv2.IMREAD_COLOR)
        print(f"[captcha] bg={bg.shape} slide={slide.shape}")

        # 背景图在页面上的显示位置（用于把原始图坐标映射到页面坐标）
        box = imgs_el[0].bounding_box()
        if box is None:
            print("[captcha] 无法获取背景图位置")
            return None
        scale_x = box["width"] / bg.shape[1]

        gap_center_orig_x = _find_gap_x(bg)
        print(f"[captcha] gap_x(orig)={gap_center_orig_x} bg_w={bg.shape[1]}")
        gap_center_page_x = box["x"] + gap_center_orig_x * scale_x

        slider = page.locator('.slider-move').first
        sb = slider.bounding_box()
        if sb is None:
            print("[captcha] 无法获取滑块位置")
            return None
        slider_center_x = sb["x"] + sb["width"] / 2
        distance = gap_center_page_x - slider_center_x
        print(f"[captcha] drag_distance={distance:.1f}")

        # 尝试自动拖拽
        if abs(distance) > 5:
            # 移动到滑块中心并按下
            page.mouse.move(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2)
            page.mouse.down()

            adist = int(abs(distance))
            step_dir = 1 if distance > 0 else -1
            current = 0
            seg1 = int(adist * 0.7)
            while current < seg1:
                step = random.uniform(4, 8)
                current = min(current + step, seg1)
                page.mouse.move(
                    sb["x"] + sb["width"] / 2 + current * step_dir,
                    sb["y"] + sb["height"] / 2 + random.randint(-3, 3),
                )
                page.wait_for_timeout(random.uniform(10, 50))
            # 小回退
            page.mouse.move(
                sb["x"] + sb["width"] / 2 + seg1 * step_dir - 3 * step_dir,
                sb["y"] + sb["height"] / 2,
            )
            page.wait_for_timeout(100)
            # 最后精确段
            while current < adist:
                step = random.uniform(0.3, 1.0)
                current = min(current + step, adist)
                page.mouse.move(
                    sb["x"] + sb["width"] / 2 + current * step_dir,
                    sb["y"] + sb["height"] / 2,
                )
                page.wait_for_timeout(random.uniform(50, 100))
            page.wait_for_timeout(200)
            page.mouse.up()
            print("[captcha] drag performed")
            page.wait_for_timeout(5000)

        ticket = page.evaluate("window.__amd_captcha_ticket")
        if ticket:
            print(f"[captcha] ticket obtained: {ticket[:20]}...")
            page.screenshot(path='amd_captcha_done.png')
            return ticket

        # 自动拖拽失败 -> 等待用户手动完成滑块验证
        print("[captcha] 自动拖拽未获得 ticket，请在浏览器中手动完成滑块验证...")
        print("[captcha] 脚本将每 2 秒检查一次 ticket，手动拖滑块成功后会自动继续")
        deadline = time.time() + 120  # 最多等待 2 分钟
        while time.time() < deadline:
            ticket = page.evaluate("window.__amd_captcha_ticket")
            if ticket:
                print(f"[captcha] manual ticket obtained: {ticket[:20]}...")
                page.screenshot(path='amd_captcha_manual_done.png')
                return ticket
            page.wait_for_timeout(2000)

        print("[captcha] 等待超时，未获得 ticket")
        page.screenshot(path='amd_captcha_timeout.png')
        return None

    finally:
        try:
            ctx.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def send_verification_code(email: str, ticket: str) -> tuple[bool, str]:
    """调用 SendVerificationCode 接口下发验证码。"""
    try:
        try:
            scene = get_scene_id()
        except Exception:
            scene = {}
        data = {
            "TelOrEmail": email,
            "Type": 1,
            "CaptchaTicket": ticket,
        }
        j = http_post_json(SEND_CODE_URL, data)
        status = j.get("Status")
        msg = j.get("Message", "")
        if status == 1:
            print(f"验证码已发送: {msg}")
            return True, ""
        else:
            print(f"发码失败 status={status}: {msg}")
            return False, str(msg)
    except Exception as e:
        print(f"send_verification_code 异常: {e}")
        return False, str(e)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
def reg_amd(email: str, vcode: str) -> tuple[Optional[str], str]:
    """调用 Register 接口注册 AMD 账户，返回 (access_token, errmsg)。"""
    last = generate_random_name().capitalize()
    first = generate_random_name().capitalize()
    phone = "138" + ''.join(random.choices(string.digits, k=8))
    data = {
        "HeaderImg": "",
        "LastName": last,
        "FirstName": first,
        "PhoneNumber": phone,
        "Email": email,
        "VerificationMethod": "email",
        "VerificationCode": vcode,
        "CaptchaTicket": "",
        "AcceptedPrivacyStatement": True,
        "IsEmailSubscribed": False,
        "OpenId": "",
        "Source": "",
        "InviteCode": "",
    }
    try:
        j = http_post_json(REGISTER_URL, data)
    except Exception as e:
        return None, str(e)
    status = j.get("Status")
    if status == 1:
        token = j.get("Data", "")
        print(f"注册成功: {email}  token={str(token)[:40]}")
        return token, ""
    else:
        return None, j.get("Message", "未知错误")


def reg_amd_all(manual_ticket: Optional[str] = None) -> bool:
    """完整注册流程。

    Args:
        manual_ticket: 可选，手动提供的 CaptchaTicket（用于自动拖拽失败时）
    """
    jwt, email = create_test_email()
    if not jwt or not email:
        print("无法继续：创建邮箱失败")
        return False

    print(f"邮箱: {email}")

    # 1. 滑块验证 + 发码（获取 ticket 并触发后台发码）
    ticket = solve_captcha_and_send_code(email, manual_ticket=manual_ticket)
    if not ticket:
        print("未获得 CaptchaTicket，无法发送验证码")
        return False

    # 2. 调 SendVerificationCode 下发验证码（如果前端自动触发失败，这里补调一次）
    ok, err = send_verification_code(email, ticket)
    if not ok:
        print(f"调用发码接口失败: {err}")
        return False

    # 3. 收邮件取验证码
    print("等待验证码邮件送达...")
    time.sleep(5)
    success, vcode = check_verification_code(jwt)
    if not success:
        print("获取验证码失败")
        return False

    # 4. 注册
    token, err = reg_amd(email, vcode)
    if err:
        print(f"注册失败: {err}")
        return False
    print(f"注册成功: {email}")
    dttmstr = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open('amd.txt', 'a', encoding='utf8') as f:
        f.write(f'{dttmstr}----{email}----{token}\n')
    return True


def main():
    if not ADMIN_PASSWORD:
        print("请设置环境变量 CF_EMAIL_ADMIN_PW")
        return
    while True:
        succ = reg_amd_all()
        if succ:
            time.sleep(10)
        else:
            time.sleep(600)


if __name__ == '__main__':
    main()
