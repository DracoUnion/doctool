import imaplib
import time
import requests
import re
from email import message_from_bytes
from datetime import datetime, timedelta, timezone


class OutlookVerificationCodeFetcher:
    """
    通过OAuth2的refresh_token获取access_token，然后使用XOAUTH2协议
    连接Outlook IMAP服务器，轮询收件箱与垃圾箱，提取最新的验证码。
    """

    def __init__(self, email, client_id, refresh_token, tenant="consumers"):
        """
        :param email: Outlook邮箱地址，例如 "user@outlook.com"
        :param client_id: Azure应用的客户端ID
        :param refresh_token: 长期有效的刷新令牌
        :param tenant: 租户类型，个人账户使用 "consumers"
        """
        self.email = email
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.tenant = tenant

    def _get_access_token(self):
        """使用refresh_token换取短期的access_token"""
        url = f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        try:
            res = requests.post(url, data=data, timeout=15)
            if res.status_code != 200:
                print(f"[错误] 换取Access Token失败，状态码: {res.status_code}, 响应: {res.text}")
                return None
            payload = res.json()
            token = payload.get("access_token")
            if not token:
                print(f"[错误] 响应中未包含access_token: {payload}")
                return None
            return token
        except Exception as e:
            print(f"[异常] 换取Access Token时出错: {e}")
            return None

    def _build_auth_string(self, access_token):
        """构造XOAUTH2认证字符串"""
        # 格式: user=<email>\x01auth=Bearer <access_token>\x01\x01
        auth_string = f"user={self.email}\x01auth=Bearer {access_token}\x01\x01"
        return auth_string.encode("utf-8")

    def _parse_email_date(self, date_str):
        """解析邮件中的Date头，转换为datetime对象用于时间过滤"""
        if not date_str:
            return None
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            # 统一为带时区的datetime，方便比较
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    def _extract_code_from_email(self, raw_email_bytes):
        """
        从原始邮件字节中提取验证码。
        常见验证码格式：6位数字（如 123456）、6位大写字母数字混合（如 A1B2C3）。
        这里使用正则 [0-9]{6} 或 [A-Z0-9]{6} 进行匹配，可根据实际邮件内容调整。
        """
        try:
            msg = message_from_bytes(raw_email_bytes)
            # 提取邮件正文
            content = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type in ("text/plain", "text/html"):
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                content += payload.decode("utf-8", errors="ignore")
                        except Exception:
                            continue
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    content = payload.decode("utf-8", errors="ignore")

            # 优先匹配6位纯数字，其次匹配6位大写字母+数字
            match = re.search(r"\b(\d{6})\b", content)
            if match:
                return match.group(1)
            match = re.search(r"\b([A-Z0-9]{6})\b", content)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            print(f"[警告] 解析邮件内容时出错: {e}")
            return None

    def fetch_latest_code(self, since_minutes=5, max_check=10):
        """
        轮询收件箱与垃圾箱，尝试提取最近 since_minutes 分钟内最新邮件中的验证码。

        :param since_minutes: 只检查最近多少分钟内的邮件
        :param max_check: 每个文件夹最多检查最近多少封邮件
        :return: 提取到的验证码字符串，未找到则返回 None
        """
        access_token = self._get_access_token()
        if not access_token:
            print('未获取到 ACCESS_TOKEN')
            return None

        auth_string = self._build_auth_string(access_token)
        imap = imaplib.IMAP4_SSL("outlook.office365.com", 993)

        try:
            # 使用XOAUTH2认证
            imap.authenticate("XOAUTH2", lambda _: auth_string)
        except Exception as e:
            print(f"[错误] IMAP认证失败: {e}")
            try:
                imap.logout()
            except Exception:
                pass
            return None

        # 计算时间阈值（UTC时间）
        since_time = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

        try:
            # 依次检查收件箱和垃圾邮件文件夹
            for mailbox in ("INBOX", "Junk"):
                print(f'检查 {mailbox}')
                try:
                    status, _ = imap.select(mailbox, readonly=True)
                    print(f'{mailbox} 状态：{status}')
                    if status != "OK":
                        continue
                except Exception as ex:
                    print(f'{mailbox} 检查失败：{ex}')
                    continue

                # 搜索所有邮件，然后取最近 max_check 封
                status, data = imap.search(None, "ALL")
                if status != "OK" or not data or not data[0]:
                    print(f'{mailbox} 邮件搜索失败：{status}')
                    continue

                ids = data[0].split()
                if not ids:
                    print(f'{mailbox} 中无任何邮件')
                    continue
                # 取最近的邮件ID（IMAP ID通常递增，后发的ID更大）
                recent_ids = ids[-max_check:] if len(ids) > max_check else ids
                print(f'{mailbox} 中最近的邮件 ID：{recent_ids}')
                # 从新到旧遍历
                for msg_id in reversed(recent_ids):
                    status, msg_data = imap.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not msg_data:
                        print(f'{mailbox} {msg_id} 邮件接收失败：{status}')
                        continue

                    raw_bytes = None
                    for item in msg_data:
                        if isinstance(item, tuple) and len(item) > 1:
                            raw_bytes = item[1]
                            break
                    if not raw_bytes:
                        print(f'{mailbox} {msg_id} 邮件读取失败')
                        continue

                    # 解析邮件头中的Date，进行时间过滤
                    msg_header = message_from_bytes(raw_bytes)
                    msg_date = self._parse_email_date(msg_header.get("Date"))
                    if msg_date and msg_date < since_time:
                        # 邮件太旧，跳过（由于是从新到旧遍历，可以提前结束当前文件夹的检查）
                        # 但为了不错过可能的时间解析异常邮件，这里不直接break，而是continue
                        print(f'{mailbox} {msg_id} 邮件太旧，跳过')
                        continue

                    code = self._extract_code_from_email(raw_bytes)
                    if code:
                        print(f"[成功] 在 {mailbox} 中找到验证码: {code}")
                        return code

            print(f"[提示] 最近 {since_minutes} 分钟内未在 INBOX 和 Junk 中找到验证码邮件。")
            return None

        except Exception as e:
            print(f"[异常] 读取邮件过程中出错: {e}")
            return None
        finally:
            try:
                imap.logout()
            except Exception:
                pass


# ==================== 使用示例 ====================
if __name__ == "__main__":
    # 请替换为你自己的凭证
    # 格式对应: 邮箱----密码(占位)----client_id----refresh_token
    line = open('outlook_emails.txt', encoding='utf8').read().split('\n')[0]
    EMAIL, _, CLIENT_ID, REFRESH_TOKEN, *_ = line.split('----')

    fetcher = OutlookVerificationCodeFetcher(
        email=EMAIL,
        client_id=CLIENT_ID,
        refresh_token=REFRESH_TOKEN,
        tenant="consumers"  # 个人Outlook账户使用 "consumers"
    )

    # 查找最近5分钟内的验证码，每个文件夹最多检查最近10封邮件
    code = fetcher.fetch_latest_code(since_minutes=5, max_check=10)

    if code:
        print(f"\n提取到的验证码: {code}")
    else:
        print("\n未能提取到验证码。请检查：")
        print("1. 凭证是否正确（client_id、refresh_token）")
        print("2. refresh_token是否具有 IMAP.AccessAsUser.All 和 offline_access 权限")
        print("3. 验证码邮件是否在最近5分钟内到达")
        print("4. 验证码格式是否与正则表达式匹配")
