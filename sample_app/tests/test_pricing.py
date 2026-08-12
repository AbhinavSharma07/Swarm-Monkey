import pytest

from sample_app.app.pricing import apply_shipping, calculate_discount, calculate_total, quote


class TestCalculateDiscount:
    def test_below_first_tier_is_zero(self):
        assert calculate_discount(5, is_member=False) == 0.0

    def test_ten_is_five_percent(self):
        assert calculate_discount(10, is_member=False) == 0.05

    def test_just_below_ten_is_zero(self):
        assert calculate_discount(9, is_member=False) == 0.0

    def test_fifty_is_fifteen_percent(self):
        assert calculate_discount(50, is_member=False) == 0.15

    def test_hundred_is_twenty_percent(self):
        assert calculate_discount(100, is_member=False) == 0.20

    def test_member_bonus_adds_five_percent(self):
        assert calculate_discount(10, is_member=True) == pytest.approx(0.10)

    def test_discount_is_capped_at_thirty_percent(self):
        assert calculate_discount(100, is_member=True) == pytest.approx(0.25)
        assert calculate_discount(1000, is_member=True) <= 0.30


class TestCalculateTotal:
    def test_no_discount_tier(self):
        assert calculate_total(1, 10.0) == 10.0

    def test_applies_tier_discount(self):
        assert calculate_total(10, 10.0) == 95.0

    def test_rejects_zero_quantity(self):
        with pytest.raises(ValueError):
            calculate_total(0, 10.0)

    def test_rejects_negative_quantity(self):
        with pytest.raises(ValueError):
            calculate_total(-1, 10.0)

    def test_rejects_negative_price(self):
        with pytest.raises(ValueError):
            calculate_total(1, -1.0)


class TestApplyShipping:
    def test_small_order_gets_flat_fee(self):
        assert apply_shipping(50.0, quantity=5) == pytest.approx(55.99)

    def test_free_shipping_above_total_threshold(self):
        assert apply_shipping(100.0, quantity=1) == 100.0

    def test_free_shipping_above_quantity_threshold(self):
        assert apply_shipping(10.0, quantity=20) == 10.0

    def test_just_below_quantity_threshold_still_charged(self):
        assert apply_shipping(10.0, quantity=19) == pytest.approx(15.99)


class TestQuoteEndToEnd:
    def test_small_member_order(self):
        assert quote(5, 10.0, is_member=True) == pytest.approx(53.49)

    def test_large_order_free_shipping(self):
        assert quote(100, 2.0, is_member=False) == 160.0
