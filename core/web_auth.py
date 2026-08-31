"""WebUI 密码哈希：Argon2id（OWASP 2024 推荐参数，内存硬化抗 GPU 暴力破解）。

存盘格式：argon2-cffi 默认输出 ``$argon2id$v=19$m=65536,t=3,p=4$<saltB64>$<hashB64>``

明文只存在于：（1）operator 配置明文密码时的临时内存；（2）首次启动生成的临时密码一次性打印到日志。

校验：argon2-cffi 内部使用恒定时间比较。

旧 PBKDF2 哈希（``pbkdf2$...``）不再被识别，触发 main.bootstrap 重新生成临时密码。
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError, VerifyMismatchError

# OWASP Password Storage Cheat Sheet (2024) 推荐：
#   m=19 MiB, t=2, p=1  或  m=12 MiB, t=3, p=1
# 这里偏保守取 m=64MiB, t=3, p=4：登录路径 QPS 极低（< 1），换来的破解成本
# 高出一个数量级。一次哈希约 50–100ms。
_PH = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=4)


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("密码不能为空")
    return _PH.hash(plain)


def is_hashed(value: str) -> bool:
    return isinstance(value, str) and value.startswith("$argon2id$")


def verify_password(plain: str, stored: str) -> bool:
    """校验明文 vs 存盘值。

    仅接受 Argon2id 格式：旧 PBKDF2 哈希视为未设密码，由 bootstrap 重新生成。
    """
    if not stored or not isinstance(stored, str) or not stored.startswith("$argon2id$"):
        return False
    try:
        return _PH.verify(stored, plain)
    except (VerifyMismatchError, InvalidHashError, Argon2Error):
        return False


def random_password(length: int = 18) -> str:
    """生成临时密码：去歧义字符 + 4 组 4-5 位易记组合。

    拼接格式为「aaaa-bbbb-cccc-dddd」（共 19 字符），按 length 截断；
    但绝不能以连字符结尾——截断到连字符位置会留下「17 字母 + -」的难看尾巴。
    """
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    chunk = "-".join(
        "".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)
    )
    if len(chunk) <= length:
        return chunk
    # 截到 length 但若末位是 '-' 就再削一位
    out = chunk[:length]
    return out[:-1] if out.endswith("-") else out


def random_jwt_secret() -> str:
    """JWT HS256 签名密钥：32 字节随机十六进制（256 位熵）。"""
    return secrets.token_hex(32)
