import pytest

from tendril.genome import candidates, seed_genome
from tendril.guidance import GuidanceError, require_credentials, select_jev


def test_real_contract_and_cached_replay_without_another_request(tmp_path):
    pool = candidates(seed_genome(), 3, 4)
    calls = []

    def transport(body, timeout):
        calls.append(body)
        criteria = body["questions"]["edit"]["criteria"]
        assert body["questions"]["edit"]["type"] == "choice"
        return {
            "model": "jev-test-resolved",
            "answers": {
                "edit": {
                    "type": "choice",
                    "choice": pool[1]["id"],
                    "confidence": 1,
                    "probabilities": {k: float(k == pool[1]["id"]) for k in criteria},
                }
            },
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }

    selected, audit = select_jev(
        pool, {"genome": seed_genome()}, 10, tmp_path, transport=transport
    )
    replay, repeated = select_jev(
        pool, {"genome": seed_genome()}, 10, tmp_path, transport=transport
    )
    assert selected == replay == pool[1]
    assert len(calls) == 1 and repeated["cache_hit"]
    assert audit["resolved_model"] == "jev-test-resolved" and "fallback" not in audit
    assert audit["usage"]["input_tokens"] == 10
    assert "Authorization" not in next(tmp_path.glob("*.json")).read_text()


def test_out_of_pool_choice_stops_and_failed_attempt_can_be_retried(tmp_path):
    import json

    pool = candidates(seed_genome(), 1, 4)
    bad = lambda body, timeout: {
        "model": "test",
        "answers": {"edit": {"type": "choice", "choice": "invented"}},
    }
    for _ in range(2):
        with pytest.raises(GuidanceError, match="invalid_response"):
            select_jev(pool, {}, 9, tmp_path, transport=bad)
    attempts = list((tmp_path / "attempts").glob("*.json"))
    assert len(attempts) == 2
    assert {json.loads(path.read_text())["attempt"] for path in attempts} == {1, 2}


def test_missing_key_fails_before_request(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        require_credentials()


@pytest.mark.parametrize(
    "response", [[], None, "bad", {"model": "test", "answers": []}]
)
def test_malformed_response_stops_selection(tmp_path, response):
    pool = candidates(seed_genome(), 1, 4)
    with pytest.raises(GuidanceError, match="invalid_response"):
        select_jev(pool, {}, 9, tmp_path, transport=lambda *_: response)


def test_cost_ledger_counts_orphaned_paid_calls_and_not_cached_replays(tmp_path):
    import json

    from tendril.experiments import _guidance_cost

    entry = {
        "request_hash": "abc",
        "response": {
            "model": "test",
            "usage": {"input_tokens": 120, "output_tokens": 30},
        },
        "error": None,
        "elapsed_seconds": 0.5,
    }
    (tmp_path / "abc.json").write_text(json.dumps(entry))
    orphan = _guidance_cost([], None, tmp_path)
    assert orphan["requests"] == orphan["orphaned_requests"] == 1
    assert orphan["known_usage"] == {"input_tokens": 120, "output_tokens": 30}
    assert orphan["estimated_api_cost"] is None
    pricing = {"input_per_million": 2.0, "output_per_million": 4.0, "currency": "USD"}
    audit = {"guidance": {"strategy": "jev", "request_hash": "abc", "cache_hit": True}}
    resumed = _guidance_cost([audit, audit], pricing, tmp_path)
    assert resumed["requests"] == 1 and resumed["cache_hits"] == 2
    assert resumed["orphaned_requests"] == 0
    assert resumed["estimated_api_cost"] == pytest.approx(0.00036)


def test_cost_ledger_keeps_failed_unknown_usage_explicit(tmp_path):
    import json

    from tendril.experiments import _guidance_cost

    (tmp_path / "failed.json").write_text(
        json.dumps(
            {
                "request_hash": "failed",
                "response": None,
                "error": "HTTP 529",
                "elapsed_seconds": 0.2,
            }
        )
    )
    result = _guidance_cost(
        [], {"input_per_million": 2.0, "output_per_million": 4.0}, tmp_path
    )
    assert (
        result["requests_with_transport_errors"]
        == result["requests_with_unknown_usage"]
        == 1
    )
    assert result["estimated_api_cost"] is None


def test_nonfinite_reply_is_audited_and_recoverable(tmp_path):
    import json

    pool = candidates(seed_genome(), 1, 4)
    with pytest.raises(GuidanceError, match="invalid_response"):
        select_jev(
            pool,
            {},
            9,
            tmp_path,
            transport=lambda *_: {
                "model": "test",
                "usage": {"input_tokens": float("nan")},
            },
        )
    attempt = json.loads(next((tmp_path / "attempts").glob("*.json")).read_text())
    assert attempt["error"] == "invalid_response"
    assert attempt["response_not_json"] and attempt["response"] is None

    def valid(body, timeout):
        return {
            "model": "test",
            "answers": {
                "edit": {
                    "type": "choice",
                    "choice": pool[0]["id"],
                    "confidence": 1.0,
                    "probabilities": {c["id"]: float(c == pool[0]) for c in pool},
                }
            },
        }

    selected, audit = select_jev(pool, {}, 9, tmp_path, transport=valid)
    assert selected == pool[0] and audit["attempt"] == 2
    selected, replay = select_jev(
        pool,
        {},
        9,
        tmp_path,
        transport=lambda *_: pytest.fail("valid decision called twice"),
    )
    assert replay["cache_hit"] and replay["attempt"] == 2
    assert len(list((tmp_path / "attempts").glob("*.json"))) == 2


def test_interrupted_transport_leaves_a_pending_attempt_before_dispatch(tmp_path):
    import json

    pool = candidates(seed_genome(), 1, 4)

    def interrupted(*_):
        record = json.loads(next((tmp_path / 'attempts').glob('*.json')).read_text())
        assert record['error'] == 'request_in_progress'
        assert record['response'] is None
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        select_jev(pool, {}, 9, tmp_path, transport=interrupted)
    record = json.loads(next((tmp_path / 'attempts').glob('*.json')).read_text())
    assert record['error'] == 'request_in_progress'


def test_echoed_credential_never_reaches_audit_or_records(tmp_path, monkeypatch):
    secret = 'test-secret-must-not-be-persisted'
    monkeypatch.setenv('TYPESAFE_API_KEY', secret)
    pool = candidates(seed_genome(), 1, 4)

    def echoed(*_):
        return {
            'model': secret,
            'answers': {'edit': {
                'type': 'choice', 'choice': pool[0]['id'], 'confidence': 1,
                'probabilities': {c['id']: float(c == pool[0]) for c in pool},
            }},
            'debug': secret,
        }

    _, audit = select_jev(pool, {}, 9, tmp_path, transport=echoed)
    assert secret not in str(audit)
    assert all(secret not in path.read_text() for path in tmp_path.rglob('*.json'))


def test_transport_sends_key_only_as_header_and_disables_redirects(monkeypatch):
    import io
    from tendril import guidance

    secret = 'test-private-authorization'
    monkeypatch.setenv('TYPESAFE_API_KEY', secret)

    def opener(handler):
        assert handler.redirect_request(None, None, 302, '', {}, 'https://other.invalid') is None

        class Transport:
            def open(self, request, timeout):
                assert request.full_url == guidance.ENDPOINT
                assert request.get_header('Authorization') == f'Bearer {secret}'
                assert secret.encode() not in request.data
                return io.StringIO('{"ok": true}')
        return Transport()

    monkeypatch.setattr(guidance, 'build_opener', opener)
    assert guidance._post({'model': guidance.DEFAULT_MODEL}, 1) == {'ok': True}


@pytest.mark.parametrize('probabilities,accepted', [
    ({'a': .33, 'b': .33, 'c': .33}, True),
    ({'a': .34, 'b': .34, 'c': .33}, True),
    ({'a': .333, 'b': .333, 'c': .333}, False),
    ({'a': .2, 'b': .2, 'c': .2}, False),
    ({'a': 0, 'b': 0, 'c': 0}, False),
    ({'a': .6, 'b': .6, 'c': .6}, False),
])
def test_probability_rounding_must_be_consistent_with_a_unit_total(probabilities, accepted):
    from tendril.guidance import _validate_response

    response = {'model': 'test', 'answers': {'edit': {
        'type': 'choice', 'choice': 'a', 'confidence': .5,
        'probabilities': probabilities,
    }}}
    if accepted:
        assert _validate_response(response, probabilities) == 'a'
    else:
        with pytest.raises(ValueError, match='sum to one'):
            _validate_response(response, probabilities)


def test_rounding_does_not_allow_nonmaximal_or_out_of_pool_choices():
    from tendril.guidance import _validate_response

    answer = {'type': 'choice', 'choice': 'b', 'confidence': .5,
              'probabilities': {'a': .5, 'b': .3, 'c': .19}}
    response = {'model': 'test', 'answers': {'edit': answer}}
    with pytest.raises(ValueError, match='highest-probability'):
        _validate_response(response, answer['probabilities'])
    answer['choice'] = 'invented'
    with pytest.raises(ValueError, match='legal edit'):
        _validate_response(response, answer['probabilities'])
