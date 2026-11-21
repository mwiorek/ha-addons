"""Ed25519 signatures (RFC 8032), pure Python: the add-on checks a map pack's licence with it and needs no crypto
package. The reference algorithm of RFC 8032 section 6, kept as written there; slow (tens of milliseconds a
signature), which is fine for a few licences checked when a pack is installed.

    sign(secret32, message) -> 64-byte signature         (packs.py, on the machine that issues licences)
    verify(public32, message, signature) -> bool         (artmode/packs.py, on Home Assistant)
    public_key(secret32) -> 32-byte public key
"""
import hashlib

p = 2 ** 255 - 19
d = -121665 * pow(121666, p - 2, p) % p
q = 2 ** 252 + 27742317777372353535851937790883648493
_SQRT_M1 = pow(2, (p - 1) // 4, p)


def _sha512(s):
    return hashlib.sha512(s).digest()


def _add(P, Q):
    A, B = (P[1] - P[0]) * (Q[1] - Q[0]) % p, (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C, D = 2 * P[3] * Q[3] * d % p, 2 * P[2] * Q[2] % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F, G * H, F * G, E * H)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _recover_x(y, sign):
    if y >= p:
        return None
    x2 = (y * y - 1) * pow(d * y * y + 1, p - 2, p)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p != 0:
        x = x * _SQRT_M1 % p
    if (x * x - x2) % p != 0:
        return None
    if (x & 1) != sign:
        x = p - x
    return x


_GY = 4 * pow(5, p - 2, p) % p
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % p)


def _compress(P):
    zi = pow(P[2], p - 2, p)
    x, y = P[0] * zi % p, P[1] * zi % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % p)


def _expand(secret):
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _modq(s):
    return int.from_bytes(_sha512(s), "little") % q


def public_key(secret):
    return _compress(_mul(_expand(secret)[0], _G))


def sign(secret, msg):
    a, prefix = _expand(secret)
    A = _compress(_mul(a, _G))
    r = _modq(prefix + msg)
    Rs = _compress(_mul(r, _G))
    s = (r + _modq(Rs + A + msg) * a) % q
    return Rs + int.to_bytes(s, 32, "little")


def verify(public, msg, signature):
    if len(public) != 32 or len(signature) != 64:
        return False
    A, R = _decompress(public), _decompress(signature[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= q:
        return False
    h = _modq(signature[:32] + public + msg)
    return _equal(_mul(s, _G), _add(R, _mul(h, A)))
