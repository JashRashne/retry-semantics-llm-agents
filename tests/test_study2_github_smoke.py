"""Exercise smoke gating/flow only with fake transport; never run live smoke."""

import importlib.util
import json
from pathlib import Path

import pytest

from retry_semantics.study2.github_adapter import GitHubConfig, GitHubEngineeringAdapter, HTTPResponse

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/smoke_study2_github.py'
spec = importlib.util.spec_from_file_location('github_smoke', SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
TOKEN = 'secret-test-token-for-smoke'


@pytest.mark.parametrize('guard', [None, '', '0', 'true'])
def test_guard_refuses_network_even_with_credentials(monkeypatch, capsys, guard):
    for name in smoke.REQUIRED_ENV:
        monkeypatch.setenv(name, TOKEN)
    if guard is None:
        monkeypatch.delenv('STUDY2_GITHUB_LIVE_ENGINEERING', raising=False)
    else:
        monkeypatch.setenv('STUDY2_GITHUB_LIVE_ENGINEERING', guard)
    monkeypatch.setattr(smoke, 'GitHubEngineeringAdapter', lambda *a: pytest.fail('network boundary reached'))
    assert smoke.main() == 2
    assert 'LIVE GITHUB ENGINEERING SMOKE NOT RUN' in capsys.readouterr().out


@pytest.mark.parametrize('missing', smoke.REQUIRED_ENV)
def test_all_runtime_variables_required_before_dispatch(monkeypatch, missing):
    monkeypatch.setenv('STUDY2_GITHUB_LIVE_ENGINEERING', '1')
    for name in smoke.REQUIRED_ENV:
        monkeypatch.setenv(name, TOKEN)
    monkeypatch.delenv(missing)
    monkeypatch.setattr(smoke, 'GitHubEngineeringAdapter', lambda *a: pytest.fail('network boundary reached'))
    assert smoke.main() == 2


@pytest.mark.parametrize('case', ['success', 'transformed', 'two_distinct', 'create_error', 'observe_error'])
def test_smoke_single_mutation_complete_observation_safe_artifact(monkeypatch, tmp_path, case):
    calls = []
    original_content = {}
    def transport(request, token, timeout):
        assert token == TOKEN
        calls.append(request)
        if request.method == 'POST':
            original_content.update(json.loads(request.body))
            value = dict(original_content, number=999, state='open')
            status = 500 if case == 'create_error' else 201
        else:
            assert request.method == 'GET'
            # Deliberately different from create-response number: proves independence.
            value = [dict(original_content, number=1, state='open')]
            if case == 'transformed':
                value[0]['body'] += 'provider transformation'
            if case == 'two_distinct':
                value += [dict(original_content, number=2, state='closed')]
            status = 429 if case == 'observe_error' else 200
        return HTTPResponse(status, (('Content-Type', 'application/json'),
                                     ('X-GitHub-Request-Id', TOKEN), ('Authorization', TOKEN)),
                            json.dumps(value).encode())
    monkeypatch.setattr(smoke, 'GitHubEngineeringAdapter',
                        lambda config: GitHubEngineeringAdapter(config, transport=transport))
    config = GitHubConfig('https://api.example.test', 'owner', 'repo', TOKEN, '2022-11-28')
    monkeypatch.setenv('STUDY2_GITHUB_LIVE_ENGINEERING', '1')
    for name, value in zip(smoke.REQUIRED_ENV, (TOKEN, 'owner', 'repo',
                                              'https://api.example.test', '2022-11-28')):
        monkeypatch.setenv(name, value)
    path, passed = smoke.run_smoke(config, tmp_path)
    encoded = path.read_text()
    artifact = json.loads(encoded)
    assert artifact['classification'] == smoke.BANNER
    assert TOKEN not in encoded and 'Authorization' not in encoded
    assert passed == (case == 'success')
    assert [c.method for c in calls] == (['POST'] if case == 'create_error' else ['POST', 'GET'])
    assert artifact['mutation_trace']['attempt_count'] == 1
    assert bytes.fromhex(artifact['mutation_trace']['attempts'][0]['request']['body_hex']) == calls[0].body
    if case == 'success':
        assert artifact['matching_distinct_identities'] == [[['owner', 'repo'], 1]]
        assert artifact['controlled_content_round_tripped']
        assert artifact['exactly_one_matching_distinct_resource']
    if case == 'two_distinct':
        assert len(artifact['matching_distinct_identities']) == 2
        assert not artifact['exactly_one_matching_distinct_resource']
    if case == 'observe_error':
        assert artifact['observation_trace']['complete'] is False
        assert artifact['provider_warnings_errors'] == ['http_error']


def test_direct_smoke_invocation_cannot_bypass_environment_guard(monkeypatch, tmp_path):
    config = GitHubConfig('https://api.example.test', 'owner', 'repo', TOKEN, '2022-11-28')
    monkeypatch.delenv('STUDY2_GITHUB_LIVE_ENGINEERING', raising=False)
    monkeypatch.setattr(smoke, 'GitHubEngineeringAdapter', lambda *a: pytest.fail('network boundary reached'))
    with pytest.raises(ValueError, match='opt-in'):
        smoke.run_smoke(config, tmp_path)
    assert not list(tmp_path.iterdir())
