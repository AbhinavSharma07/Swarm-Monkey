from __future__ import annotations


def calculate_discount(quantity: int, is_member: bool) -> float:
    if quantity >= 100:
        rate = 0.20
    elif quantity >= 50:
        rate = 0.15
    elif quantity >= 10:
        rate = 0.05
    else:
        rate = 0.0

    if is_member:
        rate += 0.05

    return min(rate, 0.30)


def calculate_total(quantity: int, unit_price: float, is_member: bool = False) -> float:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if unit_price < 0:
        raise ValueError("unit_price cannot be negative")

    discount = calculate_discount(quantity, is_member)
    subtotal = quantity * unit_price
    return round(subtotal * (1 - discount), 2)


def apply_shipping(total: float, quantity: int) -> float:
    if total >= 100 or quantity >= 20:
        return total
    return round(total + 5.99, 2)


def quote(quantity: int, unit_price: float, is_member: bool = False) -> float:
    total = calculate_total(quantity, unit_price, is_member)
    return apply_shipping(total, quantity)
