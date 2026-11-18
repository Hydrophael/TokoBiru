import secrets

from tokobiru.core.util import utcnow

ORDER_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


ORDER_CODE_LENGTH = 6


ORDER_CODE_ATTEMPTS = 5


def new_order_code():
    suffix = "".join(secrets.choice(ORDER_CODE_ALPHABET) for _ in range(ORDER_CODE_LENGTH))
    return "TB-" + utcnow().strftime("%y%m%d") + "-" + suffix