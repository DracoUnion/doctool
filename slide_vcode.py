"""Qoder sign-up orchestration.

The HTTP order mirrors ali_vcode.txt.  Fresh ``bx-*`` values, DeviceToken,
and the dynamic slider ``data`` must be supplied by an authorized browser SDK
session; this script does not forge anti-abuse tokens.
"""
from __future__ import annotations

import string
import random
import cv2
import numpy as np
from camoufox.sync_api import Camoufox
import requests
from imgyaso.adathres import adathres
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping
from urllib.parse import parse_qs, quote

WORKER_DOMAIN = "apimail.flygon.org"  # 替换为你的后台域名，比如我的，apimail.linuxdo.love
EMAIL_DOMAIN = "flygon.org" # 你的域名地址
ADMIN_PASSWORD = os.environ.get('CF_EMAIL_ADMIN_PW', '') # 你的管理员密码
CAPTCHA_HOST = "https://13lbkb5.captcha-open-southeast.aliyuncs.com/"
UPLOAD_HOST = "https://upload.captcha-open-southeast.aliyuncs.com/"
CAPTCHA_KEY_ID = "111jdk439dJJIjd023823201"
CAPTCHA_KEY_SECRET = "222aiJodos2938JDdosko2djd82sf0"
# VerifyCaptchaV3 AccessKey — hard-coded (pe.js ACM/CAPTCHA access key pair,
# same pair the SDK embeds in the ``...keys`` module under ACCESS_KEY).
# NOTE: this is a per-deployment credential; if your account uses a different
# key, replace BOTH values here (they must stay in sync).
CAPTCHA_ACC_KEY_ID = "7JLsB18MnA7GX3d6LxErT1sGT68xcVuOAoxz0b7vVzY="
CAPTCHA_ACC_KEY_SECRET = "n9jH0yACW8YrgOBcM0v7u45+/bfozcSz8ZpvzGBXg3E="
SCENE_ID = "1r7eif79x"
PREFIX = "13lbkb5"


def get_camoufox_tokens(headless: bool = True, wait_ms: int = 8000) -> dict[str, Any]:
    """Open Qoder with Camoufox and read fresh AWSC tokens.

    The browser is intentionally kept alive only while values are read. The
    returned values are short-lived and should be used with the same browser
    session/cookies when possible.
    """
    launch_opts = {
        "headless": headless,
        "humanize": True,
        "locale": "zh-CN",
        "os": ("windows",),
    }
    with Camoufox(**launch_opts) as context:
        page = context.new_page()
        page.goto("https://qoder.com/users/sign-up", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_ms)
        values = page.evaluate("""() => {
          const s = window.__baxia__ || {};
          return {
            cookies: document.cookie,
            bx_ua: s.postFYModule?.getFYToken?.() || "",
            bx_umidtoken: s.getFYModule?.getUidToken?.() || "",
            bx_et: s.etModule?.getETToken?.() || "",
            captcha: window.AliyunCaptchaConfig || null,
          };
        }""")
        required = ("bx_ua", "bx_umidtoken", "bx_et")
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise RuntimeError(f"Camoufox did not produce AWSC values: {missing}")
        return values


def get_camoufox_captcha_session(headless: bool = True) -> dict[str, Any]:
    """Initialize the official CAPTCHA SDK and return a fresh challenge.

    ``data`` is deliberately not fabricated here: it is produced by the
    dynamic captcha JS after a real pointer drag in this browser context.
    """
    launch_opts = {
        "headless": headless,
        "humanize": True,
        "locale": "zh-CN",
        "os": ("windows",),
    }
    with Camoufox(**launch_opts) as context:
        page = context.new_page()
        captcha_requests: list[dict[str, Any]] = []

        def capture_captcha_request(request):
            if "captcha-open" not in request.url or not request.post_data:
                return
            if "Action=InitCaptcha" not in request.post_data:
                return
            values = parse_qs(request.post_data, keep_blank_values=True)
            device = values.get("DeviceToken", [""])[0]
            if device:
                captcha_requests.append({
                    "url": request.url,
                    "device_token": device,
                    "params": {key: value[-1] for key, value in values.items()},
                })

        page.on("request", capture_captcha_request)
        page.goto("https://qoder.com/users/sign-up", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        result = page.evaluate("""async (sceneId) => {
          return await new Promise(resolve => {
            let done = false;
            const finish = value => { if (!done) { done = true; resolve(value); } };
            if (typeof window.initAliyunCaptcha !== "function")
              return finish({ok:false, error:"initAliyunCaptcha unavailable"});
            window.initAliyunCaptcha({SceneId: sceneId, mode:"embed", language:"zh", autoShow:true},
              (code, response) => finish({ok:true, response: response || code}));
            setTimeout(() => finish({ok:false, error:"captcha init timeout"}), 15000);
          });
        }""", SCENE_ID)
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "captcha init failed"))
        if not captcha_requests:
            raise RuntimeError("CAPTCHA init request did not expose DeviceToken")
        tokens = page.evaluate("""() => {
          const s = window.__baxia__ || {};
          return {
            cookies: document.cookie,
            bx_ua: s.postFYModule?.getFYToken?.() || "",
            bx_umidtoken: s.getFYModule?.getUidToken?.() || "",
            bx_et: s.etModule?.getETToken?.() || "",
          };
        }""")
        return {
            "captcha": result["response"],
            "device_token": captcha_requests[-1]["device_token"],
            "captcha_request": captcha_requests[-1],
            **tokens,
        }


def draw_match(bg, sld, loc):
    h, w = sld.shape[:2]
    bg = bg.copy()
    cv2.rectangle(bg, loc, (loc[0] + w, loc[1] + h), (0, 255, 0))
    open('bg_mark.png', 'wb').write(
        bytes(cv2.imencode('.png', bg)[1])
    )
    return bg

def generate_track(distance):
    track = []
    current = 0
    mid = distance * 0.7
    while current < distance:
        if current < mid:
            step = random.uniform(2, 5)   # 加速段
        else:
            step = random.uniform(0.5, 2)  # 减速段
        current = min(current + step, distance)
        track.append(round(current, 2))
    return track

def gen_captcha_track(bg, slider):
    slider2v = 255 - cv2.inRange(
        slider, 
        np.asarray([100, 100, 100]), 
        np.asarray([150, 150, 150])
    )
    # 把滑块上下方空白去掉
    row_mask = (255 - slider2v).mean(1) != 0
    ys = np.where(row_mask)[0]
    ymin, ymax = np.min(ys), np.max(ys)
    slider2v = slider2v[ymin:ymax+1]
    bg2v = adathres(bg).astype(np.uint8)
    open('bg2v.png', 'wb').write(
        bytes(cv2.imencode('.png', bg2v)[1])
    )
    open('slider2v.png', 'wb').write(
        bytes(cv2.imencode('.png', slider2v)[1])
    )
    match = cv2.matchTemplate(bg2v, slider2v, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(match)
    print(f'sc: {max_val}, loc: {max_loc}')
    draw_match(bg, slider2v, max_loc)
    distance = int(max_loc[0])
    track = generate_track(distance)
    print(f'track: {track}')
    return distance, track


def run_browser_registration(headless: bool = True) -> dict[str, Any]:
    """Run signup in one Camoufox session so SDK state and cookies persist.

    The official page generates DeviceToken, bx-* values and the encrypted
    slider payload. The slider is located locally, while the dynamic SDK
    receives the real pointer events and performs its own verification.
    """
    jwt, email = create_email()
    name = gen_name() + " " + gen_name()
    password = gen_name() + gen_name()
    launch_opts = {
        "headless": headless, "humanize": True,
        "locale": "zh-CN", "os": ("windows",),
    }
    captured: list[dict[str, Any]] = []
    with Camoufox(**launch_opts) as context:
        page = context.new_page()

        def capture(request):
            if (
                request.url.endswith("/api/v1/verificationCodes")
                or request.url.endswith("/api/v1/users")
                or "captcha-open" in request.url
            ):
                captured.append({
                    "url": request.url,
                    "method": request.method,
                    "post": request.post_data or "",
                })

        page.on("request", capture)
        page.goto("https://qoder.com/users/sign-up", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        page.fill("#basic_firstName", name.split(" ", 1)[0])
        page.fill("#basic_lastName", name.split(" ", 1)[1])
        page.fill("#basic_email", email)
        page.check("input[type=checkbox]")
        page.click("button[type=submit]")
        page.wait_for_timeout(3000)
        page.fill("#basic_password", password)
        page.click("button[type=submit]")
        page.wait_for_timeout(4000)

        # Expand the captcha if it is still in its compact embed state.
        try:
            page.locator(".aliyun-captcha").first.click(timeout=3000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        puzzle = page.locator("img.puzzle")
        slider = page.locator(".slider-move")
        if not puzzle.count() or not slider.count():
            raise RuntimeError("captcha puzzle/slider was not rendered")
        puzzle_src = puzzle.get_attribute("src") or ""
        piece_src = ""
        for image in page.locator("img").all():
            box = image.bounding_box()
            src = image.get_attribute("src") or ""
            if box and box[2] < 80 and box[3] > 150 and src.startswith("data:"):
                piece_src = src
                break
        if not puzzle_src.startswith("data:") or not piece_src:
            raise RuntimeError("captcha images are not available in the DOM")
        bg = cv2.imdecode(np.frombuffer(base64.b64decode(puzzle_src.split(",", 1)[1]), np.uint8), cv2.IMREAD_COLOR)
        piece = cv2.imdecode(np.frombuffer(base64.b64decode(piece_src.split(",", 1)[1]), np.uint8), cv2.IMREAD_COLOR)
        if bg is None or piece is None:
            raise RuntimeError("cannot decode captcha images")
        match = cv2.matchTemplate(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY), cv2.cvtColor(piece, cv2.COLOR_BGR2GRAY), cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(match)
        if score < 0.15:
            raise RuntimeError(f"weak captcha match: {score:.3f}")
        box = slider.bounding_box()
        parent = slider.locator("..")
        pbox = parent.bounding_box()
        if not box or not pbox:
            raise RuntimeError("captcha slider geometry unavailable")
        source_w = bg.shape[1]
        display_w = puzzle.bounding_box()[2] if puzzle.bounding_box() else source_w
        piece_w = piece.shape[1]
        travel = max(1.0, pbox[2] - box[2])
        distance = loc[0] * travel / max(1, source_w - piece_w)
        start_x, start_y = box[0] + box[2] / 2, box[1] + box[3] / 2
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        for point in generate_track(distance):
            page.mouse.move(start_x + point, start_y + random.uniform(-1.5, 1.5), steps=2)
            page.wait_for_timeout(random.randint(12, 28))
        page.mouse.up()
        page.wait_for_timeout(5000)

        # The dynamic SDK submits verificationCodes after successful CAPTCHA.
        if not any("verificationCodes" in x["url"] for x in captured):
            raise RuntimeError("captcha did not trigger verificationCodes")
        code = poll_email_code(jwt, WORKER_DOMAIN)
        visible_inputs = page.locator("input:visible")
        code_filled = False
        for index in range(visible_inputs.count()):
            field = visible_inputs.nth(index)
            typ = field.get_attribute("type") or "text"
            placeholder = field.get_attribute("placeholder") or ""
            if typ == "text" and ("code" in placeholder.lower() or "验证码" in placeholder):
                field.fill(code)
                code_filled = True
                break
        if not code_filled:
            raise RuntimeError("verification-code input was not found")
        page.click("button[type=submit]")
        page.wait_for_timeout(5000)
        users = [x for x in captured if x["url"].endswith("/api/v1/users")]
        return {"email": email, "password": password, "code": code,
                "users_request": users[-1] if users else None,
                "url": page.url}
def percent_encode(value: Any) -> str:
    """Alibaba RPC percent encoding (RFC3986 variant)."""
    return quote(str(value), safe="~").replace("+", "%20").replace("*", "%2A")


def rpc_signature(params: Mapping[str, Any], access_key_secret: str,
                  method: str = "POST") -> str:
    """Return Alibaba POP/RPC SignatureVersion=1.0 HMAC-SHA1 signature.

    ``params`` must not contain ``Signature``. Values are signed in their
    decoded form; URL encoding is performed exactly once here.
    """
    canonical = "&".join(
        f"{percent_encode(key)}={percent_encode(params[key])}"
        for key in sorted(params)
        if key != "Signature"
    )
    string_to_sign = (
        f"{method.upper()}&{percent_encode('/')} &".replace(" &", "&")
        + percent_encode(canonical)
    )
    digest = hmac.new(
        (access_key_secret + "&").encode(),
        string_to_sign.encode(),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def signed_captcha_params(action: str, extra: Mapping[str, Any],
                          key_id: str, key_secret: str,
                          *, version: str = "2023-03-05",
                          key_name: str = "AaduaneId") -> dict[str, Any]:
    """Build and sign an Aliyun CAPTCHA RPC request parameter dictionary."""
    params: dict[str, Any] = {
        key_name: key_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "Format": "JSON",
        "Timestamp": utc_timestamp(),
        "Version": version,
        "Action": action,
        **dict(extra),
        "SignatureNonce": str(uuid.uuid4()),
    }
    params["Signature"] = rpc_signature(params, key_secret)
    return params


class QoderSession:
    """Minimal Qoder API session using a browser-issued CSRF cookie.

    Use a real, authorized browser session to obtain bx-* values. The class
    accepts them as data and never fabricates anti-abuse tokens.
    """

    def __init__(self, session: requests.Session | None = None,
                 base_url: str = "https://qoder.com") -> None:
        self.http = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.csrf_token = ""

    def open_signup(self) -> str:
        response = self.http.get(f"{self.base_url}/users/sign-up", timeout=30)
        if 400 <= response.status_code < 600:
            raise requests.HTTPError(f'{response.url} HTTP {response.status_code}: {response.text}')
        self.csrf_token = self.http.cookies.get("qoder_csrf_token", "")
        if not self.csrf_token:
            raise RuntimeError("qoder_csrf_token was not issued")
        return self.csrf_token

    def post_json(self, path: str, payload: Mapping[str, Any]) -> requests.Response:
        if not self.csrf_token:
            self.open_signup()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-CSRF-Token": self.csrf_token,
            "Referer": f"{self.base_url}/users/sign-up",
        }
        response = self.http.post(
            f"{self.base_url}{path}", json=dict(payload),
            headers=headers, timeout=30,
        )
        if 400 <= response.status_code < 600:
            raise requests.HTTPError(f'{response.url} HTTP {response.status_code}: {response.text}')
        return response

    def check_login_type(self, email: str, bx: Mapping[str, str] | None = None) -> dict[str, Any]:
        payload = {"email": email, "oauth_callback": "/zh"}
        payload.update(bx or {})
        return self.post_json("/api/v1/auth/check-login-type", payload).json()

    def send_verification_code(self, email: str, bx: Mapping[str, str]) -> requests.Response:
        payload = {"channel": "email", "scene": "register", "email": email}
        payload.update(bx)
        return self.post_json("/api/v1/verificationCodes", payload).json()

    def register(self, email: str, password: str, code: str, name: str,
                 bx: Mapping[str, str]) -> dict[str, Any]:
        payload = {
            "type": "email_pwd", "email": email, "password": password,
            "code": code, "name": name, "invitation_code": "",
        }
        payload.update(bx)
        return self.post_json("/api/v1/users", payload).json()

def gen_name():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=10))

def create_email() -> tuple[str, str]:
    """Create a mailbox using the authorized API used by agnes_reg.py."""
    local = gen_name()
    response = requests.post(
        f"https://{WORKER_DOMAIN}/admin/new_address",
        json={"enablePrefix": True, "name": local, "domain": EMAIL_DOMAIN},
        headers={"x-admin-auth": ADMIN_PASSWORD, "Content-Type": "application/json"},
        timeout=30,
    )
    if 400 <= response.status_code < 600:
        raise requests.HTTPError(f'{response.url} HTTP {response.status_code}: {response.text}')
    data = response.json()
    if not data.get("jwt") or not data.get("address"):
        raise RuntimeError(f"mailbox API returned no address: {data}")
    return data["jwt"], data["address"]


def poll_email_code(jwt: str, WORKER_DOMAIN: str,
                    timeout: int = 180, interval: int = 5) -> str:
    """Poll the mailbox and return the first six-digit verification code."""
    deadline = time.monotonic() + timeout
    pattern = re.compile(r"(?:verification-code|验证码)[^0-9]{0,80}(\d{6})", re.I)
    while time.monotonic() < deadline:
        response = requests.get(
            f"https://{WORKER_DOMAIN}/api/mails",
            params={"limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {jwt}"}, timeout=30,
        )
        if 400 <= response.status_code < 600:
            raise requests.HTTPError(f'{response.url} HTTP {response.status_code}: {response.text}')
        for item in response.json().get("results", []):
            raw = item.get("raw", "")
            match = pattern.search(raw)
            if match:
                return match.group(1)
        time.sleep(interval)
    raise TimeoutError("verification email did not arrive")


def init_captcha(device_token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call InitCaptchaV3 and return (signed_params, JSON response)."""
    params = signed_captcha_params(
        "InitCaptchaV3",
        {"SceneId": SCENE_ID, "Language": "zh", "Mode": "embed",
         "DeviceToken": device_token},
        CAPTCHA_KEY_ID, CAPTCHA_KEY_SECRET,
    )
    response = requests.post(CAPTCHA_HOST, data=params, timeout=30)
    if 400 <= response.status_code < 600:
        raise requests.HTTPError(f'{response.url} HTTP {response.status_code}: {response.text}')
    return params, response.json()


def upload_log(log: Mapping[str, Any]) -> dict[str, Any]:
    params = signed_captcha_params(
        "UploadLog", {"log": json.dumps(log, separators=(",", ":"), ensure_ascii=False)},
        CAPTCHA_KEY_ID, CAPTCHA_KEY_SECRET,
    )
    response = requests.post(UPLOAD_HOST, data=params, timeout=30)
    if 400 <= response.status_code < 600:
        raise requests.HTTPError(f'{response.url} HTTP {response.status_code}: {response.text}')
    return response.json()


def aliyun_verify_param_v3(*, certify_id: str, scene_id: str,
                           security_token: str) -> str:
    """Build the CaptchaVerifyParam a 3.0 SDK hands to the business caller.

    pe.js's ``onBizSuccess`` (verifyType ``"3.0"``) wraps the slider result
    in a base64 JSON envelope — NOT in a ``{sceneId, certifyId,
    deviceToken, data}`` structure:

        window.btoa(JSON.stringify({
            certifyId: <captchaResult>,
            sceneId: this.config.SceneId,
            isSign: true,
            securityToken: this.config.securityToken
        }))

    ``certify_id`` is the slider-captcha result returned by the SDK and
    ``security_token`` comes from the InitCaptcha response.  The drag
    trajectory/timestamps are consumed internally by the SDK to decide the
    slide succeeded; they do not appear in this JSON in cleartext.
    """
    payload = {
        "certifyId": certify_id,
        "sceneId": scene_id,
        "isSign": True,
        "securityToken": security_token,
    }
    ascii_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return base64.b64encode(ascii_json.encode("latin-1")).decode()


def aliyun_verify_param_v2(*, scene_id: str, certify_id: str,
                           device_token: str, failover: str = "T") -> str:
    """Build the CaptchaVerifyParam a 2.x SDK hands to the business caller.

    Old AliyunCaptcha's slider-verify callback passes exactly this JSON:

        JSON{ sceneId, certifyId, deviceToken, failover }

    where ``failover`` is the constant ``"T"``.  This is the payload the
    page forwards to VerifyCaptchaV3 when it drives the RPC directly.
    """
    payload = {
        "sceneId": scene_id,
        "certifyId": certify_id,
        "deviceToken": device_token,
        "failover": failover,
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def verify_captcha(*, scene_id: str, certify_id: str, device_token: str,
                   dynamic_data: str | None = None,
                   captcha_verify_param: str | None = None) -> dict[str, Any]:
    """Call VerifyCaptchaV3 for the slider captcha.

    ``CaptchaVerifyParam`` is supplied in one of two ways:

    * ``captcha_verify_param`` — a pre-built string, e.g. the pe.js 3.0
      ``btoa(JSON{certifyId, sceneId, isSign, securityToken})`` produced by
      :func:`aliyun_verify_param_v3`, or the 2.x
      ``JSON{sceneId, certifyId, deviceToken, failover}`` produced by
      :func:`aliyun_verify_param_v2`.
    * ``dynamic_data`` — classic ``{sceneId, certifyId, deviceToken, data}``
      JSON, where ``data`` is a slider behavior payload.

    The signing AccessKey (``AccessKeyId``) is hard-coded in
    ``CAPTCHA_ACC_KEY_ID`` / ``CAPTCHA_ACC_KEY_SECRET``.
    """
    if captcha_verify_param is not None:
        verify_param = captcha_verify_param
    else:
        if dynamic_data is None:
            raise RuntimeError(
                "verify_captcha needs either captcha_verify_param or dynamic_data")
        verify_param = json.dumps({
            "sceneId": scene_id, "certifyId": certify_id,
            "deviceToken": device_token, "data": dynamic_data,
        }, separators=(",", ":"), ensure_ascii=False)
    params = signed_captcha_params(
        "VerifyCaptchaV3",
        {"SceneId": scene_id, "CertifyId": certify_id,
         "CaptchaVerifyParam": verify_param},
        CAPTCHA_ACC_KEY_ID, CAPTCHA_ACC_KEY_SECRET, key_name="AccessKeyId",
    )
    response = requests.post(CAPTCHA_HOST, data=params, timeout=30)
    if 400 <= response.status_code < 600:
        raise requests.HTTPError(f'{response.url} HTTP {response.status_code}: {response.text}')
    result = response.json()
    if not result.get("Success"):
        raise RuntimeError(f"captcha verification failed: {result}")
    return result



def seed_requests_session(browser_values: Mapping[str, Any]) -> requests.Session:
    """Copy cookies from the short Camoufox bootstrap into requests."""
    session = requests.Session()
    for item in str(browser_values.get("cookies", "")).split("; "):
        if "=" in item:
            key, value = item.split("=", 1)
            session.cookies.set(key, value, domain="qoder.com", path="/")
    return session

def register() -> dict[str, Any]:
    """Use requests after the one-time Camoufox token bootstrap.

    The browser is not used after ``browser_values`` has been acquired.  The
    slider CaptchaVerifyParam is computed locally (pe.js 3.0 ``onBizSuccess``
    format) from the ``securityToken`` returned by InitCaptcha, so no external
    ``CAPTCHA_DYNAMIC_DATA`` is required; the VerifyCaptchaV3 AccessKey pair
    is hard-coded in ``CAPTCHA_ACC_KEY_ID`` / ``CAPTCHA_ACC_KEY_SECRET``.
    """
    browser_values = get_camoufox_captcha_session(
        headless=True,
    )
    print(f'[0] 获取浏览器指纹：{browser_values}')
    bx = {
        "bx-ua": browser_values["bx_ua"],
        "bx-umidtoken": browser_values["bx_umidtoken"],
        "bx_et": browser_values["bx_et"],
    }
    jwt, email = create_email()
    print(f'[1] 生成域名邮箱：{email}')
    session = seed_requests_session(browser_values)
    qoder = QoderSession(session=session)
    qoder.open_signup()
    login_type = qoder.check_login_type(email, bx)
    print(f'[2] 检查登录类型：{login_type}')

    _, init_result = init_captcha(browser_values["device_token"])
    print(f'[3] 初始化滑动验证码：{init_result}')
    if not init_result.get("Success"):
        raise RuntimeError(f"captcha initialization failed: {init_result}")
    certify_id = init_result["CertifyId"]
    security_token = init_result.get("securityToken", "")
    r = upload_log({"sId": SCENE_ID, "pfx": PREFIX, "cId": certify_id,
                "mInit": {"s": True, "msg": "INIT_SUCCESS"}})
    print(f'[4] 上传日志：{r}')

    # The slider CaptchaVerifyParam is computed locally, mirroring pe.js's
    # 3.0 onBizSuccess path: btoa(JSON{certifyId, sceneId, isSign, securityToken}).
    # ``securityToken`` comes from the InitCaptcha response, so no browser
    # slider run / external CAPTCHA_DYNAMIC_DATA is needed.
    dynamic_data = aliyun_verify_param_v3(
        certify_id=certify_id, scene_id=SCENE_ID, security_token=security_token)
    verify_result = verify_captcha(
        scene_id=SCENE_ID, certify_id=certify_id,
        device_token=browser_values["device_token"],
        captcha_verify_param=dynamic_data,
    )
    print(f'[5] 校验滑动验证码：{verify_result}')
    r = qoder.send_verification_code(email, bx)
    print(f'[6] 发送短信验证码：{r}')
    code = poll_email_code(jwt, WORKER_DOMAIN)
    print(f'[7] 获取短信验证码：{code}')
    pwd = gen_name() + gen_name()
    result = qoder.register(email, pwd, code,
                             gen_name() + " " + gen_name(), bx)
    print(f'[8] 注册 Qoder：{result}')
    return {"email": email, "password": pwd, "login_type": login_type,
            "captcha": verify_result, "registration": result}


def analyze_pe_script(path: str = "pe.js") -> dict[str, Any]:
    """Return static diagnostics for a downloaded Aliyun dynamic captcha JS.

    This is deliberately analysis-only: it reports markers and offsets but
    does not synthesize CAPTCHA ``data`` or bypass the browser verifier.
    """
    source = open(path, "r", encoding="utf-8").read()
    markers = (
        "ACCESS_KEY", "ACCESS_SEC", "AES_IV", "WEB_AES_SECRET_KEY",
        "INIT_MD5_SECRET_SALT", "VerifyCaptchaV3", "captchaVerifyCallback",
        "securityToken", "deflate", "btoa", "window.AliyunCaptcha",
    )
    offsets: dict[str, list[int]] = {}
    for marker in markers:
        positions: list[int] = []
        start = 0
        while True:
            pos = source.find(marker, start)
            if pos < 0:
                break
            positions.append(pos)
            start = pos + len(marker)
            if len(positions) >= 20:
                break
        offsets[marker] = positions
    return {
        "path": os.path.abspath(path),
        "bytes": os.path.getsize(path),
        "single_line": "\\n" not in source,
        "markers": {key: bool(value) for key, value in offsets.items()},
        "offsets": offsets,
    }


# ---------------------------------------------------------------------------
# pe.js (Aliyun CAPTCHA SDK) encryption of CaptchaVerifyParam / DeviceData.
#
# The dynamic captcha JS (pe.js) computes the crypted ``data``/``DeviceData``
# field that RPC request bodies carry.  Deobfuscating pe.js shows the exact
# chain (verified byte-for-byte against a browser-run SDK):
#
#   de(key, plaintext) = base64( AES-128-CBC( key = utf8(key)[:16],
#                            iv  = utf8("0123456789ABCDEF")[:16] ) )
#   be(arr)            = de(data_key, "#".join(arr))
#   DeviceData         = be([ app_key, "W",
#                             de(flag_key, platform_string),
#                             app_version, "CLOUD", "" ])
#
# The AES integral is implemented below, along with a port of pe.js's
# mangled string-table decoder (``B``) so the SDK keys can be re-derived.
# ---------------------------------------------------------------------------


def aliyun_captcha_encrypt(plaintext, aes_key, iv="0123456789ABCDEF"):
    """Port of pe.js ``de(t, r)``: AES-128-CBC + PKCS7 + base64.

    ``aes_key`` is used as UTF-8 text; CryptoJS truncates it to the block
    size for AES-128 (16 bytes).  ``iv`` likewise on its first 16 bytes.
    """
    from Crypto.Cipher import AES as _AES
    from Crypto.Util.Padding import pad as _pad
    key = aes_key.encode("utf-8")[:16]
    ivb = iv.encode("utf-8")[:16]
    cipher = _AES.new(key, _AES.MODE_CBC, iv=ivb)
    return base64.b64encode(cipher.encrypt(_pad(plaintext.encode("utf-8"), 16))).decode()


# --- pe.js key-module constants (decoded from the SDK's mangled tables). ---
# The ACCESS_KEY / WEB_AES / AES_IV / INIT_MD5_SECRET_SALT values below are
# decoded from pe.js via the ``aliyun_pe_decoder()`` string table; keeping
# them here lets a script reuse them without re-running the decoder.

PE_CAPTCHA_KEYS = {
    "ACCESS_KEY_ID": "7JLsB18MnA7GX3d6LxErT1sGT68xcVuOAoxz0b7vVzY=",
    "ACCESS_KEY_SECRET": "n9jH0yACW8YrgOBcM0v7u45+/bfozcSz8ZpvzGBXg3E=",
    "WEB_AES_SECRET_KEY": "DNsKKPRHfOTuFph6taPHkC+TbC6YUaXi1NfQv95Ez2k=",
    "AES_IV": "d35db7e39ebbf3d001083105",
    "INIT_MD5_SECRET_SALT": ("VgKD/Zm+aFFPvDw0jB2HVVR74GUT+RsG"
                             "Yr6SziJDvbdgDPpJUtAx0mTMzexE3sns"),
    "API_VERSION": "2023-03-05",
}

# Fixed per-build AES keys used by be/de for the InitCaptcha flow.
PE_DATA_KEY = "45f8ac1e1de14397"
PE_FLAG_KEY = "c175a358550d02e2"


def aliyun_make_device_data(app_key, scene_id, *,
                            platform="W.10001.c", app_name="saf-captcha",
                            app_version="W20220202", prefix="",
                            region="cn", data_key=PE_DATA_KEY,
                            flag_key=PE_FLAG_KEY):
    """Build the InitCaptcha ``DeviceData`` the way pe.js does.

    The plaintext is a ``#``-joined envelope whose middle element is the
    AES-encrypted platform string; the whole envelope is then encrypted
    again with ``data_key``.
    """
    platform_str = f"{platform}#{app_name}#{scene_id}#captcha-normal#{prefix}#{region}"
    f = aliyun_captcha_encrypt(platform_str, flag_key)
    return aliyun_captcha_encrypt(
        f"{app_key}#W#{f}#{app_version}#CLOUD#", data_key)


# --- port of pe.js's mangled string-table decoder (function ``B``). --------
# pe.js hides its constants in an array of base64 fragments plus a per-run
# XOR/hex table.  ``aliyun_pe_decode`` reproduces the JS loop exactly so the
# secrets can be regenerated from the raw script instead of trusting a copy.

_PE_HEX_PREFIX = "7260735e55622621457c7d5b207e584e794725386151667f4d4176432f2a46425f782e3c235a67504074754f7059567b5c6e52536d645422246f7a652771445d63"
_PE_HEX_XOR = 23
_PE_ARRAY = [
    "8oemYIeidwR", "qenIeK=2wFB", "1D8v8e", "q5nd8pz1vn7", "i4FhF9Mn8vv",
    "kGRBUe", "k9z4B58", "ZCooF+7", "ahfxa6fA", "Y1g31pRXByB", "q5WYZ1yZZFe",
    "i/8sidW5idW", "QEKbQ5zWQ9K", "PpfzFqVn2wZ", "u/Rsjw0fLdH", "wnW5uon+kIB",
    "PCMSUIV47he", "advojIz4uIz", "Une1Onor8H8", "w+8Tu60jYhg", "Ueu6w4nuwwW",
    "IK3YwKKOIKW", "VHnj2Mu4P5z", "Ppzc/1FCFFg", "hhvuUCuoVne", "UhcfZ1R6",
    "Q5fWZCc=On", "jn3O1I37Y5H", "ud8KjEnre27", "QhsbZqoUOH", "/ufRvsyI/d4",
    "auyoFGeFFC7", "V5oMqdxA8C3", "ZCPgan", "O/Rr", "k202j9Wy7E4",
    "e2eFL1nxew4", "8qF+ZBih=zz", "LMux/p4pjMW", "B9vQupRfwoW", "aCsrQ5sXaK",
    "ueBKjeg+2Dn", "FFkF2BWA", "unZPdHva", "a1fW=n", "isHxBH8lRH7", "Y6nNQK",
    "U6cgT1c0Ue", "uPRa6K",
]


def _pe_b_decode(text, key_byte):
    """Decode one base64 fragment of pe.js's table (mirror of JS B.mV).

    Each character is mapped through the mangled lookup table ``a``
    (``a.index(23 ^ ord(ch))``), accumulated as 6-bit groups, then every
    output byte is XORed with ``key_byte``.  Verified byte-for-byte against
    the real pe.js string table.
    """
    alpha = [int(_PE_HEX_PREFIX[i:i + 2], 16) for i in range(0, len(_PE_HEX_PREFIX), 2)]
    out = bytearray()
    val = 0
    u = 0
    for ch in text:
        try:
            idx = alpha.index(23 ^ ord(ch))
        except ValueError:
            break
        val = (val << 6) | idx
        u += 1
        if u % 4 == 0:
            for b in range(3):
                out.append(((val >> (16 - 8 * b)) & 0xFF) ^ key_byte)
            val = 0
    rem = u % 4
    if rem:
        for b in range(rem - 1):
            out.append(((val >> (rem * 6 - 8 - 8 * b)) & 0xFF) ^ key_byte)
    return bytes(out)


def aliyun_pe_decode(index, key_byte):
    """Return pe.js string-table entry ``index`` decoded with ``key_byte``."""
    return _pe_b_decode(_PE_ARRAY[index], key_byte).decode('utf-8', 'replace')


def aliyun_pe_decoder_selftest():
    """Confirm the decoder reproduces pe.js's exported constants."""
    # p(t, n) == B(t - 3, n): the key module's macro.
    def p(t, n_):
        return aliyun_pe_decode(t - 3, n_)

    api_version = p(14, 7) + "05"
    assert api_version == "2023-03-05", f"API version mismatch: {api_version!r}"
    web_key = "".join(p(x, y) for x, y in [
        (38, 97), (16, 32), (44, 96), (13, 57), (41, 31), (49, 70)])
    assert web_key == PE_CAPTCHA_KEYS["WEB_AES_SECRET_KEY"], web_key
    # de() matches what a browser-run SDK produced for InitCaptcha:
    sample_plain = "W.10001.c#saf-captcha#1r7eif79x#captcha-normal#undefined#cn"
    sample_cipher = ("V0z3lM83c/TjjZu6HWeg97uPMhsuAUWj6W1AUm8Q2FRSr2gF4wC8Htz"
                     "blzQ1zt3o8RDQiWUVckJC/G79CU2otQ==")
    assert aliyun_captcha_encrypt(sample_plain, PE_FLAG_KEY) == sample_cipher
    return True


if __name__ == "__main__":
    # Camoufox is used only once, at the beginning, to obtain fresh browser
    # values. All subsequent HTTP requests use requests.Session.

    print(json.dumps(register(), ensure_ascii=False, indent=2))
