"""AMD AI 开发者计划注册机（AMD 中国站 developer.amd.com.cn，改用 Outlook 邮箱）。

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
  1. 从 outlook_emails.txt 读取 Outlook 账号（作为注册邮箱 + 收信账号）
  2. Camoufox（Firefox 内核）打开注册页，填邮箱、选邮箱验证、点“发送验证码”
  3. OpenCV 定位滑块缺口，模拟人类拖拽完成人机验证 -> 后台向邮箱下发 6 位验证码
     若自动拖拽被风控拦截，可手动输入已获取的 CaptchaTicket 继续
  4. Outlook IMAP OAuth2 收邮件，提取 6 位验证码
  5. 调 Register 接口完成注册

姓名和手机号随机生成；验证方式固定选邮箱。

用法：
    export CF_EMAIL_ADMIN_PW=（已不再需要，保留兼容）
    python amd_reg.py          # 循环注册
    python -c "import amd_reg; amd_reg.reg_amd_all()"  # 跑一次
"""

from __future__ import annotations

import base64
import traceback
import imaplib
import os
import random
import re
import string
import time
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from typing import Optional
from BookerDownloadTool.util import camou_create_driver
from contextlib import contextmanager

import cv2
import numpy as np
import requests

from camoufox.sync_api import Camoufox
from camoufox import launch_options as _camoufox_launch_options

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

@contextmanager
def _launch_trusted_camoufox():
    """启动 Camoufox（普通 camoufox，非 playwright 直连 firefox），复用已信任证书的 profile。

    返回 (Camoufox, Page)；调用方负责在 finally 里对 Camoufox 调用 __exit__() 清理。
    内置重试，对付间歇性 TLS 握手失败。
    """
    prof = _ensure_trusted_profile()
    opts = _camoufox_launch_options(headless=False, locale="zh-CN")
    # 使用已放好 cert8.db 的持久化 profile，解决 DigiCert/GeoTrust 证书链 TLS 握手失败
    opts["user_data_dir"] = prof
    opts["persistent_context"] = True
    opts.pop("executable_path", None)
    opts["no_viewport"] = True

    with Camoufox(**opts) as browser:
        browser.clear_cookies()
        page = browser.new_page()
        page.goto(
            "https://developer.amd.com.cn/register?"
            "returnUrl=https://developer.amd.com.cn/radeon/tokenfactory",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        try:
            yield browser, page
        finally:
            page.close()
            browser.close()


# ---------------------------------------------------------------------------
# AMD 中国站接口
# ---------------------------------------------------------------------------
BASE = "https://developer.amd.com.cn/api"
SEND_CODE_URL = BASE + "/api/User/SendVerificationCode"
REGISTER_URL = BASE + "/api/User/Register"
SCENE_URL = BASE + "/api/Aliyun/GetEncryptedSceneId"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0"


# ---------------------------------------------------------------------------
# 账号/随机数据生成
# ---------------------------------------------------------------------------
def generate_random_name() -> str:
    letters1 = ''.join(random.choices(string.ascii_lowercase, k=5))
    numbers = ''.join(random.choices(string.digits, k=random.randint(1, 3)))
    letters2 = ''.join(random.choices(string.ascii_lowercase, k=random.randint(1, 3)))
    return letters1 + numbers + letters2



def _load_outlook_accounts(path: str = "outlook_emails.txt") -> list[tuple[str, str, str]]:
    """读取 Outlook 账号，每行 EMAIL----placeholder----CLIENT_ID----REFRESH_TOKEN。"""
    accounts = []
    if not os.path.exists(path):
        print(f"[outlook] 未找到 {path}，请按 EMAIL--------CLIENT_ID----REFRESH_TOKEN 格式准备")
        return accounts
    with open(path, encoding="utf8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("----")
            if len(parts) >= 4:
                email, _, client_id, refresh_token = parts[0], parts[1], parts[2], parts[3]
                accounts.append((email, client_id, refresh_token))
    print(f"[outlook] 加载 {len(accounts)} 个账号")
    return accounts


def _next_outlook_account(path: str = "outlook_emails.txt") -> Optional[tuple[str, str, str]]:
    global _OUTLOOK_ACCOUNTS, _OUTLOOK_IDX
    if not _OUTLOOK_ACCOUNTS:
        _OUTLOOK_ACCOUNTS = _load_outlook_accounts(path)
    if not _OUTLOOK_ACCOUNTS:
        return None
    acct = _OUTLOOK_ACCOUNTS[_OUTLOOK_IDX % len(_OUTLOOK_ACCOUNTS)]
    _OUTLOOK_IDX += 1
    return acct


# ---------------------------------------------------------------------------
# Outlook IMAP OAuth2：收取验证码邮件，提取 6 位验证码
# ---------------------------------------------------------------------------
def _get_access_token(email: str, client_id: str, refresh_token: str,
                      tenant: str = "consumers") -> Optional[str]:
    """使用 refresh_token 换取短期 access_token。"""
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    try:
        res = requests.post(url, data=data, timeout=15)
        if res.status_code != 200:
            print(f"[outlook] 换取 Access Token 失败: {res.status_code} {res.text[:200]}")
            return None
        token = res.json().get("access_token")
        if not token:
            print(f"[outlook] 响应无 access_token: {res.json()}")
            return None
        return token
    except Exception as e:
        print(f"[outlook] 换取 Access Token 异常: {e}")
        return None


def _build_auth_string(email: str, access_token: str) -> bytes:
    """构造 XOAUTH2 认证字符串。"""
    # 格式: user=<email>\x01auth=Bearer <access_token>\x01\x01
    auth_string = f"user={email}\x01auth=Bearer {access_token}\x01\x01"
    return auth_string.encode("utf-8")


def _parse_email_date(date_str: str):
    """解析邮件 Date 头，转为带时区的 datetime。"""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _extract_code_from_email(content: str) -> Optional[str]:
    """从邮件正文中提取 6 位数字验证码。

    AMD 验证码邮件的 HTML 头部包含 CSS 样式表，其中的颜色值（如
    #111827、#6b7280）里也含有六位数字，会干扰提取。真正的验证码
    放在 HTML 尾部的 <span> 标签内（如 <span ...>288136</span>）。
    策略：扫描全文所有纯数字 6 位，排除常见噪声后取**最后一个**。
    因为 CSS 颜色值都在头部，验证码在尾部，最后一个六位数字即为验证码。
    """
    # 优先匹配6位纯数字，其次匹配6位大写字母+数字
    # 取最后一个
    vcodes = re.findall(r"\b(\d{6})\b", content)
    if vcodes:
        return vcodes[-1]
    vcodes = re.findall(r"\b([A-Z0-9]{6})\b", content)
    if vcodes:
        return vcodes[-1]
    return None


def _check_mailbox_for_code(imap, mailbox: str, since_time,
                            max_check: int = 5) -> Optional[str]:
    """在指定邮箱中搜索最近邮件，提取验证码。找到则返回，否则返回 None。

    仅检查最新的 max_check 封邮件（按 ID 逆序，即最新的优先），并打印
    主题与 Date 方便确认是本次注册的验证码邮件。
    """
    try:
        status, _ = imap.select(mailbox, readonly=True)
        if status != "OK":
            print(f"[outlook] 选择 {mailbox} 失败: {status}")
            return None
    except Exception as ex:
        print(f"[outlook] 选择 {mailbox} 异常: {ex}")
        return None

    status, data = imap.search(None, "ALL")
    if status != "OK" or not data or not data[0]:
        print(f"[outlook] {mailbox} 搜索失败: {status}")
        return None
    ids = data[0].split()
    if not ids:
        print(f"[outlook] {mailbox} 无邮件")
        return None

    recent_ids = ids[-max_check:] if len(ids) > max_check else ids
    print(f"[outlook] {mailbox} 最近 {len(recent_ids)} 封邮件，按时间逆序检查 ...")
    for msg_id in reversed(recent_ids):
        status, msg_data = imap.fetch(msg_id, "(RFC822)")
        if status != "OK" or not msg_data:
            continue
        raw_bytes = None
        for item in msg_data:
            if isinstance(item, tuple) and len(item) > 1:
                raw_bytes = item[1]
                break
        if not raw_bytes:
            continue

        msg = message_from_bytes(raw_bytes)
        msg_date = _parse_email_date(msg.get("Date"))
        subject = (msg.get("Subject") or "").strip()
        if msg_date and msg_date < since_time:
            print(f"[outlook] {mailbox} {msg_id.decode() if isinstance(msg_id, bytes) else msg_id} 邮件太旧 ({msg_date})，跳过，主题='{subject}'")
            continue

        # 提取正文（优先 text/plain，其次 text/html）
        content = ""
        if msg.is_multipart():
            plain_parts = []
            html_parts = []
            for part in msg.walk():
                ctype = part.get_content_type()
                try:
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    text = payload.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if ctype == "text/plain":
                    plain_parts.append(text)
                elif ctype == "text/html":
                    html_parts.append(text)
            content = "\n".join(plain_parts) if plain_parts else "\n".join(html_parts)
        else:
            try:
                payload = msg.get_payload(decode=True)
                content = payload.decode("utf-8", errors="ignore") if payload else ""
            except Exception:
                content = ""

        code = _extract_code_from_email(content)
        if code:
            print(f"[outlook] 在 {mailbox} 最新邮件提取到验证码: {code} (主题='{subject}', 日期={msg_date})")
            return code
        print(f"[outlook] {mailbox} {msg_id.decode() if isinstance(msg_id, bytes) else msg_id} 未提取到验证码，主题='{subject}', 正文片段: {content[:200]}")

    return None


def fetch_verification_code(email: str, client_id: str, refresh_token: str,
                            since_minutes: int = 3,
                            max_check: int = 5,
                            poll_interval: int = 10,
                            max_wait_seconds: int = 180) -> Optional[str]:
    """通过 Outlook IMAP OAuth2 收取验证码邮件，提取 6 位验证码。

    邮件可能有延迟，故内置轮询：每 poll_interval 秒检查一次，最多等待
    max_wait_seconds 秒。
    """
    access_token = _get_access_token(email, client_id, refresh_token)
    if not access_token:
        return None

    auth_string = _build_auth_string(email, access_token)
    since_time = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    deadline = time.time() + max_wait_seconds

    while time.time() < deadline:
        imap = imaplib.IMAP4_SSL("outlook.office365.com", 993)
        try:
            imap.authenticate("XOAUTH2", lambda _: auth_string)
        except Exception as e:
            print(f"[outlook] IMAP 认证失败: {e}")
            try:
                imap.logout()
            except Exception:
                pass
            return None

        try:
            for mailbox in ("INBOX", "Junk"):
                code = _check_mailbox_for_code(imap, mailbox, since_time, max_check)
                if code:
                    return code
        except Exception as e:
            print(f"[outlook] 检查邮箱异常: {e}")
        finally:
            try:
                imap.logout()
            except Exception:
                pass

        remaining = deadline - time.time()
        if remaining <= 0:
            break
        wait = min(poll_interval, remaining)
        print(f"[outlook] 本轮未找到验证码，{wait} 秒后重试 ...")
        time.sleep(wait)

    print(f"[outlook] 最近 {since_minutes} 分钟内未找到验证码邮件（已轮询 {max_wait_seconds} 秒）")
    return None


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


def _drag_slider(page, sb, distance: float) -> None:
    """执行滑块拖拽操作。

    Args:
        page: Playwright Page 对象（用于鼠标操作）
        target: 操作上下文（主页面或包含滑块的 iframe）
        sb: 滑块的 bounding_box
        distance: 拖拽距离（已加滑块宽度修正）
    """
    if abs(distance) <= 5:
        print("[captcha] 拖拽距离过小，跳过拖拽")
        return

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
    # 最后精确段（保持较快匀速，不再减速）
    while current < adist:
        step = random.uniform(2, 4)
        current = min(current + step, adist)
        page.mouse.move(
            sb["x"] + sb["width"] / 2 + current * step_dir,
            sb["y"] + sb["height"] / 2 + random.randint(-1, 1),
        )
        page.wait_for_timeout(random.uniform(10, 30))
    page.wait_for_timeout(200)
    page.mouse.up()
    print("[captcha] drag performed")
    page.wait_for_timeout(5000)

def calc_slider_distance(page):
    img_slider_el = page.locator('img#aliyunCaptcha-puzzle').first
    img_bg_el = page.locator('img#aliyunCaptcha-img').first
    bg_src = img_bg_el.get_attribute("src")
    slide_src = img_slider_el.get_attribute("src")
    # print(bg_src)
    # print(slide_src)
    if bg_src.startswith('data:image'):
        bg_b64 = bg_src.split(',', 1)[1]
        img_bg = base64.b64decode(bg_b64)
    else:
        img_bg = requests.get(bg_src).content
    if slide_src.startswith('data:image'):
        slide_b64 = slide_src.split(',', 1)[1]
        img_slide = base64.b64decode(slide_b64)
    else:
        img_slide = requests.get(slide_src).content
    bg = cv2.imdecode(np.frombuffer(img_bg, np.uint8), cv2.IMREAD_COLOR)
    slide = cv2.imdecode(np.frombuffer(img_slide, np.uint8), cv2.IMREAD_COLOR)
    print(f"[captcha] bg={bg.shape} slide={slide.shape}")

    # 背景图在页面上的显示位置（用于把原始图坐标映射到页面坐标）
    box = img_bg_el.bounding_box()
    scale_x = box["width"] / bg.shape[1]

    gap_center_orig_x = _find_gap_x(bg)
    print(f"[captcha] gap_x(orig)={gap_center_orig_x} bg_w={bg.shape[1]}")
    gap_center_page_x = box["x"] + gap_center_orig_x * scale_x

    slider = page.locator('.slider-move').first
    sb = slider.bounding_box()
    if sb is None:
        print("[captcha] 无法获取滑块位置")
        return None, None
    slider_center_x = sb["x"] + sb["width"] / 2
    distance = gap_center_page_x - slider_center_x
    # 滑块拖到“缺口中心 - 滑块中心”位置后，滑块还未完全填入缺口，
    # 实际需要再向右平移一个滑块宽度，才能对齐缺口右侧边缘完成验证。
    distance += sb["width"]
    print(f"[captcha] drag_distance(修正后, +滑块宽度)={distance:.1f}")
    return sb, distance

def _fill_reg_info(page, email):
    # 填邮箱
    email_input = page.locator('input[type="email"]').first
    email_input.wait_for(state="visible", timeout=15000)
    email_input.fill("")
    email_input.type(email, delay=20)
    print(f"[captcha] 已填邮箱: {email}")

    # 生成并填姓名、手机号（随机值）
    first = generate_random_name().capitalize()
    last = generate_random_name().capitalize()
    phone = "138" + ''.join(random.choices(string.digits, k=8))
    print(f"[captcha] 姓名: {first} {last}  手机: {phone}")

    # 收集所有可见的文本输入框（排除验证码框），按 DOM 顺序排列
    # 页面的输入框通常没有 name/id/placeholder 属性，故按顺序定位：
    #   第一个未填的 -> First Name，第二个 -> Last Name，第三个 -> Phone Number
    name1_inp = page.locator('label.form-item:nth-child(1) > input:nth-child(2)').first
    name2_inp = page.locator('label.form-item:nth-child(2) > input:nth-child(2)').first
    phone_inp = page.locator('label.form-item:nth-child(3) > input:nth-child(2)').first
    name1_inp.fill("")
    name1_inp.type(first, delay=15)
    print(f"[captcha] 填写名称 {first}")
    name2_inp.fill("")
    name2_inp.type(last, delay=15)
    print(f"[captcha] 填写姓氏 {last}")
    phone_inp.fill("")
    phone_inp.type(phone, delay=15)
    print(f"[captcha] 填写电话 {phone}")

    # 选邮箱验证
    radio = page.locator('input[type="radio"][value="email"]').first
    radio.click(force=True)
    print("[captcha] 已选邮箱验证")

    # 勾选两个复选框（项目兴趣 + 技术资讯订阅）
    cb1 = page.locator('label.privacy-check:nth-child(7) > input:nth-child(1)').first
    cb2 = page.locator('label.privacy-check:nth-child(8) > input:nth-child(1)').first
    if not cb1.is_checked():
        cb1.check(force=True)
    print(f"[captcha] 已勾选复选框 [{cb1}]")
    if not cb2.is_checked():
        cb2.check(force=True)
    print(f"[captcha] 已勾选复选框 [{cb2}]")

def solve_captcha_and_send_code(page) -> bool:
    """填写表单、选邮箱验证、点发送验证码、拖滑块，返回按钮状态判断结果。"""
    '''
    # 等待 SDK 出现（主页面）
    print("[captcha] 等待 initAliyunCaptcha SDK ...")
    sdk_found = False
    for _ in range(40):  # 最多等 20 秒
        if page.evaluate("typeof window.initAliyunCaptcha === 'function'"):
            sdk_found = True
            print("[captcha] 主页面发现 initAliyunCaptcha")
            break
        page.wait_for_timeout(500)

    if not sdk_found:
        print("[captcha] 未发现 initAliyunCaptcha（主页面）")
    '''

    # 等待滑块验证码图片出现（主页面）
    print("[captcha] 等待滑块验证码图片出现 ...")
    captcha_dialog = page.locator('#aliyunCaptcha-window-popup').first
    captcha_dialog.wait_for(state='visible', timeout=1000 * 30)

    for i in range(10):
        print(f'[captcha] 尝试自动滑动验证码 {i+1}/10')
        # page.wait_for_timeout(1000)
        # 计算距离
        sb, distance = calc_slider_distance(page)
        if not sb or not distance:
            print(f'[captcha] 滑块位置获取失败')
            return False
        # 执行滑块拖拽
        _drag_slider(page, sb, distance)

        # 拖拽完成后，判断验证码浮窗是否消失
        # 若消失，说明验证通过，不再重试；之后直接返回按钮是否禁用
        captcha_vanished = False
        for _ in range(10):  # 最多等 5 秒
            captcha_vanished = not captcha_dialog.is_visible()
            print(f'滑动验证码浮窗是否消失：{captcha_vanished}')
            if captcha_vanished: break
            page.wait_for_timeout(500)
        if captcha_vanished: break

    return captcha_vanished

def get_apikey(page) -> str:
    llm_panel = page.locator('section.ma-section:nth-child(2) > div:nth-child(3) > div:nth-child(1)').first
    llm_panel.click()
    view_btn = page.locator('.anticon-eye-invisible').first
    view_btn.click()
    key_text = page.locator('.ant-input-sm').first
    return key_text.input_value()

def reg_amd_retry(acc, retry=5) -> bool:
    for _ in range(retry):
        try:
            succ = reg_amd(acc)
            if succ: return True
        except:
            traceback.print_exc()
    return False

def reg_amd(acc) -> bool:
    """完整注册流程（全部在浏览器中完成，不再使用 CaptchaTicket）。

    流程：
      1. 取 Outlook 账号（作为注册邮箱 + 收信账号）
      2. 浏览器填邮箱/姓名/手机号，选邮箱验证，点发送验证码，做滑块验证
      3. 检查“发送验证码”按钮状态判断发码成功
      4. Outlook IMAP 轮询收邮件，提取 6 位验证码
      5. 在浏览器里填验证码，点“提交注册 Register”
      6. 检查注册结果，写入 amd.txt
    """
    # 1. 取 Outlook 账号（作为注册邮箱 + 收信账号）
    email, client_id, refresh_token = acc

    print(f"邮箱: {email}")

    with _launch_trusted_camoufox() as (camoufox, page):
        page.goto(
            "https://developer.amd.com.cn/register?"
            "returnUrl=https://developer.amd.com.cn/radeon/tokenfactory",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        # 2. 浏览器滑块验证 + 发码（page 保持打开，供后续填验证码和提交注册）
        # 填写基本信息
        _fill_reg_info(page, email)
        # 点发送验证码
        send_btn = page.locator('button.code-btn').first
        txt = send_btn.inner_text().strip()
        print(f"[captcha] 点击按钮: '{txt}'")
        send_btn.click()
        # 解决滑动验证码
        ok = solve_captcha_and_send_code(page)
        if not ok:
            print("滑块验证未成功")
            return False
        # 2.5. 判断邮箱是否已注册（在收验证码之前，避免无意义轮询）
        send_btn = page.locator('button.code-btn').first
        html = page.content()
        if not send_btn.is_disabled() and '已注册' in html:
            print(f'检测到 {email} 已注册')
            return login_amd(page, email, client_id, refresh_token)
    
        # 3. Outlook 收邮件取 6 位验证码（内置轮询，邮件有延迟时会自动重试）
        print("等待验证码邮件送达...")

        # 4. 在浏览器里填验证码并点“提交注册”（验证码若错误则重新获取，最多3次）
        max_vcode_retries = 3
        for vcode_try in range(1, max_vcode_retries + 1):
            vcode = fetch_verification_code(email, client_id, refresh_token)
            if not vcode:
                print("[captcha] 获取验证码失败")
                return False
            print(f"[captcha] 获取到验证码: {vcode}")

            print(f"[captcha] 填入验证码: {vcode}")
            vcode_input = page.locator('.code-wrapper > input:nth-child(1)').first
            vcode_input.fill("")
            vcode_input.type(vcode, delay=15)
            print(f"[captcha] 已填验证码: {vcode}")

            # 点“提交注册 Register”
            reg_btn = page.locator('.submit-btn').first
            reg_btn.click()

            # 等待注册结果（每次30秒，检查更多成功特征）
            registered = False
            errmsg = ''
            deadline = time.time() + 30
            while time.time() < deadline:
                url = page.url
                # 成功特征：页面跳转到 tokenfactory（注册成功后的固定跳转页）
                if 'radeon/tokenfactory' in url.lower():
                    registered = True
                    print(f"[captcha] 页面跳转到 tokenfactory: {url}")
                    break
                msg_toast = page.locator('.van-toast__text').first
                errmsg = (
                    msg_toast.inner_text().strip()
                    if msg_toast.count() else ""
                )
                print(f'[captcha] 注册失败：{errmsg}')
                page.wait_for_timeout(500)


            if registered:
                print(f"注册成功: {email}")
                apikey = get_apikey(page)
                dttmstr = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
                with open('amd.txt', 'a', encoding='utf8') as f:
                    f.write(f'{dttmstr}----{email}----{apikey}\n')
                return True
            
            # 验证码错误，继续下一次重试（重新获取验证码）
            print(f"[captcha] 第 {vcode_try}/{max_vcode_retries} 次注册失败：{errmsg}")

        print("[captcha] 验证码重试次数已用完，注册未成功")
        return False



def login_amd(page, email: str, client_id, refresh_token) -> bool:
    """跳转到登录页，填写邮箱和密码并登录，返回是否跳转到 tokenfactory。

    登录页：https://developer.amd.com.cn/login?returnUrl=...radeon/tokenfactory
    登录成功后页面会跳转回 tokenfactory。
    """
    LOGIN_URL = ("https://developer.amd.com.cn/login?"
                 "returnUrl=https%3A%2F%2Fdeveloper.amd.com.cn%2Fradeon%2Ftokenfactory")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    print(f"[login] 已跳转到登录页: {page.url}")

    # 填邮箱
    email_input = page.locator('input.login-input:nth-child(4)').first
    email_input.fill("")
    email_input.type(email, delay=15)
    print(f"[login] 已填邮箱: {email}")

    # 发送验证码
    send_btn = page.locator('.login-code-btn').first
    txt = send_btn.inner_text().strip()
    print(f"[captcha] 点击按钮: '{txt}'")
    send_btn.click()

    # 解决滑动验证码
    ok = solve_captcha_and_send_code(page)
    if not ok:
        print("滑块验证未成功")
        return False
    # 收验证码
    vcode = fetch_verification_code(email, client_id, refresh_token)
    if not vcode:
        print("[captcha] 获取验证码失败")
        return False
    print(f"[captcha] 获取到验证码: {vcode}")

    print(f"[captcha] 填入验证码: {vcode}")
    vcode_input = page.locator('input.login-input:nth-child(1)').first
    vcode_input.fill("")
    vcode_input.type(vcode, delay=15)
    print(f"[captcha] 已填验证码: {vcode}")
    # 点登录按钮
    login_btn = page.locator('.login-button').first
    login_btn.click()

    # 等待跳转到 tokenfactory
    deadline = time.time() + 30
    login = False
    while time.time() < deadline:
        url = page.url
        # 成功特征：页面跳转到 tokenfactory（注册成功后的固定跳转页）
        if 'radeon/tokenfactory' in url.lower():
            login = True
            print(f"[captcha] 页面跳转到 tokenfactory: {url}")
            break
        msg_toast = page.locator('.van-toast__text').first
        errmsg = (
            msg_toast.inner_text().strip()
            if msg_toast.count() else ""
        )
        print(f'[captcha] 登录失败：{errmsg}')
        page.wait_for_timeout(500)


    if login:
        print(f"登录成功: {email}")
        apikey = get_apikey(page)
        dttmstr = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        with open('amd.txt', 'a', encoding='utf8') as f:
            f.write(f'{dttmstr}----{email}----{apikey}\n')
        return True

    print(f"[login] 登录后未跳转到 tokenfactory，当前 URL: {page.url}")
    return False


def main():
    accounts = _load_outlook_accounts()
    for acc in accounts:
        reg_amd_retry(acc)


if __name__ == '__main__':
    main()
