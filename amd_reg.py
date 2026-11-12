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
  2. Selenium + Firefox 打开注册页，填邮箱、选邮箱验证、点“发送验证码”
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

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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
# 阿里云滑块人机验证（Selenium + OpenCV，获取 CaptchaTicket 并触发发码）
# ---------------------------------------------------------------------------
def _match_slide_distance(bg: np.ndarray, slide: np.ndarray) -> int:
    """OpenCV 模板匹配，返回缺口中心在原始图中的 x 坐标。"""
    bg_g = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    slide_g = cv2.cvtColor(slide, cv2.COLOR_BGR2GRAY)

    # 去掉 slide 四周空白，只保留实图部分
    _, mask = cv2.threshold(slide_g, 10, 255, cv2.THRESH_BINARY)
    ys, xs = np.where(mask > 0)
    if len(xs) > 0:
        x0, x1 = xs.min(), xs.max()
        y0, y1 = ys.min(), ys.max()
        slide_crop = slide[y0:y1 + 1, x0:x1 + 1]
    else:
        slide_crop = slide
    slide_crop_g = cv2.cvtColor(slide_crop, cv2.COLOR_BGR2GRAY)

    res = cv2.matchTemplate(bg_g, slide_crop_g, cv2.TM_CCORR_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    gap_center_x = max_loc[0] + slide_crop.shape[1] / 2
    print(f"[captcha] match val={max_val:.4f} loc={max_loc}")
    return int(gap_center_x)


def solve_captcha_and_send_code(email: str,
                                manual_ticket: Optional[str] = None) -> Optional[str]:
    """用 Selenium 完成滑块验证，触发后台发码，返回 CaptchaTicket。

    流程：打开注册页 -> 填邮箱 -> 选邮箱验证 -> 点发送验证码 -> 出现滑块 ->
    OpenCV 定位缺口 -> 拖拽滑块 -> 验证成功 -> 后台自动调 SendVerificationCode 发码。

    若自动拖拽被风控拦截（ticket 为 None），则在控制台提示并等待用户手动完成滑块验证；
    手动完成后脚本会自动读取 ticket 并继续。也可直接传入 manual_ticket 跳过浏览器验证。
    """
    # 如果用户直接提供了 ticket，跳过浏览器流程
    if manual_ticket:
        print(f"[captcha] 使用手动提供的 ticket: {manual_ticket[:20]}...")
        return manual_ticket

    opts = Options()
    opts.headless = False
    opts.set_capability("pageLoadStrategy", "eager")
    opts.set_preference("dom.webdriver.enabled", False)
    opts.set_preference("useAutomationExtension", False)
    driver = webdriver.Firefox(options=opts)
    driver.set_window_size(1400, 900)

    wait = WebDriverWait(driver, 20)

    try:
        driver.get(
            "https://developer.amd.com.cn/register?"
            "returnUrl=https://developer.amd.com.cn/radeon/tokenfactory"
        )

        # 反自动化标记
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        # 填邮箱
        email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]')))
        email_input.clear()
        email_input.send_keys(email)

        # 选邮箱验证
        radios = driver.find_elements(By.CSS_SELECTOR, 'input[type="radio"][value="email"]')
        if radios:
            driver.execute_script("arguments[0].click();", radios[0])

        # 点发送验证码
        btns = driver.find_elements(By.XPATH, '//button')
        clicked = False
        for b in btns:
            txt = b.text.strip()
            if '验证码' in txt or 'Send Code' in txt:
                driver.execute_script("arguments[0].click();", b)
                clicked = True
                break
        if not clicked:
            print("[captcha] 未找到发送验证码按钮")
            return None

        # 安装 ticket 拦截器（等待 SDK 可用后再挂钩）
        driver.execute_script("""
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

        time.sleep(5)

        sdk_ready = driver.execute_script('return window.__amd_sdk_ready;')
        print(f"[captcha] SDK ready: {sdk_ready}")

        # 等待滑块图片出现
        deadline = time.time() + 15
        imgs_el = []
        while time.time() < deadline:
            imgs_el = driver.find_elements(By.CSS_SELECTOR, 'img[src^="data:image"]')
            if len(imgs_el) >= 2:
                break
            time.sleep(0.5)

        if len(imgs_el) < 2:
            print("[captcha] 滑块验证码图未出现")
            driver.save_screenshot('amd_captcha_noimg.png')
            return None

        bg_b64 = imgs_el[0].get_attribute('src').split(',', 1)[1]
        slide_b64 = imgs_el[1].get_attribute('src').split(',', 1)[1]
        bg = cv2.imdecode(np.frombuffer(base64.b64decode(bg_b64), np.uint8), cv2.IMREAD_COLOR)
        slide = cv2.imdecode(np.frombuffer(base64.b64decode(slide_b64), np.uint8), cv2.IMREAD_COLOR)
        print(f"[captcha] bg={bg.shape} slide={slide.shape}")

        bg_rect = imgs_el[0].rect
        scale_x = bg_rect['width'] / bg.shape[1]

        gap_center_orig_x = _match_slide_distance(bg, slide)
        gap_center_page_x = bg_rect['x'] + gap_center_orig_x * scale_x

        slider = driver.find_element(By.CSS_SELECTOR, '.slider-move')
        srect = slider.rect
        slider_center_x = srect['x'] + srect['width'] / 2
        distance = gap_center_page_x - slider_center_x
        print(f"[captcha] drag_distance={distance:.1f}")

        # 尝试自动拖拽
        if abs(distance) > 5:
            actions = ActionChains(driver)
            actions.move_to_element_with_offset(slider, srect['width'] // 2, srect['height'] // 2)
            actions.pause(0.2)
            actions.click_and_hold()
            actions.pause(0.1)

            adist = int(abs(distance))
            step_dir = 1 if distance > 0 else -1
            current = 0
            seg1 = int(adist * 0.7)
            while current < seg1:
                step = random.uniform(4, 8)
                current = min(current + step, seg1)
                actions.move_by_offset(int(step) * step_dir, random.randint(-3, 3))
                actions.pause(random.uniform(0.01, 0.05))
            actions.move_by_offset(-3 * step_dir, 0)
            actions.pause(0.1)
            while current < adist:
                step = random.uniform(0.3, 1.0)
                current = min(current + step, adist)
                actions.move_by_offset(int(step) * step_dir, 0)
                actions.pause(random.uniform(0.05, 0.1))
            actions.pause(0.2)
            actions.release()
            actions.perform()
            print("[captcha] drag performed")
            time.sleep(5)

        ticket = driver.execute_script('return window.__amd_captcha_ticket;')
        if ticket:
            print(f"[captcha] ticket obtained: {ticket[:20]}...")
            driver.save_screenshot('amd_captcha_done.png')
            return ticket

        # 自动拖拽失败 -> 等待用户手动完成滑块验证
        print("[captcha] 自动拖拽未获得 ticket，请在浏览器中手动完成滑块验证...")
        print("[captcha] 脚本将每 2 秒检查一次 ticket，手动拖滑块成功后会自动继续")
        deadline = time.time() + 120  # 最多等待 2 分钟
        while time.time() < deadline:
            ticket = driver.execute_script('return window.__amd_captcha_ticket;')
            if ticket:
                print(f"[captcha] manual ticket obtained: {ticket[:20]}...")
                driver.save_screenshot('amd_captcha_manual_done.png')
                return ticket
            time.sleep(2)

        print("[captcha] 等待超时，未获得 ticket")
        driver.save_screenshot('amd_captcha_timeout.png')
        return None

    finally:
        driver.quit()


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
