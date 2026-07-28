from kimi_code_usage.providers.kimi_membership import parse_monthly_usage_snapshot


def test_parse_monthly_usage_snapshot_reads_first_total_card_in_usage_progress():
    snapshot = {
        "tree": [[
            {"role": "heading", "name": "用量进度"},
            {"role": "StaticText", "name": "总使用量"},
            {"role": "StaticText", "name": "62%"},
            {"role": "StaticText", "name": "Kimi Code"},
            {"role": "StaticText", "name": "2026-08-12 后重置"},
            {"role": "heading", "name": "赠送额度"},
            {"role": "StaticText", "name": "总使用量"},
            {"role": "StaticText", "name": "100%"},
        ]]
    }

    row = parse_monthly_usage_snapshot(snapshot, lang_zh=False)

    assert row is not None
    assert row.label == "Monthly Credits"
    assert row.used == 62.0
    assert row.limit == 100.0
    assert row.remaining == 38.0
    assert row.percent == 62.0
    assert row.reset_at == "2026-08-12"
    assert row.unit == "%"


def test_parse_monthly_usage_snapshot_returns_none_without_usage_progress_card():
    snapshot = {"tree": [[{"role": "StaticText", "name": "账户"}]]}

    assert parse_monthly_usage_snapshot(snapshot, lang_zh=True) is None
