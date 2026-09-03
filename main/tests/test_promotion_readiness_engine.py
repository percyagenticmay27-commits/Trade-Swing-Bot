from swing_trade_bot.promotion_readiness_engine import evaluate_promotion_readiness

def good(**overrides):
    data=dict(underlying_symbol='NVDA',leveraged_symbol='NVDX',lifecycle_status='WATCHLIST',source_confluence_score=5,financial_health_score=70,theme_momentum_score=70,opportunity_quality_score=70,thesis_intact=True,entry_score=70)
    data.update(overrides); return evaluate_promotion_readiness(**data)

def test_all_six_pass(): assert good().promotion_ready is True

def test_numeric_boundaries_and_zero():
    for field,gate,threshold in [('source_confluence_score','trusted_sources',5),('financial_health_score','financial_health',70),('theme_momentum_score','theme_strength',70),('opportunity_quality_score','opportunity_quality',70),('entry_score','entry',70)]:
        assert getattr(good(**{field:threshold}),gate).status=='PASS'
        assert getattr(good(**{field:threshold-.01}),gate).status=='FAIL'
        assert getattr(good(**{field:0}),gate).status=='FAIL'

def test_thesis_false_fails(): assert good(thesis_intact=False).thesis_integrity.status=='FAIL'

def test_missing_is_pending():
    for field,gate in [('source_confluence_score','trusted_sources'),('financial_health_score','financial_health'),('theme_momentum_score','theme_strength'),('opportunity_quality_score','opportunity_quality'),('entry_score','entry')]:
        result=good(**{field:None}); assert getattr(result,gate).status=='PENDING'; assert getattr(result,gate).value is None; assert not result.promotion_ready
    assert good(thesis_intact=None).thesis_integrity.status=='PENDING'

def test_stale_is_pending(): assert good(stale={'entry':True}).entry.status=='PENDING'

def test_only_watchlist_can_be_ready():
    assert not good(lifecycle_status='DISCOVERY').promotion_ready
    assert not good(lifecycle_status='MONITOR').promotion_ready

def test_performance_metrics_are_not_inputs():
    assert 'number_of_trades' not in evaluate_promotion_readiness.__annotations__
    assert good().promotion_ready

def test_underlying_identity():
    result=good(underlying_symbol='nvda',leveraged_symbol='nvdx'); assert result.underlying_symbol=='NVDA' and result.leveraged_symbol=='NVDX'
