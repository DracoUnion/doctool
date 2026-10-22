"""Qoder sign-up orchestration.

The HTTP order mirrors ali_vcode.txt.  Fresh ``bx-*`` values, DeviceToken,
and the dynamic slider ``data`` must be supplied by an authorized browser SDK
session; this script does not forge anti-abuse tokens.
"""
from __future__ import annotations

import random
import cv2
import numpy as np
import requests
from imgyaso.adathres import adathres
import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping
from urllib.parse import quote


CAPTCHA_HOST = "https://13lbkb5.captcha-open-southeast.aliyuncs.com/"
UPLOAD_HOST = "https://upload.captcha-open-southeast.aliyuncs.com/"
CAPTCHA_KEY_ID = "111jdk439dJJIjd023823201"
CAPTCHA_KEY_SECRET = "222aiJodos2938JDdosko2djd82sf0"
SCENE_ID = "1r7eif79x"
PREFIX = "13lbkb5"

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

def solve_captcha():
    _, init_r = init_captcha('123123')
    slider_url = 'https://static-captcha-sgp.aliyuncs.com/' + init_r['PuzzleImage']
    bg_url = 'https://static-captcha-sgp.aliyuncs.com/' + init_r['Image']
    slider = cv2.imdecode(
        np.frombuffer(requests.get(slider_url).content, np.uint8),
        cv2.IMREAD_COLOR,
    )
    bg = cv2.imdecode(
        np.frombuffer(requests.get(bg_url).content, np.uint8),
        cv2.IMREAD_COLOR,
    )
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
    # draw_match(bg, slider2v, max_loc)
    track = generate_track(max_loc[0])
    print(f'track: {track}')


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
        response.raise_for_status()
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
        response.raise_for_status()
        return response

    def check_login_type(self, email: str, bx: Mapping[str, str] | None = None) -> dict[str, Any]:
        payload = {"email": email, "oauth_callback": "/zh"}
        payload.update(bx or {})
        return self.post_json("/api/v1/auth/check-login-type", payload).json()

    def send_verification_code(self, email: str, bx: Mapping[str, str]) -> requests.Response:
        payload = {"channel": "email", "scene": "register", "email": email}
        payload.update(bx)
        return self.post_json("/api/v1/verificationCodes", payload)

    def register(self, email: str, password: str, code: str, name: str,
                 bx: Mapping[str, str]) -> dict[str, Any]:
        payload = {
            "type": "email_pwd", "email": email, "password": password,
            "code": code, "name": name, "invitation_code": "",
        }
        payload.update(bx)
        return self.post_json("/api/v1/users", payload).json()


def create_email(worker_domain: str, email_domain: str,
                 admin_password: str) -> tuple[str, str]:
    """Create a mailbox using the authorized API used by agnes_reg.py."""
    import random
    import string
    local = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    response = requests.post(
        f"https://{worker_domain}/admin/new_address",
        json={"enablePrefix": True, "name": local, "domain": email_domain},
        headers={"x-admin-auth": admin_password, "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("jwt") or not data.get("address"):
        raise RuntimeError(f"mailbox API returned no address: {data}")
    return data["jwt"], data["address"]


def poll_email_code(jwt: str, worker_domain: str,
                    timeout: int = 180, interval: int = 5) -> str:
    """Poll the mailbox and return the first six-digit verification code."""
    deadline = time.monotonic() + timeout
    pattern = re.compile(r"(?:verification-code|验证码)[^0-9]{0,80}(\d{6})", re.I)
    while time.monotonic() < deadline:
        response = requests.get(
            f"https://{worker_domain}/api/mails",
            params={"limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {jwt}"}, timeout=30,
        )
        response.raise_for_status()
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
    response.raise_for_status()
    return params, response.json()


def upload_log(log: Mapping[str, Any]) -> dict[str, Any]:
    params = signed_captcha_params(
        "UploadLog", {"log": json.dumps(log, separators=(",", ":"), ensure_ascii=False)},
        CAPTCHA_KEY_ID, CAPTCHA_KEY_SECRET,
    )
    response = requests.post(UPLOAD_HOST, data=params, timeout=30)
    response.raise_for_status()
    return response.json()


def verify_captcha(*, scene_id: str, certify_id: str, device_token: str,
                   dynamic_data: str, access_key_id: str,
                   access_key_secret: str) -> dict[str, Any]:
    """Call VerifyCaptchaV3 with data generated by the official SDK.

    ``dynamic_data`` is intentionally an input: it is generated by the
    loaded captcha JS from real pointer events and is not a plain x coordinate.
    """
    verify_param = json.dumps({
        "sceneId": scene_id, "certifyId": certify_id,
        "deviceToken": device_token, "data": dynamic_data,
    }, separators=(",", ":"), ensure_ascii=False)
    params = signed_captcha_params(
        "VerifyCaptchaV3",
        {"SceneId": scene_id, "CertifyId": certify_id,
         "CaptchaVerifyParam": verify_param},
        access_key_id, access_key_secret, key_name="AccessKeyId",
    )
    response = requests.post(CAPTCHA_HOST, data=params, timeout=30)
    response.raise_for_status()
    result = response.json()
    if not result.get("Success"):
        raise RuntimeError(f"captcha verification failed: {result}")
    return result


def register(*, bx_tokens: Mapping[str, str], device_token: str,
              dynamic_data: str, verify_key_id: str,
              verify_key_secret: str, worker_domain: str,
              email_domain: str, admin_password: str,
              password: str = "Asd123!@#", name: str = "qwe qweqwe") -> dict[str, Any]:
    """Run the documented request sequence using externally supplied SDK data."""
    jwt, email = create_email(worker_domain, email_domain, admin_password)
    qoder = QoderSession()
    qoder.open_signup()
    qoder.check_login_type(email, bx_tokens)

    init_params, init_result = init_captcha(device_token)
    if not init_result.get("Success"):
        raise RuntimeError(f"captcha initialization failed: {init_result}")
    certify_id = init_result["CertifyId"]

    upload_log({
        "sId": SCENE_ID, "pfx": PREFIX, "cId": certify_id,
        "mInit": {"s": True, "msg": "INIT_SUCCESS"},
    })
    verify_captcha(
        scene_id=SCENE_ID, certify_id=certify_id,
        device_token=device_token, dynamic_data=dynamic_data,
        access_key_id=verify_key_id, access_key_secret=verify_key_secret,
    )
    qoder.send_verification_code(email, bx_tokens)
    code = poll_email_code(jwt, worker_domain)
    return qoder.register(email, password, code, name, bx_tokens)




if __name__ == "__main__":
    # Deterministic sample from ali_vcode.txt (no network request is made).
    sample = {
        "AaduaneId": "111jdk439dJJIjd023823201",
        "SignatureMethod": "HMAC-SHA1", "SignatureVersion": "1.0",
        "Format": "JSON", "Timestamp": "2026-10-22T10:13:56Z",
        "Version": "2023-03-05", "Action": "InitCaptchaV3",
        "SceneId": "1r7eif79x", "Language": "zh", "Mode": "embed",
        "DeviceToken": "REPLACE_WITH_BROWSER_DEVICE_TOKEN",
        "SignatureNonce": "56565ddf-774c-493f-a1ed-0e040d439979",
    }
    print(rpc_signature(sample, "222aiJodos2938JDdosko2djd82sf0"))
    solve_captcha()
