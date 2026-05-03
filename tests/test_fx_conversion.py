from __future__ import annotations

import pytest

from app.core.enums import Market
from app.core.errors import FailClosedError
from app.portfolio.fx import convert_to_inr


def test_fx_conversion_uses_fresh_usd_inr(fresh_fx) -> None:
    assert convert_to_inr(100, Market.US, fresh_fx) == 8_300


def test_us_trade_conversion_blocks_missing_fx() -> None:
    with pytest.raises(FailClosedError, match="fresh_usd_inr_fx_required"):
        convert_to_inr(100, Market.US, None)
