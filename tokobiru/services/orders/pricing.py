from tokobiru.core.config import FREE_SHIPPING_MIN, SHIPPING_FEE


def shipping_fee_for(subtotal, method):
    if method == "pickup" or not SHIPPING_FEE:
        return 0
    if FREE_SHIPPING_MIN and subtotal >= FREE_SHIPPING_MIN:
        return 0
    return SHIPPING_FEE
