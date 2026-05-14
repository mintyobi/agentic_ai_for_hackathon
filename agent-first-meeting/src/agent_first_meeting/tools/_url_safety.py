"""SSRF ガード: URL の宛先 IP が内部リソースを指していないかを検証する.

Azure Container Apps / VM / App Service 上で稼働させると、内部 IP や
インスタンスメタデータ（169.254.169.254）に到達できてしまうため、
ユーザー入力やエージェント生成の URL はここで弾く必要がある。
"""
import ipaddress
import socket
from urllib.parse import urlparse

# 名前ベースでも弾くホスト（Azure / AWS / GCP のメタデータ）
_BLOCKED_HOSTNAMES = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata",
    "localhost",
    "ip6-localhost",
}


def is_safe_public_url(url: str) -> tuple[bool, str]:
    """URL が安全な公開エンドポイントを指しているか判定する.

    Returns:
        (ok, reason). ok=False のときは reason に弾いた理由が入る。
    """
    if not isinstance(url, str) or not url:
        return False, "empty url"

    try:
        parsed = urlparse(url)
    except ValueError as e:
        return False, f"invalid url: {e}"

    if parsed.scheme not in ("http", "https"):
        return False, f"unsupported scheme: {parsed.scheme!r}"

    hostname = parsed.hostname
    if not hostname:
        return False, "no hostname"

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return False, f"blocked hostname: {hostname}"

    # DNS 解決して、すべての A/AAAA レコードが公開 IP であることを確認
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        return False, f"dns resolution failed: {e}"

    seen_addrs: list[str] = []
    for info in infos:
        addr = info[4][0]
        seen_addrs.append(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False, f"invalid ip from dns: {addr}"
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, f"blocked internal ip {addr} for host {hostname}"

    if not seen_addrs:
        return False, f"no addresses resolved for {hostname}"

    return True, "ok"
