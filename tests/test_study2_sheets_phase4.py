"""Hostile Phase 4 OFFLINE tests. Every credential and provider identity is synthetic."""
from dataclasses import asdict, replace
import http.client
import http.server
import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import ssl
import stat
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.request
import webbrowser
from urllib.parse import urlencode

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex
from retry_semantics.study2 import sheets_live_go_phase1 as p1
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase2_read as read
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase3_operator as inherited
from retry_semantics.study2 import sheets_phase4_control as control
from retry_semantics.study2 import sheets_phase4_setup as setup
from retry_semantics.study2 import sheets_phase4_operator as operator
from test_study2_sheets_phase2 import FakeTLS, Wire, payload
from test_study2_sheets_phase3 import client_file
from test_study2_sheets_http_framing import chunked, parsed

_qualification_spec = importlib.util.spec_from_file_location('sheets_phase4_qualification',
    frozen.ROOT / 'scripts/qualify_sheets_phase4_offline.py')
qualification = importlib.util.module_from_spec(_qualification_spec)
_qualification_spec.loader.exec_module(qualification)

BEARER = 'ya29.synthetic-phase4-bearer'
CLIENT_SECRET = 'synthetic-phase4-client-secret'
HEAD = 'a' * 40
NEXT_HEAD = 'b' * 40


@pytest.fixture(autouse=True)
def forbidden_network_browser(monkeypatch):
    def denied(*a, **kw):
        pytest.fail('Phase 4 provider/network/browser access forbidden')
    for name in ('socket', 'create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'getnameinfo'):
        monkeypatch.setattr(socket, name, denied)
    for cls in (http.client.HTTPConnection, http.client.HTTPSConnection):
        monkeypatch.setattr(cls, 'connect', denied)
    monkeypatch.setattr(ssl.SSLContext, 'wrap_socket', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', denied)
    for name in ('open', 'open_new', 'open_new_tab'):
        monkeypatch.setattr(webbrowser, name, denied)
    monkeypatch.setattr(os, 'environ', {})


@pytest.fixture
def client():
    return credentials.ClientConfig('123-abc.apps.googleusercontent.com', CLIENT_SECRET, 'TEST_ONLY_project')


@pytest.fixture
def reviewed(client):
    return {'schema': 'sheets-phase4-client-review-v1', 'public': client.public_projection(),
            'public_sha256': client.public_hash}


@pytest.fixture
def config(tmp_path):
    value = json.loads((frozen.SHEETS_DOCS / 'SHEETS_PHASE4_OPERATOR_CONFIGURATION_DRAFT.json').read_text())
    root = tmp_path.resolve() / 'operational'
    root.mkdir(mode=0o700)
    (root / 'registry').mkdir(mode=0o700)
    value.update(storage_root=str(root), expected_head=HEAD, account_alias='TEST_ONLY_account',
                 operator_alias='TEST_ONLY_operator', reservation_id='TEST_ONLY_fixture',
                 authorization_id='TEST_ONLY_authorization')
    value['read']['registry_root'] = str(root / 'registry')
    return inherited._typed(value, control.OperatorConfiguration)


@pytest.fixture
def offline(config, reviewed, monkeypatch):
    monkeypatch.setattr(p3, 'repository_check', lambda head: p2.require(head == HEAD))
    p3.write_json(config.path('operator.json'), config.projection())
    p3.write_json(config.path('client-review.json'), reviewed)
    attestation = control.startup(config, reviewed, dict.fromkeys(control.ASSUMPTIONS, True))
    pin = control.runtime_projection(config, reviewed)
    p3.write_json(config.path('startup.json'), attestation)
    p3.write_json(config.path('offline-pin.json'), pin)
    return dict(config=config, review=reviewed, attestation=attestation, pin=pin)


@pytest.fixture
def prepared(client):
    now = time.time()
    body = canonical_json_bytes(dict(access_token=BEARER, expires_in=3600, scope=p1.SCOPE,
                                    token_type='Bearer', refresh_token='synthetic-refresh'))
    return credentials.validate_token_response(body, client, account_alias='TEST_ONLY_account',
        exchange_started_at=now - 2, prepared_at=now - 1, clock_uncertainty_seconds=2)


def mark_synthetic_token_validated(diagnostic):
    diagnostic.callback_count = 'one'
    diagnostic.status_class = '200'
    diagnostic.framing_class = 'content_length'
    diagnostic.encoding_class = 'absent'
    diagnostic.content_type_class = 'json'
    diagnostic.advance('token_semantics_validated')


def persist_acquisition(config, reviewed, prepared):
    p3.write_json(config.path('oauth-intent.json'), setup.oauth_intent(config, reviewed))
    p3.write_json(config.path('acquisition.json'), prepared[1].projection())


def fake_create(monkeypatch, config, fault=None):
    body = canonical_json_bytes({'spreadsheetId': 'A' * 44, **setup.create_request(config)})
    calls = []
    class Response:
        status = {'401': 401, 'redirect': 302, '500': 500}.get(fault, 200)
        chunked = fault == 'chunked'
        def getheaders(self):
            headers = [('Content-Length', str(len(body))), ('Content-Type', 'application/json')]
            if fault == 'oversize': headers[0] = ('Content-Length', '999999')
            if fault == 'duplicate': headers += [('content-length', str(len(body)))]
            if fault == 'encoding': headers += [('Content-Encoding', 'gzip')]
            if fault == 'transfer': headers += [('Transfer-Encoding', 'chunked')]
            if fault == 'type': headers[1] = ('Content-Type', 'text/html')
            if fault == 'no-length': headers.pop(0)
            return headers
        def read(self, size):
            calls.append('body')
            if fault == 'body': raise TimeoutError(BEARER)
            if fault == 'truncated': return body[:-1]
            if fault == 'malformed': return b'x' * len(body)
            return body
        def isclosed(self): return fault != 'not-closed'
    class Connection:
        def __init__(self, host, port, **kwargs):
            calls.append('construct')
            assert host == frozen.HOST and port == 443 and kwargs['timeout'] == config.create_seconds
            p1.validate_context(kwargs['context'])
        def connect(self):
            calls.append('connect')
            assert self.auto_open == self.debuglevel == 0
            if fault == 'connect': raise ConnectionError(BEARER)
        def request(self, method, path, data, headers):
            calls.append('request')
            assert method == 'POST' and path == '/v4/spreadsheets?' + urlencode({'fields': setup.CREATE_FIELDS})
            assert data == canonical_json_bytes(setup.create_request(config))
            assert headers['Authorization'] == 'Bearer ' + BEARER
            if fault == 'send': raise ConnectionResetError(BEARER)
        def getresponse(self):
            calls.append('response')
            if fault == 'response': raise OSError(CLIENT_SECRET)
            return Response()
        def close(self):
            calls.append('close')
            if fault == 'close': raise OSError(BEARER)
    monkeypatch.setattr(setup.http.client, 'HTTPSConnection', Connection)
    return calls


def create(config, reviewed, prepared, **changes):
    return setup.provision(config, reviewed, *prepared, **{**dict(execute_provisioning=True,
        operator_confirmation=setup.CREATE_CONFIRMATION), **changes})


@pytest.mark.parametrize('fault,accepted', [
    ('length', True), ('chunked', True), ('bad-chunk', False), ('conflict', False),
    ('unsupported-transfer', False), ('incomplete', False), ('bad-json', False),
    ('wrong-status', False), ('connect', False), ('post-dispatch-loss', False),
    ('invalid-identity', False), ('duplicate-length', False), ('gzip', False),
    ('wrong-type', False), ('neither', False), ('oversize', False),
])
def test_create_raw_http_framing_and_uncertainty(offline, prepared, monkeypatch, fault, accepted):
    config, review = offline['config'], offline['review']
    persist_acquisition(config, review, prepared)
    body = canonical_json_bytes({'spreadsheetId': 'A' * 44, **setup.create_request(config)})
    if fault == 'bad-json':
        body = b'x' * len(body)
    if fault == 'invalid-identity':
        body = canonical_json_bytes({'spreadsheetId': 'TEST_ONLY_wrong', **setup.create_request(config)})
    headers = [('Content-Length', str(len(body))), ('Content-Type', 'application/json; charset=utf-8')]
    wire_body = body
    if fault in ('chunked', 'bad-chunk', 'conflict'):
        headers = [('Transfer-Encoding', 'chunked'), ('Content-Type', ' Application/JSON ; CHARSET=UTF-8 ')]
        wire_body = chunked(body) if fault != 'bad-chunk' else b'z\r\ninvalid\r\n'
    if fault == 'conflict': headers.append(('Content-Length', str(len(body))))
    if fault == 'unsupported-transfer': headers[0] = ('Transfer-Encoding', 'gzip, chunked')
    if fault == 'incomplete': headers[0] = ('Content-Length', str(len(body) + 1))
    if fault == 'duplicate-length': headers.append(('content-length', str(len(body))))
    if fault == 'gzip': headers.append(('Content-Encoding', 'gzip'))
    if fault == 'wrong-type': headers[1] = ('Content-Type', 'text/plain')
    if fault == 'neither': headers.pop(0)
    if fault == 'oversize': headers[0] = ('Content-Length', '65537')
    calls = []

    class Connection:
        def __init__(self, *args, **kwargs):
            calls.append('construct')
        def connect(self):
            calls.append('connect')
            if fault == 'connect': raise ConnectionError('synthetic')
        def request(self, method, path, data, request_headers):
            assert p3.load_json(config.path('create-intent.json')) == setup.create_intent(config, review)
            assert method == 'POST' and data == canonical_json_bytes(setup.create_request(config))
            assert request_headers['Accept-Encoding'] == 'identity'
            calls.append('request')
        def getresponse(self):
            calls.append('response')
            if fault == 'post-dispatch-loss': raise ConnectionResetError('synthetic')
            return parsed(wire_body, headers, status=500 if fault == 'wrong-status' else 200)
        def close(self): calls.append('close')

    monkeypatch.setattr(setup.http.client, 'HTTPSConnection', Connection)
    result = create(config, review, prepared)
    assert result == p3.load_json(config.path('create-result.json'))
    assert result['outcome'] == ('CREATE_RESPONSE_VALIDATED' if accepted else
                                 'CREATE_UNCERTAIN_RECONCILIATION_REQUIRED')
    assert result['http_status'] == (None if fault in ('connect', 'post-dispatch-loss') else
                                     500 if fault == 'wrong-status' else 200)
    assert result['spreadsheet_id'] == ('A' * 44 if accepted else None)
    assert config.path('create-intent.json').exists()
    assert not config.path('provisioning.json').exists()
    with pytest.raises(credentials.CredentialRefused):
        create(config, review, prepared)
    assert calls.count('request') == (0 if fault == 'connect' else 1)


@pytest.fixture
def positive(offline, prepared, monkeypatch):
    config, review = offline['config'], offline['review']
    persist_acquisition(config, review, prepared)
    fake_create(monkeypatch, config)
    assert create(config, review, prepared)['outcome'] == 'CREATE_RESPONSE_VALIDATED'
    parser = operator.session_parser()
    for line in ('review-provisioning --operator-confirmation ' + p3.PROVISION_CONFIRMATION + ' --isolated --no-writers',
                 'reserve-and-descriptor', 'attest-post-setup --provisioning-reviewed'):
        operator.dispatch(parser.parse_args(line.split()), config, review, *prepared)
    return operator.post_inputs(config, *prepared)


def issue(positive, **changes):
    values = dict(inputs=positive, capability='LIVE_READ_GO', engineering_only=True,
        operator_confirmation=p1.CONFIRMATION, fixture_hash=positive['descriptor'].get('fixture_hash', '0' * 64),
        runtime_hash=control.hash_public(positive['pin']), source_hash=control.hash_public(control.source_projection()),
        startup_hash=control.hash_public(positive['attestation']))
    return operator.issue(**{**values, **changes})


def read_inputs(positive):
    config = positive['config']
    return dict(inputs=positive, execute_live_read=True,
        authorization=p3.parse_authorization(p3.load_json(config.path('authorization.json'))),
        receipt=p3.load_json(config.path('phase3-receipt.json')),
        operational_receipt=p3.load_json(config.path('phase4-receipt.json')))


@pytest.mark.parametrize('fault', [None, 'connect', 'send', 'response', '401', 'redirect', '500', 'chunked',
    'oversize', 'duplicate', 'encoding', 'transfer', 'type', 'no-length', 'body', 'truncated', 'malformed', 'not-closed', 'close'])
def test_create_one_intent_one_attempt_never_repeat(offline, prepared, monkeypatch, fault):
    config, review = offline['config'], offline['review']
    persist_acquisition(config, review, prepared)
    calls = fake_create(monkeypatch, config, fault)
    result = create(config, review, prepared)
    assert result['outcome'] == ('CREATE_RESPONSE_VALIDATED' if fault is None else 'CREATE_UNCERTAIN_RECONCILIATION_REQUIRED')
    assert calls.count('construct') == calls.count('connect') == calls.count('close') == 1
    assert calls.count('request') <= 1
    with pytest.raises(credentials.CredentialRefused): create(config, review, prepared)
    assert calls.count('construct') == 1
    if fault is not None:
        with pytest.raises(credentials.CredentialRefused):
            setup.review_provisioning(config, review, operator_confirmation=p3.PROVISION_CONFIRMATION, isolated=True, no_writers=True)
        assert not config.path('provisioning.json').exists()
    evidence = b''.join(p.read_bytes() for p in Path(config.storage_root).iterdir() if p.is_file())
    for material in (BEARER, CLIENT_SECRET, sha256_hex(BEARER.encode()), sha256_hex(CLIENT_SECRET.encode())):
        assert material.encode() not in evidence


@pytest.mark.parametrize('change', [dict(execute_provisioning=False), dict(operator_confirmation=''),
    dict(operator_confirmation='LIVE_READ_GO')])
def test_create_requires_separate_permission(offline, prepared, change):
    config = offline['config']
    persist_acquisition(config, offline['review'], prepared)
    with pytest.raises(credentials.CredentialRefused): create(config, offline['review'], prepared, **change)
    assert not config.path('create-intent.json').exists()


@pytest.mark.parametrize('body', [b'{}', b'{', b'[]', b'{"spreadsheetId":"bad"}', b'null'])
def test_malformed_create_identity_refused(config, reviewed, body):
    with pytest.raises(credentials.CredentialRefused): setup.validated_identity(body, config, reviewed)


@pytest.mark.parametrize('attack', ['boolean-id', 'boolean-extent', 'wrong-title', 'extra-sheet', 'values', 'wrong-id'])
def test_create_response_exact_structure(config, reviewed, attack):
    value = {'spreadsheetId': 'A' * 44, **setup.create_request(config)}
    properties = value['sheets'][0]['properties']
    if attack == 'boolean-id': properties['sheetId'] = True
    if attack == 'boolean-extent': properties['gridProperties']['columnCount'] = True
    if attack == 'wrong-title': properties['title'] = 'Unrelated'
    if attack == 'extra-sheet': value['sheets'].append(value['sheets'][0])
    if attack == 'values': value['sheets'][0]['data'] = [BEARER]
    if attack == 'wrong-id': value['spreadsheetId'] = 'TEST_ONLY_arbitrary'
    with pytest.raises(credentials.CredentialRefused): setup.validated_identity(canonical_json_bytes(value), config, reviewed)


@pytest.mark.parametrize('attack', ['web', 'service-account', 'adc', 'scope', 'auth', 'token', 'cert',
    'redirect', 'extra', 'duplicate', 'inner-duplicate', 'client-id', 'project-id', 'secret-empty',
    'secret-control', 'mode', 'oversized'])
def test_client_review_rejects_unknown_or_unsafe_inputs(client, tmp_path, attack):
    value = client_file(client)
    if attack == 'web': value = {'web': value['installed']}
    if attack == 'service-account': value = {'type': 'service_account', 'private_key': CLIENT_SECRET}
    if attack == 'adc': value = {'type': 'authorized_user', 'refresh_token': CLIENT_SECRET}
    if attack == 'scope': value['installed']['scope'] = 'drive'
    if attack == 'auth': value['installed']['auth_uri'] = 'https://evil.invalid/' + CLIENT_SECRET
    if attack == 'token': value['installed']['token_uri'] = 'https://evil.invalid/' + CLIENT_SECRET
    if attack == 'cert': value['installed']['auth_provider_x509_cert_url'] = 'https://evil.invalid/' + CLIENT_SECRET
    if attack == 'redirect': value['installed']['redirect_uris'] = ['https://evil.invalid/' + CLIENT_SECRET]
    if attack == 'extra': value['installed']['unknown'] = CLIENT_SECRET
    if attack == 'client-id': value['installed']['client_id'] = 'invalid-client-id'
    if attack == 'project-id': value['installed']['project_id'] = 'unsafe project id'
    if attack == 'secret-empty': value['installed']['client_secret'] = ''
    if attack == 'secret-control': value['installed']['client_secret'] = 'bad\nsecret'
    path = tmp_path / 'client.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    if attack == 'duplicate': path.write_text('{"installed":{},"installed":{}}')
    if attack == 'inner-duplicate': path.write_text(json.dumps(value).replace(
        '"project_id":', '"project_id":"duplicate","project_id":', 1))
    if attack == 'mode': path.chmod(0o644)
    if attack == 'oversized': path.write_bytes(b' ' * 16385)
    with pytest.raises(credentials.CredentialRefused) as error: setup.review_client(path)
    assert error.value.args == () and error.value.__context__ is None and error.value.__cause__ is None
    assert CLIENT_SECRET not in repr(error.value)


def test_review_valid_download_excludes_secret_and_secret_hash(client, tmp_path):
    path = tmp_path / 'client.json'
    path.write_text(json.dumps(client_file(client)))
    path.chmod(0o600)
    first = setup.review_client(path)
    value = client_file(replace(client, client_secret='different-synthetic-secret'))
    path.write_text(json.dumps(value))
    assert setup.review_client(path) == first
    assert CLIENT_SECRET not in json.dumps(first)
    assert sha256_hex(CLIENT_SECRET.encode()) not in json.dumps(first)


def test_legacy_auth_metadata_review_uses_current_runtime_endpoint(client, tmp_path):
    value = client_file(client)
    value['installed']['auth_uri'] = setup.LEGACY_AUTH_METADATA_URI
    path = tmp_path / 'client.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    review = setup.review_client(path)
    loaded = setup.load_client_config(path, reviewed_public_hash=review['public_sha256'])
    assert review['public_sha256'] == client.public_hash
    assert review['public'] == loaded.public_projection()
    assert review['public']['auth_uri'] == credentials.AUTH_URI
    assert credentials.DesktopPreparer(loaded).authorization_url('http://127.0.0.1:12345/').startswith(
        credentials.AUTH_URI + '?')
    assert CLIENT_SECRET not in json.dumps(review)


def test_current_auth_metadata_review_still_accepted(client, tmp_path):
    path = tmp_path / 'client.json'
    path.write_text(json.dumps(client_file(client)))
    path.chmod(0o600)
    assert setup.review_client(path)['public_sha256'] == client.public_hash


@pytest.mark.parametrize('auth_uri', [
    'https://evil.invalid', 'http://accounts.google.com/o/oauth2/auth',
    'https://accounts.google.com/', 'https://accounts.google.com/o/oauth2/auth.evil',
    'https://accounts.google.com/o/oauth2/auth?next=evil',
    'https://accounts.google.com/o/oauth2/v2/auth#fragment',
    'https://accounts.google.com.evil.invalid/o/oauth2/v2/auth',
])
def test_phase4_rejects_other_auth_metadata(client, tmp_path, auth_uri):
    value = client_file(client)
    value['installed']['auth_uri'] = auth_uri
    path = tmp_path / 'client.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    with pytest.raises(credentials.CredentialRefused):
        setup.review_client(path)
    with pytest.raises(credentials.CredentialRefused):
        setup.load_client_config(path, reviewed_public_hash=client.public_hash)


def test_legacy_review_and_acquisition_share_public_hash_binding(offline, client, prepared, tmp_path, monkeypatch):
    value = client_file(client)
    value['installed']['auth_uri'] = setup.LEGACY_AUTH_METADATA_URI
    path = tmp_path / 'client.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    review = setup.review_client(path)
    assert review == offline['review']
    with pytest.raises(credentials.CredentialRefused):
        setup.load_client_config(path, reviewed_public_hash='0' * 64)
    monkeypatch.setattr(credentials, 'load_client_config',
        lambda *a, **kw: pytest.fail('frozen Phase 3 loader called'))
    seen = []
    def fake_acquire(self, **kwargs):
        seen.append(self._config.public_hash)
        assert self._config.public_projection() == review['public']
        assert self._config.client_secret == CLIENT_SECRET
        return prepared
    monkeypatch.setattr(credentials.DesktopPreparer, 'acquire', fake_acquire)
    assert setup.acquire(**offline, client_path=path, execute_oauth=True,
        operator_confirmation=credentials.ACQUISITION_CONFIRMATION,
        present_url=lambda _: pytest.fail('unexpected browser')) == prepared
    assert seen == [review['public_sha256']]
    evidence = b''.join(p.read_bytes() for p in Path(offline['config'].storage_root).iterdir() if p.is_file())
    assert CLIENT_SECRET.encode() not in evidence
    assert sha256_hex(CLIENT_SECRET.encode()).encode() not in evidence


def test_legacy_acquisition_rejects_substituted_public_client(offline, client, tmp_path, monkeypatch):
    value = client_file(replace(client, client_id='999-other.apps.googleusercontent.com'))
    value['installed']['auth_uri'] = setup.LEGACY_AUTH_METADATA_URI
    path = tmp_path / 'client.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    monkeypatch.setattr(credentials.DesktopPreparer, 'acquire',
        lambda *a, **kw: pytest.fail('substituted client reached OAuth'))
    with pytest.raises(credentials.CredentialRefused):
        setup.acquire(**offline, client_path=path, execute_oauth=True,
            operator_confirmation=credentials.ACQUISITION_CONFIRMATION,
            present_url=lambda _: pytest.fail('unexpected browser'))
    assert not offline['config'].path('oauth-intent.json').exists()


@pytest.mark.parametrize('attack', ['symlink', 'hardlink', 'mode', 'oversized'])
def test_compat_acquisition_loader_rejects_unsafe_client_file(client, tmp_path, attack):
    path = tmp_path / 'client.json'
    value = client_file(client)
    value['installed']['auth_uri'] = setup.LEGACY_AUTH_METADATA_URI
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    if attack == 'symlink':
        link = tmp_path / 'link.json'
        link.symlink_to(path)
        path = link
    if attack == 'hardlink': os.link(path, tmp_path / 'other.json')
    if attack == 'mode': path.chmod(0o644)
    if attack == 'oversized': path.write_bytes(b' ' * 16385)
    with pytest.raises(credentials.CredentialRefused):
        setup.load_client_config(path, reviewed_public_hash=client.public_hash)


@pytest.mark.parametrize('n', ['minimum_handoff_seconds', 'authorization_seconds', 'consent_seconds', 'exchange_seconds', 'create_seconds'])
@pytest.mark.parametrize('bad', [0, -1, True, float('inf'), float('nan')])
def test_operator_budgets_positive_finite(config, n, bad):
    with pytest.raises(frozen.QualificationError): replace(config, **{n: bad})


@pytest.mark.parametrize('n', [n for n in p3.RuntimeConfiguration.__dataclass_fields__ if n.endswith('_seconds')])
@pytest.mark.parametrize('bad', [-1, True, float('inf'), float('nan')])
def test_read_budgets_finite(config, n, bad):
    with pytest.raises(frozen.QualificationError): replace(config, read={**config.read, n: bad})


def test_budget_sum_and_strict_coherence_and_hash(offline):
    config = offline['config']
    assert config.runtime().attempt_seconds == 60
    assert config.minimum_handoff_seconds > config.authorization_seconds + 72
    for changed in (dict(minimum_handoff_seconds=192), dict(authorization_seconds=72), dict(authorization_seconds=145)):
        with pytest.raises(frozen.QualificationError): replace(config, **changed)
    changed = replace(config, read={**config.read, 'dns_seconds': 6})
    assert control.hash_public(control.runtime_projection(changed, offline['review'])) != control.hash_public(offline['pin'])
    assert control.offline_preflight(**{**offline, 'config': changed})['status'] == 'BLOCKED'


def test_acquisition_failure_schema_is_runtime_pinned(offline):
    schemas = control.runtime_projection(offline['config'], offline['review'])['schemas']
    assert schemas.count('sheets-phase4-acquisition-failure-v1') == 1


@pytest.mark.parametrize('name', ['_socket', 'fcntl'])
def test_new_native_pin_detects_replaced_file_and_contents(offline, monkeypatch, tmp_path, name):
    before = control.runtime_projection(offline['config'], offline['review'])
    original_import = control.importlib.import_module
    replacement = tmp_path / (name + '.so')
    replacement.write_bytes(b'first synthetic native implementation')
    monkeypatch.setattr(control.importlib, 'import_module', lambda selected:
        SimpleNamespace(__file__=str(replacement)) if selected == name else original_import(selected))
    replaced = control.runtime_projection(offline['config'], offline['review'])
    assert replaced['native_operational_implementations'][name]['resolved_path'] == str(replacement.resolve())
    assert control.hash_public(replaced) != control.hash_public(before)
    replacement.write_bytes(b'second synthetic native implementation')
    changed_contents = control.runtime_projection(offline['config'], offline['review'])
    assert control.hash_public(changed_contents) != control.hash_public(replaced)
    blocked = control.offline_preflight(**offline)
    assert blocked['status'] == 'BLOCKED'
    assert {'runtime_pin', 'startup'} <= set(blocked['reasons'])


@pytest.mark.parametrize('name', ['_socket', 'fcntl'])
def test_new_native_pin_without_stable_file_fails_closed(offline, monkeypatch, name):
    original_import = control.importlib.import_module
    monkeypatch.setattr(control.importlib, 'import_module', lambda selected:
        SimpleNamespace(__file__=None) if selected == name else original_import(selected))
    with pytest.raises(frozen.QualificationError):
        control.runtime_projection(offline['config'], offline['review'])
    assert control.offline_preflight(**offline)['status'] == 'BLOCKED'


@pytest.mark.parametrize('returned', [0, 1, 5])
def test_qualification_runner_records_exact_invocation_and_status(capsys, returned):
    calls = []
    command = ['-q', '-W', 'error', 'tests/test_study2_sheets_phase4.py']
    code = qualification.run_qualification(command, runner=lambda args: calls.append(args) or returned)
    output = capsys.readouterr().out
    assert calls == [command] and code == returned
    assert f'QUALIFICATION_COMMAND: pytest.main({command!r})' in output
    assert f'QUALIFICATION_EXIT_CODE: {returned}' in output


def test_qualification_runner_records_launch_failure(capsys):
    def fail(_):
        raise OSError(BEARER)
    assert qualification.run_qualification(['-q'], runner=fail) == 4
    output = capsys.readouterr().out
    assert 'QUALIFICATION_COMMAND: pytest.main([\'-q\'])' in output
    assert 'QUALIFICATION_LAUNCH_FAILURE: OSError' in output
    assert 'QUALIFICATION_EXIT_CODE: unavailable' in output
    assert BEARER not in output


@pytest.mark.parametrize('name', sorted(p1.ENV_DENY | p3.EXTRA_ENV_DENY))
def test_startup_rejects_prohibited_environment(offline, monkeypatch, name):
    monkeypatch.setenv(name.lower(), BEARER)
    assert 'environment' in control.offline_preflight(**offline)['reasons']


def test_offline_preflight_deterministic_no_writes_or_network(offline, monkeypatch):
    config = offline['config']
    before = sorted((p.name, p.stat().st_mtime_ns) for p in Path(config.storage_root).iterdir())
    monkeypatch.setattr(credentials.DesktopPreparer, 'acquire', lambda *a, **kw: pytest.fail('acquisition from preflight'))
    monkeypatch.setattr(p3, 'write_json', lambda *a, **kw: pytest.fail('preflight writes'))
    first = control.offline_preflight(**offline)
    assert first == control.offline_preflight(**offline)
    assert first['status'] == 'PASS' and first['scope'] == 'before-real-setup'
    assert before == sorted((p.name, p.stat().st_mtime_ns) for p in Path(config.storage_root).iterdir())


def test_dirty_repository_always_blocks():
    with pytest.raises(frozen.QualificationError): p3.repository_check(control.BASE)


@pytest.mark.parametrize('attack', ['trust', 'source', 'pin', 'attestation', 'head', 'storage', 'unknown-file', 'setup-intent'])
def test_offline_drift_and_residue_blocks(offline, monkeypatch, attack):
    values = {**offline}
    config = values['config']
    if attack == 'trust': monkeypatch.setattr(p3, 'trust_inventory', lambda: {'changed': True})
    if attack == 'source': monkeypatch.setattr(control, 'source_projection', lambda: {'changed': 'source'})
    if attack == 'pin': values['pin'] = {}
    if attack == 'attestation': values['attestation'] = {}
    if attack == 'head': values['config'] = replace(config, expected_head='b' * 40)
    if attack == 'storage': Path(config.storage_root).chmod(0o755)
    if attack == 'unknown-file': (Path(config.storage_root) / 'unexpected').touch(mode=0o600)
    if attack == 'setup-intent': p3.write_json(config.path('create-intent.json'), {})
    assert control.offline_preflight(**values)['status'] == 'BLOCKED'


@pytest.mark.parametrize('fault', [None, 'acquisition', 'metadata-persistence'])
def test_oauth_one_acquisition_no_retry_no_read_authorization(offline, client, tmp_path, prepared, monkeypatch, fault):
    config = offline['config']
    path = tmp_path / 'client.json'
    p3.write_json(path, client_file(client))
    calls = []
    def acquire(self, **kwargs):
        calls.append('oauth')
        assert kwargs['operator_confirmation'] == credentials.ACQUISITION_CONFIRMATION
        assert kwargs['consent_seconds'] == 300 and kwargs['exchange_timeout_seconds'] == 30
        if fault == 'acquisition': raise OSError(BEARER)
        mark_synthetic_token_validated(kwargs['diagnostic'])
        return prepared
    monkeypatch.setattr(credentials.DesktopPreparer, 'acquire', acquire)
    write = p3.write_json
    def failing_write(path, value):
        if fault == 'metadata-persistence' and path.name == 'acquisition.json': raise OSError(BEARER)
        return write(path, value)
    monkeypatch.setattr(p3, 'write_json', failing_write)
    args = dict(**offline, client_path=path, execute_oauth=True,
        operator_confirmation=credentials.ACQUISITION_CONFIRMATION, present_url=lambda _: pytest.fail('unexpected browser'))
    if fault is None:
        assert setup.acquire(**args) == prepared
    else:
        with pytest.raises(credentials.CredentialRefused) as error: setup.acquire(**args)
        assert error.value.__context__ is None
    with pytest.raises(credentials.CredentialRefused): setup.acquire(**args)
    assert calls == ['oauth']
    assert not config.path('authorization.json').exists()
    assert not config.path('create-intent.json').exists()
    data = b''.join(p.read_bytes() for p in Path(config.storage_root).iterdir() if p.is_file())
    assert BEARER.encode() not in data and sha256_hex(BEARER.encode()).encode() not in data
    if fault is not None:
        failure = p3.load_json(config.path('acquisition-failure.json'))
        assert control.validate_acquisition_failure(failure) == failure
        assert failure['recovery'] == 'stop-review-no-retry'
        assert failure['reason'] == ('persistence_failure' if fault == 'metadata-persistence' else 'local_failure')
        assert failure['last_stage'] == ('acquisition_persistence_started' if fault == 'metadata-persistence'
                                         else 'oauth_intent_persisted')
        assert config.path('oauth-intent.json').exists() and not config.path('acquisition.json').exists()
    else:
        assert not config.path('acquisition-failure.json').exists()


def test_diagnostic_write_failure_preserves_spent_intent(offline, client, tmp_path, monkeypatch):
    config = offline['config']
    path = tmp_path / 'client.json'
    p3.write_json(path, client_file(client))
    monkeypatch.setattr(credentials.DesktopPreparer, 'acquire',
                        lambda *a, **kw: (_ for _ in ()).throw(OSError(BEARER)))
    write = p3.write_json
    def fault(path, value):
        if path.name == 'acquisition-failure.json':
            raise OSError(BEARER)
        return write(path, value)
    monkeypatch.setattr(p3, 'write_json', fault)
    with pytest.raises(credentials.CredentialRefused):
        setup.acquire(**offline, client_path=path, execute_oauth=True,
            operator_confirmation=credentials.ACQUISITION_CONFIRMATION,
            present_url=lambda _: pytest.fail('browser'))
    assert config.path('oauth-intent.json').exists()
    assert not config.path('acquisition-failure.json').exists()
    assert not config.path('acquisition.json').exists()


def test_handoff_lifetime_failure_is_consistent(offline, client, prepared, tmp_path, monkeypatch):
    config = offline['config']
    path = tmp_path / 'client.json'
    p3.write_json(path, client_file(client))
    def acquire(self, **kwargs):
        mark_synthetic_token_validated(kwargs['diagnostic'])
        return replace(prepared[0], expires_at=time.time() + 100), prepared[1]
    monkeypatch.setattr(credentials.DesktopPreparer, 'acquire', acquire)
    with pytest.raises(credentials.CredentialRefused):
        setup.acquire(**offline, client_path=path, execute_oauth=True,
            operator_confirmation=credentials.ACQUISITION_CONFIRMATION,
            present_url=lambda _: pytest.fail('browser'))
    failure = p3.load_json(config.path('acquisition-failure.json'))
    assert control.validate_acquisition_failure(failure) == failure
    assert failure['reason'] == 'handoff_lifetime_invalid'
    assert failure['last_stage'] == 'token_semantics_validated'
    assert not config.path('acquisition.json').exists()


def test_spent_predecessor_allows_only_valid_failure_diagnostic(spent_oauth, monkeypatch):
    config = spent_oauth['config']
    failure = credentials.AcquisitionDiagnostic().projection()
    p3.write_json(config.path('acquisition-failure.json'), failure)
    monkeypatch.setattr(p3, 'repository_check', lambda head: None)
    result = control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    assert result['live_go'] == 'CLOSED'
    record = p3.load_json(acquisition_attempt_path(config) / 'acquisition-attempt.json')
    assert 'acquisition-failure.json' in record['offline_files_present']
    assert not (acquisition_attempt_path(config) / 'acquisition-failure.json').exists()


def test_malformed_failure_diagnostic_blocks_new_attempt(spent_oauth, monkeypatch):
    config = spent_oauth['config']
    failure = {**credentials.AcquisitionDiagnostic().projection(), 'reason': 'provider-secret'}
    p3.write_json(config.path('acquisition-failure.json'), failure)
    monkeypatch.setattr(p3, 'repository_check', lambda head: None)
    with pytest.raises(Exception):
        control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    assert not acquisition_attempt_path(config).exists()


_HTTP_FAILURE = {'callback_count': 'one', 'http_status_class': '200',
    'framing_class': 'content_length', 'content_encoding_class': 'absent',
    'content_type_class': 'json'}


@pytest.mark.parametrize('changes', [
    {'reason': 'semantic_scope_mismatch', **_HTTP_FAILURE},
    {'last_stage': 'authorization_url_presented', 'reason': 'callback_timeout', 'callback_count': 'one'},
    {'last_stage': 'callback_received', 'reason': 'callback_timeout', 'callback_count': 'one'},
    {'last_stage': 'authorization_url_presented', 'reason': 'callback_timeout',
     'http_status_class': '200'},
    {'last_stage': 'authorization_url_presented', 'reason': 'callback_count_invalid'},
    {'last_stage': 'callback_received', 'reason': 'callback_transport_failure', 'callback_count': 'one'},
    {'last_stage': 'callback_parsed', 'reason': 'state_mismatch'},
    {'last_stage': 'token_response_started', 'reason': 'malformed_query', 'callback_count': 'one'},
    {'http_status_class': '200'},
    {'callback_count': 'one'},
    {'last_stage': 'token_response_started', 'reason': 'non_success_status',
     'callback_count': 'one', 'http_status_class': '200'},
    {'last_stage': 'token_response_started', 'reason': 'non_success_status',
     'callback_count': 'one', 'http_status_class': '2xx'},
    {'last_stage': 'token_response_started', 'reason': 'framing_invalid',
     **{**_HTTP_FAILURE, 'http_status_class': '2xx'}},
    {'last_stage': 'token_response_started', 'reason': 'framing_invalid',
     **{**_HTTP_FAILURE, 'http_status_class': 'other_2xx'}},
    {'last_stage': 'token_response_started', 'reason': 'non_success_status',
     **{**_HTTP_FAILURE, 'http_status_class': 'other_2xx'}},
    {'last_stage': 'token_response_started', 'reason': 'non_success_status',
     **{**_HTTP_FAILURE, 'http_status_class': '4xx'}},
    {'last_stage': 'token_response_started', 'reason': 'framing_invalid',
     **{**_HTTP_FAILURE, 'http_status_class': '4xx'}},
    {'last_stage': 'token_response_started', 'reason': 'content_encoding_invalid',
     **{**_HTTP_FAILURE, 'content_encoding_class': 'identity'}},
    {'last_stage': 'token_response_started', 'reason': 'content_encoding_invalid',
     **{**_HTTP_FAILURE, 'framing_class': 'unsupported_transfer', 'content_encoding_class': 'other'}},
    {'last_stage': 'token_response_started', 'reason': 'content_type_invalid', **_HTTP_FAILURE},
    {'last_stage': 'token_response_started', 'reason': 'body_size_invalid',
     **{**_HTTP_FAILURE, 'framing_class': 'chunked'}},
    {'last_stage': 'token_response_started', 'reason': 'body_incomplete', **_HTTP_FAILURE},
    {'last_stage': 'token_json_parsed', 'reason': 'malformed_json', **_HTTP_FAILURE},
    {'last_stage': 'token_json_parsed', 'reason': 'required_field_missing',
     **{**_HTTP_FAILURE, 'framing_class': 'unsupported_transfer'}},
    {'last_stage': 'token_body_complete', 'reason': 'semantic_scope_mismatch', **_HTTP_FAILURE},
    {'last_stage': 'token_json_parsed', 'reason': 'handoff_lifetime_invalid', **_HTTP_FAILURE},
    {'last_stage': 'token_semantics_validated', 'reason': 'persistence_failure', **_HTTP_FAILURE},
    {'last_stage': 'acquisition_persisted', 'reason': 'local_failure', **_HTTP_FAILURE},
    {'reason': ['provider-secret']},
])
def test_impossible_failure_cross_fields_rejected(changes):
    value = {**credentials.AcquisitionDiagnostic().projection(), **changes}
    assert credentials.acquisition_failure_consistent(value) is False
    with pytest.raises(p2.Refused):
        control.validate_acquisition_failure(value)


def test_producer_rejects_inconsistent_projection():
    diagnostic = credentials.AcquisitionDiagnostic()
    diagnostic.reason = 'semantic_scope_mismatch'
    with pytest.raises(credentials.CredentialRefused):
        diagnostic.projection()


@pytest.mark.parametrize('attack', ['review', 'descriptor', 'record', 'reservation', 'token-life', 'token-type',
    'metadata', 'acquisition', 'create-uncertain', 'intent', 'prior-issue', 'conditions', 'runtime'])
def test_post_setup_blocks_incomplete_real_inputs(positive, monkeypatch, attack):
    inputs = {**positive}
    config = inputs['config']
    if attack == 'review': inputs['review'] = {}
    if attack == 'descriptor': inputs['descriptor'] = {}
    if attack == 'record': config.path('provisioning.json').write_bytes(b'{}\n')
    if attack == 'reservation':
        # Test-only tamper, never an operational recovery action.
        (Path(config.runtime().registry_root) / ('reservation-' + config.reservation_id + '.json')).write_bytes(b'{}\n')
    if attack == 'token-life':
        inputs['token'] = replace(inputs['token'], expires_at=time.time() + 900)
        inputs['metadata'] = replace(inputs['metadata'], expires_at=inputs['token'].expires_at)
    if attack == 'token-type': inputs['token'] = object()
    if attack == 'metadata': inputs['metadata'] = replace(inputs['metadata'], account_alias='other')
    if attack == 'acquisition': config.path('acquisition.json').write_bytes(b'{}\n')
    if attack == 'create-uncertain':
        value = p3.load_json(config.path('create-result.json'))
        value['outcome'] = 'CREATE_UNCERTAIN_RECONCILIATION_REQUIRED'
        config.path('create-result.json').write_bytes(canonical_json_bytes(value) + b'\n')
    if attack == 'intent': config.path('create-intent.json').write_bytes(b'{}\n')
    if attack == 'prior-issue': p3.write_json(config.path('issue-intent.json'), {})
    if attack == 'conditions': inputs['conditions'] = p3.LocalConditions(True, True, True, True, False)
    if attack == 'runtime': monkeypatch.setattr(p3, 'trust_inventory', lambda: {'changed': True})
    assert control.post_setup_preflight(**inputs)['status'] == 'BLOCKED'
    with pytest.raises(credentials.CredentialRefused): issue(inputs)
    assert not config.path('authorization.json').exists()


def test_post_setup_pass_local_read_only_and_offline_no_longer_passes(positive, monkeypatch):
    monkeypatch.setattr(p3, 'write_json', lambda *a, **kw: pytest.fail('post-setup preflight writes'))
    assert control.post_setup_preflight(**positive)['status'] == 'PASS'
    config = positive['config']
    assert control.offline_preflight(config, positive['review'], positive['attestation'], positive['offline_pin'])['status'] == 'BLOCKED'


@pytest.mark.parametrize('change', [dict(capability='CLEAN_MUTATION_GO'), dict(capability=''), dict(engineering_only=False),
    dict(operator_confirmation='yes'), dict(fixture_hash='0'*64), dict(runtime_hash='0'*64),
    dict(source_hash='0'*64), dict(startup_hash='0'*64)])
def test_issue_exact_capability_hashes_and_confirmation(positive, change):
    with pytest.raises(credentials.CredentialRefused): issue(positive, **change)
    assert not positive['config'].path('issue-intent.json').exists()


def test_issue_once_binds_all_receipts(positive):
    result = issue(positive)
    config = positive['config']
    auth = p3.parse_authorization(p3.load_json(config.path('authorization.json')))
    assert auth.authorization_id.startswith('TEST_ONLY_') and auth.capability is p1.Capability.LIVE_READ_GO
    assert auth.expires_at - auth.authorized_at == 120
    assert result['authorization_sha256'] == p2.authorization_hash(auth)
    with pytest.raises(credentials.CredentialRefused): issue(positive)
    assert operator.inspect_artifacts(config, positive['review'])['authorization_sha256'] == result['authorization_sha256']


@pytest.mark.parametrize('fault,expected', [(None, read.Outcome.ZERO), ('connect', read.Outcome.TRANSPORT),
    ('send', read.Outcome.TRANSPORT), ('status', read.Outcome.TRANSPORT), ('body', read.Outcome.TRANSPORT),
    ('truncated', read.Outcome.MALFORMED), ('construct', read.Outcome.CONSTRUCTION)])
def test_first_read_uses_frozen_wrapper_once_no_setup_retry_refresh_fallback(positive, monkeypatch, fault, expected):
    issue(positive)
    config = positive['config']
    fixture = p3.parse_fixture_descriptor(positive['descriptor'])
    wire = Wire(canonical_json_bytes(payload(fixture)), fault=fault)
    monkeypatch.setattr(read.ssl, 'SSLSocket', FakeTLS)
    monkeypatch.setattr(read, '_construct', wire.construct)
    calls = []
    def supervise(fixture, configuration, token, provenance, authorization, root, deadline):
        calls.append('attempt')
        with p2.LocalRegistry(root) as registry:
            return read._read_once(registry, fixture, configuration, token, provenance, authorization, deadline)
    monkeypatch.setattr(read, '_supervise', supervise)
    monkeypatch.setattr(credentials.DesktopPreparer, 'acquire', lambda *a, **kw: pytest.fail('acquisition from read'))
    monkeypatch.setattr(setup, 'provision', lambda *a, **kw: pytest.fail('create from read'))
    result = operator.execute_read(**read_inputs(positive))
    assert result['summary']['outcome'] == expected.value
    assert calls == ['attempt'] and wire.constructs == 1
    assert wire.connects <= 1 and wire.responses <= 1 and len(wire.chunks) <= 1
    if wire.chunks: assert wire.chunks[0].startswith(b'GET ') and b':batchUpdate' not in wire.chunks[0]
    with pytest.raises(credentials.CredentialRefused): operator.execute_read(**read_inputs(positive))
    assert calls == ['attempt']
    inspection = operator.inspect_artifacts(config, positive['review'])
    assert inspection['qualification'] == ('SUCCESS_PENDING_INDEPENDENT_REVIEW_AND_FREEZE' if fault is None else 'UNQUALIFIED_OR_INCOMPLETE_STOP')
    recovery = p3.inspect_recovery(configuration=config.runtime(), descriptor=positive['descriptor'],
                                  authorization=read_inputs(positive)['authorization'])
    assert recovery['authorization_state'] == 'SPENT' and recovery['evidence'] == 'terminal-recorded'
    data = b''.join(p.read_bytes() for p in Path(config.storage_root).rglob('*') if p.is_file())
    for material in (BEARER, CLIENT_SECRET, sha256_hex(BEARER.encode()), sha256_hex(CLIENT_SECRET.encode())):
        assert material.encode() not in data


@pytest.mark.parametrize('attack', ['no-flag', 'wrong-receipt', 'token-object', 'runtime', 'expired-auth', 'wrong-capability', 'unready'])
def test_read_gates_before_adapter(positive, monkeypatch, attack):
    issue(positive)
    values = read_inputs(positive)
    if attack == 'no-flag': values['execute_live_read'] = False
    if attack == 'wrong-receipt': values['operational_receipt'] = {}
    if attack == 'token-object': values['inputs'] = {**positive, 'token': object()}
    if attack == 'runtime': monkeypatch.setattr(p3, 'trust_inventory', lambda: {'changed': True})
    if attack == 'expired-auth': values['authorization'] = replace(values['authorization'], authorized_at=1, expires_at=121)
    if attack == 'wrong-capability': values['authorization'] = replace(values['authorization'], capability=p1.Capability.CLEAN_MUTATION_GO)
    if attack == 'unready': values['inputs'] = {**positive, 'token': replace(positive['token'], expires_at=time.time()+500)}
    monkeypatch.setattr(read.ReadAdapter, 'inspect', lambda *a, **kw: pytest.fail('read before gates'))
    with pytest.raises(credentials.CredentialRefused): operator.execute_read(**values)


@pytest.mark.parametrize('receipt', [None, {}, {'schema': 'sheets-phase4-issuance-receipt-v1'}])
def test_qualified_wrapper_refuses_missing_or_invalid_phase4_receipt_before_lower_api(positive, monkeypatch, receipt):
    issue(positive)
    values = read_inputs(positive)
    values['operational_receipt'] = receipt
    monkeypatch.setattr(inherited, 'execute_read', lambda **kw: pytest.fail('lower API reached without Phase 4 receipt'))
    with pytest.raises(credentials.CredentialRefused): operator.execute_read(**values)
    assert not positive['config'].path('read-intent.json').exists()


def test_phase4_documentation_bounds_receipt_and_bearer_claims():
    doc = (frozen.SHEETS_DOCS / 'GOOGLE_SHEETS_LIVE_GO_PHASE4.md').read_text()
    assert 'anonymous multiprocessing spawn IPC/kernel buffers' in doc
    assert 'Frozen Phase 3 does not interpret the Phase 4 receipt' in doc
    assert 'language/process sandboxing' in doc
    assert 'refresh_token_expires_in' in doc


def test_secret_repr_and_hostile_objects(positive):
    class Hostile:
        def __repr__(self): pytest.fail('repr of credential')
        def __str__(self): pytest.fail('str of credential')
        def refresh(self): pytest.fail('refresh')
    assert BEARER not in repr(positive['token']) and CLIENT_SECRET not in repr(credentials.ClientConfig(
        '123.apps.googleusercontent.com', CLIENT_SECRET, 'TEST_ONLY_project'))
    assert 'credential_readiness' in control.post_setup_preflight(**{**positive, 'token': Hostile()})['reasons']


def test_read_arbitrary_exception_has_no_secret_context(positive, monkeypatch):
    issue(positive)
    def fail(**kw): raise RuntimeError(BEARER)
    monkeypatch.setattr(inherited, 'execute_read', fail)
    with pytest.raises(credentials.CredentialRefused) as error: operator.execute_read(**read_inputs(positive))
    assert error.value.args == () and error.value.__context__ is None
    assert positive['config'].path('read-intent.json').exists()
    assert not positive['config'].path('result.json').exists()


def test_session_command_parser_does_not_echo_secret(capsys):
    with pytest.raises(credentials.CredentialRefused) as error: operator.session_parser().parse_args(['unknown-' + BEARER])
    assert error.value.__context__ is None
    assert capsys.readouterr().err == ''


def test_config_template_is_unusable_until_audited_commit():
    value = json.loads((frozen.SHEETS_DOCS / 'SHEETS_PHASE4_OPERATOR_CONFIGURATION_DRAFT.json').read_text())
    assert value['expected_head'] is None
    with pytest.raises(frozen.QualificationError): inherited._typed(value, control.OperatorConfiguration)


def test_cli_offline_missing_input_blocked_no_network(tmp_path, capsys):
    assert operator.main(['phase4-preflight', '--configuration', str(tmp_path / 'missing')]) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'BLOCKED'


@pytest.mark.parametrize('scope', ['', 'https://www.googleapis.com/auth/drive', p1.SCOPE + ' other', p1.SCOPE + ' ' + p1.SCOPE])
def test_wrong_scope_never_exports_prepared_token(client, scope):
    now = time.time()
    body = canonical_json_bytes(dict(access_token=BEARER, expires_in=3600, scope=scope, token_type='Bearer'))
    with pytest.raises(credentials.CredentialRefused) as error:
        credentials.validate_token_response(body, client, account_alias='TEST_ONLY_account',
            exchange_started_at=now, prepared_at=now, clock_uncertainty_seconds=2)
    assert error.value.__context__ is None


@pytest.mark.parametrize('stage', ['intent-write', 'intent-fsync', 'result-write'])
def test_provision_storage_failure_leaves_spent_intent(offline, prepared, monkeypatch, stage):
    config, review = offline['config'], offline['review']
    persist_acquisition(config, review, prepared)
    calls = fake_create(monkeypatch, config)
    original_write, original_fsync = os.write, os.fsync
    # Portable fd-to-path identification through fstat instead of /dev/fd links.
    def named(fd, name):
        path = config.path(name)
        return path.exists() and os.fstat(fd).st_ino == path.stat().st_ino and os.fstat(fd).st_dev == path.stat().st_dev
    def write(fd, data):
        if (stage == 'intent-write' and named(fd, 'create-intent.json') or
            stage == 'result-write' and named(fd, 'create-result.json')): raise OSError(BEARER)
        return original_write(fd, data)
    def fsync(fd):
        if stage == 'intent-fsync' and named(fd, 'create-intent.json'): raise OSError(BEARER)
        return original_fsync(fd)
    monkeypatch.setattr(os, 'write', write)
    monkeypatch.setattr(os, 'fsync', fsync)
    with pytest.raises(credentials.CredentialRefused): create(config, review, prepared)
    assert config.path('create-intent.json').exists()
    assert calls.count('request') == (1 if stage == 'result-write' else 0)
    with pytest.raises(credentials.CredentialRefused): create(config, review, prepared)
    assert calls.count('request') <= 1


def test_create_intent_parent_directory_fsync_failure_never_reaches_provider(offline, prepared, monkeypatch):
    config, review = offline['config'], offline['review']
    persist_acquisition(config, review, prepared)
    calls = fake_create(monkeypatch, config)
    real_fsync = os.fsync
    observed = []
    def fail_parent_directory(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode) and info.st_ino == Path(config.storage_root).stat().st_ino:
            observed.append('parent-directory-fsync')
            assert config.path('create-intent.json').exists()
            assert config.path('create-intent.json').stat().st_size > 0
            raise OSError(BEARER)
        if config.path('create-intent.json').exists() and info.st_ino == config.path('create-intent.json').stat().st_ino:
            observed.append('intent-file-fsync')
        return real_fsync(fd)
    monkeypatch.setattr(os, 'fsync', fail_parent_directory)
    monkeypatch.setattr(os, 'unlink', lambda *a, **kw: pytest.fail('automatic cleanup after fsync failure'))
    with pytest.raises(credentials.CredentialRefused): create(config, review, prepared)
    assert observed == ['intent-file-fsync', 'parent-directory-fsync']
    assert not any(name in calls for name in ('construct', 'connect', 'request'))
    # The present POSIX pathname is poisoned, not refunded or automatically retried.
    assert config.path('create-intent.json').exists()
    with pytest.raises(credentials.CredentialRefused): create(config, review, prepared)
    assert not calls


def test_duplicate_create_callers_only_one_wins(offline, prepared, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    config, review = offline['config'], offline['review']
    persist_acquisition(config, review, prepared)
    calls = fake_create(monkeypatch, config, 'response')
    def attempt():
        try:
            return create(config, review, prepared)['outcome']
        except credentials.CredentialRefused:
            return 'REFUSED'
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ['CREATE_UNCERTAIN_RECONCILIATION_REQUIRED', 'REFUSED']
    assert calls.count('request') == 1


def test_two_processes_one_permanent_create_intent_no_second_provider_path(offline, prepared):
    config, review = offline['config'], offline['review']
    persist_acquisition(config, review, prepared)
    # Both independent interpreters wait immediately before the inherited O_EXCL
    # write. Their provider boundary is a fail-closed fake; socket is also trapped.
    child = '''
import http.client, os, socket, sys
from pathlib import Path
from retry_semantics.study2 import sheets_live_preparation as frozen
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_credentials as credentials
from retry_semantics.study2 import sheets_phase3_operator as inherited
from retry_semantics.study2 import sheets_phase4_control as control
from retry_semantics.study2 import sheets_phase4_setup as setup
root = Path(sys.argv[1])
config = inherited._typed(p3.load_json(root / "operator.json"), control.OperatorConfiguration)
review = p3.load_json(root / "client-review.json")
metadata = inherited._metadata(p3.load_json(root / "acquisition.json"))
token = frozen.prepare_token("ya29.synthetic-phase4-bearer", expires_at=metadata.expires_at,
    clock_uncertainty_seconds=metadata.clock_uncertainty_seconds)
p3.repository_check = lambda head: None
p3.environment_gate = lambda: None
def denied(*args, **kwargs):
    raise AssertionError("provider networking forbidden in process-race test")
socket.socket = socket.create_connection = socket.getaddrinfo = denied
http.client.HTTPSConnection = denied
def provider_boundary(*args, **kwargs):
    print("PROVIDER_BOUND", flush=True)
    raise RuntimeError("deliberate offline stop")
setup.ssl.create_default_context = provider_boundary
real_write = p3.write_json
def synchronized_write(path, value):
    if path.name == "create-intent.json":
        print("READY", flush=True)
        if sys.stdin.readline() != "GO\\n":
            raise RuntimeError("barrier closed")
    return real_write(path, value)
p3.write_json = synchronized_write
try:
    result = setup.provision(config, review, token, metadata, execute_provisioning=True,
        operator_confirmation=setup.CREATE_CONFIRMATION)
except credentials.CredentialRefused:
    print("REFUSED", flush=True)
else:
    print(result["outcome"], flush=True)
'''
    processes = [subprocess.Popen([sys.executable, '-u', '-c', child, config.storage_root],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=frozen.ROOT) for _ in range(2)]
    try:
        for process in processes:
            readable, _, _ = select.select([process.stdout], [], [], 20)
            assert readable, 'child did not reach create-intent barrier'
            assert process.stdout.readline().strip() == 'READY'
        for process in processes:
            process.stdin.write('GO\n')
            process.stdin.flush()
        outputs = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 0, stderr
            outputs.append(stdout.splitlines())
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()
    flattened = [line for output in outputs for line in output]
    assert flattened.count('PROVIDER_BOUND') == 1
    assert flattened.count('CREATE_UNCERTAIN_RECONCILIATION_REQUIRED') == 1
    assert flattened.count('REFUSED') == 1
    assert config.path('create-intent.json').exists()
    assert p3.load_json(config.path('create-intent.json')) == setup.create_intent(config, review)
    assert not config.path('provisioning.json').exists()


@pytest.mark.parametrize('artifact', ['create-intent.json', 'create-result.json', 'provisioning.json', 'oauth-intent.json', 'acquisition.json'])
def test_setup_record_drift_after_issuance_blocks_read(positive, monkeypatch, artifact):
    issue(positive)
    positive['config'].path(artifact).write_bytes(b'{}\n')
    monkeypatch.setattr(read.ReadAdapter, 'inspect', lambda *a, **kw: pytest.fail('read despite setup drift'))
    with pytest.raises(credentials.CredentialRefused): operator.execute_read(**read_inputs(positive))
    assert not positive['config'].path('read-intent.json').exists()


@pytest.mark.parametrize('path_attack', ['root-link', 'client-link', 'hardlink', 'bad-file-mode', 'bad-registry-mode'])
def test_storage_links_modes_rejected(offline, client, tmp_path, path_attack):
    config = offline['config']
    if path_attack == 'root-link':
        link = tmp_path / 'linked'
        link.symlink_to(config.storage_root)
        altered = replace(config, storage_root=str(link), read={**config.read, 'registry_root': str(link/'registry')})
        with pytest.raises(frozen.QualificationError): control.storage_check(altered)
    elif path_attack == 'client-link':
        real = tmp_path / 'client.json'
        p3.write_json(real, client_file(client))
        link = tmp_path / 'client-link.json'
        link.symlink_to(real)
        with pytest.raises(credentials.CredentialRefused): setup.review_client(link)
    else:
        if path_attack == 'hardlink': os.link(config.path('operator.json'), config.path('result.json'))
        if path_attack == 'bad-file-mode': config.path('operator.json').chmod(0o644)
        if path_attack == 'bad-registry-mode': Path(config.runtime().registry_root).chmod(0o755)
        with pytest.raises(frozen.QualificationError): control.storage_check(config)


@pytest.mark.parametrize('argument,name', [('fixture','fixture.json'), ('metadata','acquisition.json'),
    ('authorization','authorization.json'), ('receipt','phase3-receipt.json'), ('operational-receipt','phase4-receipt.json'),
    ('pin','read-pin.json'), ('configuration','operator.json')])
def test_exact_read_command_rejects_any_path_substitution(positive, monkeypatch, argument, name):
    config = positive['config']
    args = ['read', '--execute-live-read', '--token-input', 'resident-memory']
    for key, artifact in [('fixture','fixture.json'), ('metadata','acquisition.json'), ('authorization','authorization.json'),
        ('receipt','phase3-receipt.json'), ('operational-receipt','phase4-receipt.json'), ('pin','read-pin.json'), ('configuration','operator.json')]:
        args += ['--' + key, str(config.path(artifact) if key != argument else Path(config.storage_root)/'wrong.json')]
    monkeypatch.setattr(operator, 'execute_read', lambda **kw: pytest.fail('substituted read path'))
    with pytest.raises(frozen.QualificationError):
        operator.dispatch(operator.session_parser().parse_args(args), config, positive['review'], positive['token'], positive['metadata'])


def test_inspection_rejects_arbitrary_secret_bearing_result(offline):
    config = offline['config']
    p3.write_json(config.path('create-intent.json'), setup.create_intent(config, offline['review']))
    p3.write_json(config.path('create-result.json'), {'outcome':'UNKNOWN', 'raw': BEARER})
    with pytest.raises(frozen.QualificationError): operator.inspect_artifacts(config, offline['review'])


def test_oauth_explicit_flag_not_sufficient_when_pin_wrong(offline, client, tmp_path):
    path = tmp_path/'client.json'
    p3.write_json(path, client_file(client))
    with pytest.raises(credentials.CredentialRefused):
        setup.acquire(**{**offline, 'pin': {}}, client_path=path, execute_oauth=True,
            operator_confirmation=credentials.ACQUISITION_CONFIRMATION, present_url=lambda _: pytest.fail('UI with bad pin'))
    assert not offline['config'].path('oauth-intent.json').exists()


@pytest.mark.parametrize('action', ['stop', 'blocked', 'read', 'exception'])
def test_ephemeral_parent_worker_handoff_no_application_bearer_file(offline, prepared, monkeypatch, action, capsys):
    config = offline['config']
    monkeypatch.setattr(operator.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(operator.sys.stdout, 'isatty', lambda: True)
    monkeypatch.setattr(operator.resource, 'setrlimit', lambda *a: None)
    acquisitions, actions = [], []
    def acquire(*a, **kw):
        acquisitions.append('oauth')
        return prepared
    monkeypatch.setattr(setup, 'acquire', acquire)
    if action == 'stop': line = 'stop'
    elif action in ('blocked', 'exception'): line = 'post-setup-preflight'
    else:
        line = 'read --execute-live-read --token-input resident-memory'
        for key, artifact in [('fixture','fixture.json'), ('metadata','acquisition.json'), ('authorization','authorization.json'),
            ('receipt','phase3-receipt.json'), ('operational-receipt','phase4-receipt.json'), ('pin','read-pin.json'), ('configuration','operator.json')]:
            line += ' --' + key + ' ' + str(config.path(artifact))
    monkeypatch.setattr('builtins.input', lambda _: line)
    def dispatch(args, configuration, review, token, metadata):
        actions.append(args.action)
        assert token is prepared[0] and metadata is prepared[1]
        if action == 'exception': raise RuntimeError(BEARER)
        return {'status':'BLOCKED' if action == 'blocked' else 'PASS'}
    monkeypatch.setattr(operator, 'dispatch', dispatch)
    if action == 'exception':
        with pytest.raises(credentials.CredentialRefused) as error:
            operator.resident_session(config, Path('/explicit/private/client'), execute_oauth=True,
                operator_confirmation=credentials.ACQUISITION_CONFIRMATION)
        assert error.value.__context__ is None
    else:
        assert operator.resident_session(config, Path('/explicit/private/client'), execute_oauth=True,
            operator_confirmation=credentials.ACQUISITION_CONFIRMATION) == (2 if action == 'blocked' else 0)
    assert acquisitions == ['oauth']
    assert len(actions) == (0 if action == 'stop' else 1)
    assert BEARER not in capsys.readouterr().out
    assert BEARER.encode() not in b''.join(p.read_bytes() for p in Path(config.storage_root).iterdir() if p.is_file())


def test_registry_unknown_file_blocks(offline):
    path = Path(offline['config'].runtime().registry_root) / 'arbitrary-private-file'
    path.touch(mode=0o600)
    assert control.offline_preflight(**offline)['status'] == 'BLOCKED'


@pytest.mark.parametrize('stage', ['after-post-preflight', 'after-phase3-issuance'])
def test_issuance_rechecks_fresh_minimum_lifetime_after_local_work(positive, monkeypatch, stage):
    wall = {'now': time.time()}
    monkeypatch.setattr(time, 'time', lambda: wall['now'])
    if stage == 'after-post-preflight':
        original = control.post_setup_preflight
        def delayed(**kwargs):
            result = original(**kwargs)
            assert result['status'] == 'PASS'
            wall['now'] = positive['token'].expires_at - 901
            return result
        monkeypatch.setattr(control, 'post_setup_preflight', delayed)
    else:
        original = p3.issue_authorization
        def delayed(**kwargs):
            result = original(**kwargs)
            wall['now'] = positive['token'].expires_at - 901
            return result
        monkeypatch.setattr(p3, 'issue_authorization', delayed)
    with pytest.raises(credentials.CredentialRefused): issue(positive)
    assert not positive['config'].path('authorization.json').exists()
    assert positive['config'].path('issue-intent.json').exists() == (stage == 'after-phase3-issuance')


def successor_path(config):
    root = Path(config.storage_root)
    return root.with_name(root.name + '-at-' + NEXT_HEAD)


def allow_successor_head(monkeypatch):
    monkeypatch.setattr(p3, 'repository_check', lambda head: p2.require(head == NEXT_HEAD))


def test_prelive_supersession_preserves_old_bytes_and_starts_fresh(offline, monkeypatch):
    config = offline['config']
    assert offline['attestation']['runtime_sha256'] == control.hash_public(offline['pin'])
    old_root = Path(config.storage_root)
    files = ('operator.json', 'client-review.json', 'startup.json', 'offline-pin.json')
    before = {name: (sha256_hex((old_root / name).read_bytes()), (old_root / name).stat().st_mtime_ns)
              for name in files}
    allow_successor_head(monkeypatch)
    result = control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    new_root = successor_path(config)
    assert result['successor'] == str(new_root) and result['network'] == 'not-performed'
    assert {name: (sha256_hex((old_root / name).read_bytes()), (old_root / name).stat().st_mtime_ns)
            for name in files} == before
    assert sorted(p.name for p in old_root.iterdir()) == sorted([*files, 'registry'])
    assert sorted(p.name for p in new_root.iterdir()) == ['operator.json', 'registry', 'supersession.json']
    assert not list((new_root / 'registry').iterdir())
    new_config = inherited._typed(p3.load_json(new_root / 'operator.json'), control.OperatorConfiguration)
    assert new_config.expected_head == NEXT_HEAD and new_config.storage_root == str(new_root)
    assert new_config.runtime().registry_root == str(new_root / 'registry')
    assert control.storage_check(new_config)['secrets'] == 'excluded'
    record = p3.load_json(new_root / 'supersession.json')
    assert record['predecessor_expected_head'] == HEAD
    assert record['offline_files_present'] == sorted(files)
    assert record['no_live_boundary_artifacts'] is True
    assert json.loads((frozen.SHEETS_DOCS / 'SHEETS_PHASE4_OPERATOR_CONFIGURATION_DRAFT.json').read_text())['expected_head'] is None


def test_stale_but_internally_bound_predecessor_pin_remains_supersedable(offline, monkeypatch, tmp_path):
    config = offline['config']
    pin = p3.load_json(config.path('offline-pin.json'))
    pin['python_executable'] = str(tmp_path / 'former-python')
    startup_record = p3.load_json(config.path('startup.json'))
    startup_record['runtime_sha256'] = control.hash_public(pin)
    config.path('offline-pin.json').write_bytes(canonical_json_bytes(pin) + b'\n')
    config.path('startup.json').write_bytes(canonical_json_bytes(startup_record) + b'\n')
    assert pin != control.runtime_projection(config, offline['review'])
    allow_successor_head(monkeypatch)
    assert control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)['successor'] == str(successor_path(config))


@pytest.mark.parametrize('tamper', ['startup_digest', 'offline_pin'])
def test_stored_startup_and_pin_must_remain_bound(offline, monkeypatch, tmp_path, tamper):
    config = offline['config']
    if tamper == 'startup_digest':
        path = config.path('startup.json')
        record = p3.load_json(path)
        record['runtime_sha256'] = 'f' * 64
        assert record['runtime_sha256'] != control.hash_public(offline['pin'])
    else:
        path = config.path('offline-pin.json')
        record = p3.load_json(path)
        record['python_executable'] = str(tmp_path / 'alternate-python')
        assert control.hash_public(record) != offline['attestation']['runtime_sha256']
    path.write_bytes(canonical_json_bytes(record) + b'\n')
    assert p3.load_json(path) == record
    allow_successor_head(monkeypatch)
    with pytest.raises(frozen.QualificationError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    assert not successor_path(config).exists()


def test_successor_requires_fresh_review_startup_pin_before_preflight(offline, reviewed, monkeypatch):
    allow_successor_head(monkeypatch)
    config = offline['config']
    control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    new_root = successor_path(config)
    successor = inherited._typed(p3.load_json(new_root / 'operator.json'), control.OperatorConfiguration)
    assert operator.main(['phase4-preflight', '--configuration', str(new_root / 'operator.json')]) == 2
    p3.write_json(successor.path('client-review.json'), reviewed)
    attestation = control.startup(successor, reviewed, dict.fromkeys(control.ASSUMPTIONS, True))
    p3.write_json(successor.path('startup.json'), attestation)
    pin = control.runtime_projection(successor, reviewed)
    p3.write_json(successor.path('offline-pin.json'), pin)
    assert control.offline_preflight(successor, reviewed, attestation, pin)['status'] == 'PASS'


@pytest.mark.parametrize('artifact', [name for name in control.FILES if name not in control.PRELIVE_FILES])
def test_every_phase4_live_boundary_artifact_blocks_supersession(offline, monkeypatch, artifact):
    allow_successor_head(monkeypatch)
    config = offline['config']
    p3.write_json(config.path(artifact), {})
    with pytest.raises(frozen.QualificationError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    assert not successor_path(config).exists()
    assert config.path(artifact).exists()


@pytest.mark.parametrize('name', ['reservation-TEST_ONLY_fixture.json', 'claim-TEST_ONLY_authorization.json',
                                  'attempt-TEST_ONLY_authorization.jsonl', 'registry.lock'])
def test_nonempty_registry_blocks_supersession(offline, monkeypatch, name):
    allow_successor_head(monkeypatch)
    config = offline['config']
    p3.write_json(Path(config.runtime().registry_root) / name, {})
    with pytest.raises(frozen.QualificationError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    assert not successor_path(config).exists()


@pytest.mark.parametrize('attack', ['unknown', 'hardlink'])
def test_unknown_file_or_hardlink_blocks_supersession(offline, monkeypatch, tmp_path, attack):
    allow_successor_head(monkeypatch)
    config = offline['config']
    if attack == 'unknown':
        p3.write_json(Path(config.storage_root) / 'paper-observation.json', {})
    else:
        os.link(config.path('operator.json'), tmp_path / 'other-link')
    with pytest.raises(frozen.QualificationError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    assert not successor_path(config).exists()


@pytest.mark.parametrize('attack', ['existing', 'symlink'])
def test_existing_or_symlink_destination_refuses_without_overwrite(offline, monkeypatch, tmp_path, attack):
    allow_successor_head(monkeypatch)
    config = offline['config']
    destination = successor_path(config)
    if attack == 'existing':
        destination.mkdir(mode=0o700)
        (destination / 'marker').write_text('preserve')
    else:
        destination.symlink_to(tmp_path)
    with pytest.raises(FileExistsError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    if attack == 'existing': assert (destination / 'marker').read_text() == 'preserve'
    else: assert destination.is_symlink()


@pytest.mark.parametrize('stage', [1, 6])
def test_directory_fsync_failure_leaves_inactive_successor(offline, monkeypatch, stage):
    allow_successor_head(monkeypatch)
    config = offline['config']
    original = control._fsync_directory
    calls = []
    def failing(path):
        calls.append(str(path))
        if len(calls) == stage:
            raise OSError('synthetic fsync failure')
        return original(path)
    monkeypatch.setattr(control, '_fsync_directory', failing)
    with pytest.raises(OSError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    destination = successor_path(config)
    assert destination.exists() and config.path('operator.json').exists()
    successor = replace(config, storage_root=str(destination), expected_head=NEXT_HEAD,
                        read={**config.read, 'registry_root': str(destination / 'registry')})
    with pytest.raises(Exception):
        control.storage_check(successor)


def test_final_predecessor_recheck_blocks_late_oauth_intent(offline, monkeypatch):
    allow_successor_head(monkeypatch)
    config = offline['config']
    destination = successor_path(config)
    original = control._fsync_directory
    injected = []
    def inject_after_final_link_fsync(path):
        original(path)
        if path == destination and (destination / 'supersession.json').exists() and not injected:
            p3.write_json(config.path('oauth-intent.json'), {})
            injected.append(True)
    monkeypatch.setattr(control, '_fsync_directory', inject_after_final_link_fsync)
    with pytest.raises(frozen.QualificationError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    assert injected and config.path('oauth-intent.json').exists()
    assert (destination / 'supersession.pending.json').exists()
    assert (destination / 'supersession.json').exists()
    assert (destination / 'supersession.json').stat().st_nlink == 2
    successor = replace(config, storage_root=str(destination), expected_head=NEXT_HEAD,
                        read={**config.read, 'registry_root': str(destination / 'registry')})
    with pytest.raises(frozen.QualificationError):
        control.storage_check(successor)
    assert [p for p in destination.parent.iterdir() if p.name.startswith(Path(config.storage_root).name + '-at-')] == [destination]


def test_partial_operator_write_and_wrong_head_fail_closed(offline, monkeypatch):
    config = offline['config']
    allow_successor_head(monkeypatch)
    with pytest.raises(frozen.QualificationError):
        control.supersede_prelive(config, HEAD, control.SUPERSESSION_CONFIRMATION)
    with pytest.raises(frozen.QualificationError):
        control.supersede_prelive(config, NEXT_HEAD, 'no-confirmation')
    assert not successor_path(config).exists()
    real_write = p3.write_json
    def failing(path, value):
        if path.name == 'operator.json' and path.parent == successor_path(config):
            raise OSError('synthetic crash before operator')
        return real_write(path, value)
    monkeypatch.setattr(p3, 'write_json', failing)
    with pytest.raises(OSError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    destination = successor_path(config)
    assert (destination / 'supersession.pending.json').exists()
    assert not (destination / 'operator.json').exists()


def test_supersession_cli_is_offline_and_reports_successor(offline, monkeypatch, capsys):
    allow_successor_head(monkeypatch)
    config = offline['config']
    assert operator.main(['supersede-prelive', '--configuration', str(config.path('operator.json')),
        '--new-expected-head', NEXT_HEAD,
        '--operator-confirmation', control.SUPERSESSION_CONFIRMATION]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['successor'] == str(successor_path(config))
    assert result['network'] == 'not-performed' and result['live_go'] == 'CLOSED'


def test_two_processes_cannot_create_two_successors(offline):
    config = offline['config']
    child = '''
import http.client, socket, ssl, sys, urllib.request, webbrowser
from pathlib import Path
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_operator as op
from retry_semantics.study2 import sheets_phase4_control as p4
def denied(*a, **kw):
    raise AssertionError("network/browser forbidden")
for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
    setattr(socket, name, denied)
http.client.HTTPSConnection.connect = denied
ssl.SSLContext.wrap_socket = denied
urllib.request.urlopen = denied
webbrowser.open = denied
p3.repository_check = lambda head: p2.require(head == "b" * 40)
config = op._typed(p3.load_json(Path(sys.argv[1])), p4.OperatorConfiguration)
try:
    p4.supersede_prelive(config, "b" * 40, p4.SUPERSESSION_CONFIRMATION)
    print("WIN")
except Exception as error:
    print(type(error).__name__, file=sys.stderr)
    print("BLOCK")
'''
    processes = [subprocess.Popen([sys.executable, '-c', child, str(config.path('operator.json'))],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={}) for _ in range(2)]
    outputs = [process.communicate(timeout=30) for process in processes]
    assert sorted(output.strip() for output, _ in outputs) == ['BLOCK', 'WIN'], outputs
    assert all(process.returncode == 0 for process in processes)
    assert sorted(p.name for p in successor_path(config).iterdir()) == ['operator.json', 'registry', 'supersession.json']


def acquisition_attempt_path(config):
    root = Path(config.storage_root)
    return root.with_name(root.name + '-acquisition-at-' + NEXT_HEAD)


@pytest.fixture
def spent_oauth(offline):
    config = offline['config']
    p3.write_json(config.path('oauth-intent.json'), setup.oauth_intent(config, offline['review']))
    return offline


def test_reviewed_new_acquisition_preserves_predecessor_and_starts_fresh(spent_oauth, monkeypatch):
    allow_successor_head(monkeypatch)
    config = spent_oauth['config']
    old_root = Path(config.storage_root)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in old_root.iterdir() if p.is_file()}
    assert not list((old_root / 'registry').iterdir())
    with pytest.raises(frozen.QualificationError):
        control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    assert not successor_path(config).exists()
    result = control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    destination = acquisition_attempt_path(config)
    assert result['new_attempt'] == str(destination) and result['network'] == 'not-performed'
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in old_root.iterdir() if p.is_file()} == before
    assert sorted(p.name for p in destination.iterdir()) == ['acquisition-attempt.json', 'operator.json', 'registry']
    assert not list((destination / 'registry').iterdir())
    fresh = inherited._typed(p3.load_json(destination / 'operator.json'), control.OperatorConfiguration)
    assert fresh.expected_head == NEXT_HEAD and fresh.runtime().registry_root == str(destination / 'registry')
    assert control.storage_check(fresh)['secrets'] == 'excluded'
    provenance = p3.load_json(destination / 'acquisition-attempt.json')
    assert provenance['predecessor_oauth_intent_sha256'] == control.hash_public(
        setup.oauth_intent(config, spent_oauth['review']))
    assert provenance['offline_files_present'] == sorted([*before])
    assert provenance['no_accepted_local_acquisition_artifact'] is True
    assert provenance['no_sheets_side_artifacts'] is True
    assert operator.main(['phase4-preflight', '--configuration', str(destination / 'operator.json')]) == 2
    p3.write_json(fresh.path('client-review.json'), spent_oauth['review'])
    attestation = control.startup(fresh, spent_oauth['review'], dict.fromkeys(control.ASSUMPTIONS, True))
    pin = control.runtime_projection(fresh, spent_oauth['review'])
    p3.write_json(fresh.path('startup.json'), attestation)
    p3.write_json(fresh.path('offline-pin.json'), pin)
    assert control.offline_preflight(fresh, spent_oauth['review'], attestation, pin)['status'] == 'PASS'
    assert json.loads((frozen.SHEETS_DOCS / 'SHEETS_PHASE4_OPERATOR_CONFIGURATION_DRAFT.json').read_text())['expected_head'] is None


def test_new_acquisition_from_valid_prelive_successor(offline, monkeypatch):
    allow_successor_head(monkeypatch)
    config = offline['config']
    control.supersede_prelive(config, NEXT_HEAD, control.SUPERSESSION_CONFIRMATION)
    predecessor = inherited._typed(p3.load_json(successor_path(config) / 'operator.json'),
                                   control.OperatorConfiguration)
    review = offline['review']
    p3.write_json(predecessor.path('client-review.json'), review)
    attestation = control.startup(predecessor, review, dict.fromkeys(control.ASSUMPTIONS, True))
    p3.write_json(predecessor.path('startup.json'), attestation)
    p3.write_json(predecessor.path('offline-pin.json'), control.runtime_projection(predecessor, review))
    p3.write_json(predecessor.path('oauth-intent.json'), setup.oauth_intent(predecessor, review))
    monkeypatch.setattr(p3, 'repository_check', lambda head: p2.require(head == 'c' * 40))
    result = control.new_acquisition_attempt(predecessor, 'c' * 40,
                                             control.NEW_ACQUISITION_CONFIRMATION)
    fresh = inherited._typed(p3.load_json(Path(result['new_attempt']) / 'operator.json'),
                           control.OperatorConfiguration)
    assert control.storage_check(fresh)['secrets'] == 'excluded'
    assert p3.load_json(fresh.path('acquisition-attempt.json'))['offline_files_present'] == sorted([
        'operator.json', 'client-review.json', 'startup.json', 'offline-pin.json',
        'supersession.json', 'oauth-intent.json'])


@pytest.mark.parametrize('missing', ['client-review.json', 'startup.json', 'offline-pin.json'])
def test_new_acquisition_requires_complete_offline_package(spent_oauth, monkeypatch, missing):
    allow_successor_head(monkeypatch)
    config = spent_oauth['config']
    config.path(missing).unlink()
    with pytest.raises(Exception):
        control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    assert not acquisition_attempt_path(config).exists()


@pytest.mark.parametrize('artifact', [name for name in control.FILES if name not in
    control.SPENT_OAUTH_FILES | {'supersession.json', 'acquisition-attempt.json'}])
def test_every_other_artifact_blocks_new_acquisition(spent_oauth, monkeypatch, artifact):
    allow_successor_head(monkeypatch)
    config = spent_oauth['config']
    p3.write_json(config.path(artifact), {})
    with pytest.raises(Exception):
        control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    assert not acquisition_attempt_path(config).exists()


@pytest.mark.parametrize('attack', ['missing-intent', 'malformed-intent', 'unknown-root', 'registry',
                                    'wrong-confirmation', 'same-head'])
def test_new_acquisition_ineligible_states_fail_before_creation(spent_oauth, monkeypatch, attack):
    allow_successor_head(monkeypatch)
    config = spent_oauth['config']
    if attack == 'missing-intent': config.path('oauth-intent.json').unlink()
    if attack == 'malformed-intent': config.path('oauth-intent.json').write_bytes(b'{}\n')
    if attack == 'unknown-root': p3.write_json(Path(config.storage_root) / 'paper-observation.json', {})
    if attack == 'registry': p3.write_json(Path(config.runtime().registry_root) / 'registry.lock', {})
    confirmation = 'wrong' if attack == 'wrong-confirmation' else control.NEW_ACQUISITION_CONFIRMATION
    head = HEAD if attack == 'same-head' else NEXT_HEAD
    with pytest.raises(Exception): control.new_acquisition_attempt(config, head, confirmation)
    assert not acquisition_attempt_path(config).exists()


@pytest.mark.parametrize('attack', ['existing', 'symlink'])
def test_new_acquisition_destination_collision(spent_oauth, monkeypatch, tmp_path, attack):
    allow_successor_head(monkeypatch)
    config = spent_oauth['config']
    destination = acquisition_attempt_path(config)
    if attack == 'existing':
        destination.mkdir(mode=0o700)
        (destination / 'marker').write_text('preserve')
    else:
        destination.symlink_to(tmp_path)
    with pytest.raises(FileExistsError):
        control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    if attack == 'existing': assert (destination / 'marker').read_text() == 'preserve'
    else: assert destination.is_symlink()


@pytest.mark.parametrize('stage', [1, 6])
def test_new_acquisition_fsync_failure_leaves_blocked_residue(spent_oauth, monkeypatch, stage):
    allow_successor_head(monkeypatch)
    config = spent_oauth['config']
    original = control._fsync_directory
    calls = []
    def failing(path):
        calls.append(path)
        if len(calls) == stage: raise OSError('synthetic fsync failure')
        return original(path)
    monkeypatch.setattr(control, '_fsync_directory', failing)
    with pytest.raises(OSError):
        control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    destination = acquisition_attempt_path(config)
    assert destination.exists()
    fresh = replace(config, storage_root=str(destination), expected_head=NEXT_HEAD,
                    read={**config.read, 'registry_root': str(destination / 'registry')})
    with pytest.raises(Exception): control.storage_check(fresh)


def test_new_acquisition_late_predecessor_change_blocks_activation(spent_oauth, monkeypatch):
    allow_successor_head(monkeypatch)
    config = spent_oauth['config']
    destination = acquisition_attempt_path(config)
    original = control._fsync_directory
    injected = []
    def mutate(path):
        original(path)
        if path == destination and (destination / 'acquisition-attempt.json').exists() and not injected:
            p3.write_json(config.path('acquisition.json'), {})
            injected.append(True)
    monkeypatch.setattr(control, '_fsync_directory', mutate)
    with pytest.raises(frozen.QualificationError):
        control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    assert injected and (destination / 'acquisition-attempt.pending.json').exists()
    assert (destination / 'acquisition-attempt.json').stat().st_nlink == 2
    fresh = replace(config, storage_root=str(destination), expected_head=NEXT_HEAD,
                    read={**config.read, 'registry_root': str(destination / 'registry')})
    with pytest.raises(frozen.QualificationError): control.storage_check(fresh)


def test_new_acquisition_cli_is_offline(spent_oauth, monkeypatch, capsys):
    allow_successor_head(monkeypatch)
    config = spent_oauth['config']
    assert operator.main(['new-acquisition-attempt', '--configuration', str(config.path('operator.json')),
        '--new-expected-head', NEXT_HEAD, '--operator-confirmation',
        control.NEW_ACQUISITION_CONFIRMATION]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['new_attempt'] == str(acquisition_attempt_path(config))
    assert result['network'] == 'not-performed' and result['live_go'] == 'CLOSED'


def test_two_processes_cannot_create_two_new_acquisition_packages(spent_oauth):
    config = spent_oauth['config']
    child = '''
import http.client, socket, ssl, sys, urllib.request, webbrowser
from pathlib import Path
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_operator as op
from retry_semantics.study2 import sheets_phase4_control as p4
def denied(*a, **kw): raise AssertionError("network/browser forbidden")
for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
    setattr(socket, name, denied)
http.client.HTTPSConnection.connect = denied
ssl.SSLContext.wrap_socket = denied
urllib.request.urlopen = denied
webbrowser.open = denied
p3.repository_check = lambda head: p2.require(head == "b" * 40)
config = op._typed(p3.load_json(Path(sys.argv[1])), p4.OperatorConfiguration)
try:
    p4.new_acquisition_attempt(config, "b" * 40, p4.NEW_ACQUISITION_CONFIRMATION)
    print("WIN")
except Exception:
    print("BLOCK")
'''
    processes = [subprocess.Popen([sys.executable, '-c', child, str(config.path('operator.json'))],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={}) for _ in range(2)]
    outputs = [process.communicate(timeout=30) for process in processes]
    assert sorted(output.strip() for output, _ in outputs) == ['BLOCK', 'WIN'], outputs
    assert all(process.returncode == 0 for process in processes)
    assert sorted(p.name for p in acquisition_attempt_path(config).iterdir()) == [
        'acquisition-attempt.json', 'operator.json', 'registry']


def unused_acquisition_path(config):
    return control._unused_acquisition_successor_root(config.storage_root)


def test_unused_success_name_is_fixed_size_and_path_bound(unused_success):
    root = Path(unused_success['config'].storage_root)
    assert 'os' in unused_success['pin']['phase4_support_implementations']
    long = root.with_name('L' * 236)
    chained = root.with_name('Q' * 180 + '-acquisition-at-' + 'c' * 40)
    names = [control._unused_acquisition_successor_root(path).name for path in (root, long, chained)]
    assert all(name.startswith(control.UNUSED_SUCCESSOR_PREFIX) for name in names)
    assert all(len(name.encode('utf-8')) == 107 for name in names)
    assert len(set(names)) == 3
    assert control._unused_acquisition_successor_root(root) == control._unused_acquisition_successor_root(str(root))
    assert control._unused_acquisition_successor_root(root).parent == root.parent


def test_real_length_synthetic_predecessor_creates_short_successor(offline, prepared, monkeypatch):
    original, review = offline['config'], offline['review']
    long_root = Path(original.storage_root).with_name('L' * 236)
    long_root.mkdir(mode=0o700)
    (long_root / 'registry').mkdir(mode=0o700)
    config = replace(original, storage_root=str(long_root),
        read={**original.read, 'registry_root': str(long_root / 'registry')})
    p3.write_json(config.path('operator.json'), config.projection())
    p3.write_json(config.path('client-review.json'), review)
    attestation = control.startup(config, review, dict.fromkeys(control.ASSUMPTIONS, True))
    p3.write_json(config.path('startup.json'), attestation)
    p3.write_json(config.path('offline-pin.json'), control.runtime_projection(config, review))
    persist_acquisition(config, review, prepared)
    destination = unused_acquisition_path(config)
    assert len(long_root.name.encode('utf-8')) == 236
    assert len(destination.name.encode('utf-8')) == 107
    assert len(destination.name.encode('utf-8')) <= os.pathconf(long_root.parent, 'PC_NAME_MAX')
    allow_successor_head(monkeypatch)
    result = control.supersede_unused_acquisition(config, NEXT_HEAD,
                                                  control.UNUSED_ACQUISITION_CONFIRMATION)
    assert result['successor'] == str(destination)
    fresh = inherited._typed(p3.load_json(destination / 'operator.json'), control.OperatorConfiguration)
    assert control.storage_check(fresh)['secrets'] == 'excluded'


@pytest.fixture
def unused_success(offline, prepared):
    persist_acquisition(offline['config'], offline['review'], prepared)
    return offline


def test_supersede_unused_success_preserves_predecessor_and_starts_fresh(unused_success, monkeypatch, capsys):
    allow_successor_head(monkeypatch)
    config, review = unused_success['config'], unused_success['review']
    old = Path(config.storage_root)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in old.iterdir() if p.is_file()}
    assert not list((old / 'registry').iterdir())
    with pytest.raises(frozen.QualificationError):
        control.new_acquisition_attempt(config, NEXT_HEAD, control.NEW_ACQUISITION_CONFIRMATION)
    result = control.supersede_unused_acquisition(config, NEXT_HEAD,
                                                  control.UNUSED_ACQUISITION_CONFIRMATION)
    destination = unused_acquisition_path(config)
    assert result['successor'] == str(destination) and result['live_go'] == 'CLOSED'
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in old.iterdir() if p.is_file()} == before
    assert sorted(p.name for p in destination.iterdir()) == [
        'operator.json', 'registry', 'unused-acquisition-supersession.json']
    assert not list((destination / 'registry').iterdir())
    fresh = inherited._typed(p3.load_json(destination / 'operator.json'), control.OperatorConfiguration)
    assert fresh.expected_head == NEXT_HEAD and fresh.runtime().registry_root == str(destination / 'registry')
    provenance = p3.load_json(destination / 'unused-acquisition-supersession.json')
    assert provenance['schema'] == 'sheets-phase4-reviewed-unused-acquisition-supersession-v1'
    assert provenance['predecessor_oauth_intent_sha256'] == control.hash_public(
        setup.oauth_intent(config, review))
    assert provenance['predecessor_acquisition_sha256'] == control.hash_public(
        p3.load_json(config.path('acquisition.json')))
    assert provenance['offline_files_present'] == sorted(before)
    assert provenance['operator_attested_session_stopped_before_provisioning'] is True
    assert provenance['fresh_oauth_required'] is True and provenance['no_credential_inherited'] is True
    assert BEARER.encode() not in b''.join(p.read_bytes() for p in destination.iterdir() if p.is_file())
    assert control.storage_check(fresh)['secrets'] == 'excluded'
    assert operator.main(['inspect', '--configuration', str(fresh.path('operator.json'))]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection['next_action'] == 'fresh-client-review-required'
    assert operator.main(['phase4-preflight', '--configuration', str(fresh.path('operator.json'))]) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'BLOCKED'
    p3.write_json(fresh.path('client-review.json'), review)
    attestation = control.startup(fresh, review, dict.fromkeys(control.ASSUMPTIONS, True))
    pin = control.runtime_projection(fresh, review)
    p3.write_json(fresh.path('startup.json'), attestation)
    p3.write_json(fresh.path('offline-pin.json'), pin)
    assert control.offline_preflight(fresh, review, attestation, pin)['status'] == 'PASS'
    assert operator.inspect_artifacts(fresh, review)['next_action'] == 'fresh-oauth-requires-separate-approval'
    with pytest.raises(FileExistsError):
        control.supersede_unused_acquisition(config, NEXT_HEAD, control.UNUSED_ACQUISITION_CONFIRMATION)


@pytest.mark.parametrize('attack', [
    'create-intent.json', 'create-result.json', 'provisioning.json', 'fixture.json',
    'acquisition-failure.json', 'missing-acquisition', 'unknown-root', 'registry',
    'authorization.json', 'read-pin.json', 'read-intent.json', 'result.json',
    'malformed-acquisition', 'wrong-acquisition-review', 'wrong-refresh-persistence',
    'wrong-pin-head', 'wrong-startup-hash', 'wrong-oauth-intent',
    'wrong-confirmation', 'same-head',
])
def test_unused_success_ineligible_predecessor_rejected(unused_success, monkeypatch, attack):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    if attack == 'missing-acquisition':
        config.path('acquisition.json').unlink()
    elif attack == 'unknown-root':
        p3.write_json(Path(config.storage_root) / 'unknown.json', {})
    elif attack == 'registry':
        p3.write_json(Path(config.runtime().registry_root) / 'registry.lock', {})
    elif attack == 'malformed-acquisition':
        config.path('acquisition.json').write_bytes(b'{}\n')
    elif attack == 'wrong-acquisition-review':
        value = p3.load_json(config.path('acquisition.json'))
        value['public_config_sha256'] = '0' * 64
        config.path('acquisition.json').write_bytes(canonical_json_bytes(value) + b'\n')
    elif attack == 'wrong-refresh-persistence':
        value = p3.load_json(config.path('acquisition.json'))
        value['refresh_persistence'] = 'disk'
        config.path('acquisition.json').write_bytes(canonical_json_bytes(value) + b'\n')
    elif attack == 'wrong-pin-head':
        value = p3.load_json(config.path('offline-pin.json'))
        value['expected_head'] = NEXT_HEAD
        config.path('offline-pin.json').write_bytes(canonical_json_bytes(value) + b'\n')
    elif attack == 'wrong-startup-hash':
        value = p3.load_json(config.path('startup.json'))
        value['runtime_sha256'] = '0' * 64
        config.path('startup.json').write_bytes(canonical_json_bytes(value) + b'\n')
    elif attack == 'wrong-oauth-intent':
        config.path('oauth-intent.json').write_bytes(b'{}\n')
    elif attack in control.FILES:
        p3.write_json(config.path(attack), {})
    confirmation = ('wrong' if attack == 'wrong-confirmation' else
                    control.UNUSED_ACQUISITION_CONFIRMATION)
    head = HEAD if attack == 'same-head' else NEXT_HEAD
    with pytest.raises(Exception):
        control.supersede_unused_acquisition(config, head, confirmation)
    assert not unused_acquisition_path(config).exists()


def test_unused_success_one_shot_even_with_different_later_head(unused_success, monkeypatch):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    control.supersede_unused_acquisition(config, NEXT_HEAD,
                                          control.UNUSED_ACQUISITION_CONFIRMATION)
    monkeypatch.setattr(p3, 'repository_check', lambda head: p2.require(head == 'c' * 40))
    with pytest.raises(FileExistsError):
        control.supersede_unused_acquisition(config, 'c' * 40,
                                              control.UNUSED_ACQUISITION_CONFIRMATION)
    assert sorted(p.name for p in unused_acquisition_path(config).iterdir()) == [
        'operator.json', 'registry', 'unused-acquisition-supersession.json']


@pytest.mark.parametrize('limit', ['too-small', 'zero', 'unknown', 'invalid-type', 'error'])
def test_unused_success_name_max_fail_closed(unused_success, monkeypatch, limit):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    destination = unused_acquisition_path(config)
    observed = []
    def pathconf(parent, key):
        observed.append((parent, key))
        if limit == 'error': raise OSError('synthetic pathconf failure')
        return {'too-small': len(destination.name.encode('utf-8')) - 1,
                'zero': 0, 'unknown': -1, 'invalid-type': '255'}[limit]
    monkeypatch.setattr(control.os, 'pathconf', pathconf)
    with pytest.raises(Exception):
        control.supersede_unused_acquisition(config, NEXT_HEAD,
                                              control.UNUSED_ACQUISITION_CONFIRMATION)
    assert observed == [(destination.parent, 'PC_NAME_MAX')]
    assert not destination.exists()


@pytest.mark.parametrize('attack', ['predecessor-root', 'successor-root'])
def test_unused_success_forged_naming_provenance_rejected(unused_success, monkeypatch, attack):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    control.supersede_unused_acquisition(config, NEXT_HEAD,
                                          control.UNUSED_ACQUISITION_CONFIRMATION)
    destination = unused_acquisition_path(config)
    fresh = inherited._typed(p3.load_json(destination / 'operator.json'), control.OperatorConfiguration)
    path = destination / 'unused-acquisition-supersession.json'
    record = p3.load_json(path)
    if attack == 'predecessor-root':
        record['predecessor_root'] = str(Path(config.storage_root).with_name('different-sibling'))
    else:
        record['successor_root'] = str(Path(config.storage_root))
    path.write_bytes(canonical_json_bytes(record) + b'\n')
    with pytest.raises(frozen.QualificationError): control.storage_check(fresh)


def test_unused_success_dedicated_prefix_without_provenance_rejected(unused_success):
    config = unused_success['config']
    destination = unused_acquisition_path(config)
    destination.mkdir(mode=0o700)
    (destination / 'registry').mkdir(mode=0o700)
    fresh = replace(config, storage_root=str(destination), expected_head=NEXT_HEAD,
                    read={**config.read, 'registry_root': str(destination / 'registry')})
    p3.write_json(fresh.path('operator.json'), fresh.projection())
    with pytest.raises(Exception): control.storage_check(fresh)


def test_short_unused_successor_allows_later_prelive_supersession(unused_success, monkeypatch):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    control.supersede_unused_acquisition(config, NEXT_HEAD,
                                          control.UNUSED_ACQUISITION_CONFIRMATION)
    destination = unused_acquisition_path(config)
    fresh = inherited._typed(p3.load_json(destination / 'operator.json'), control.OperatorConfiguration)
    assert control.storage_check(fresh)['secrets'] == 'excluded'
    monkeypatch.setattr(p3, 'repository_check', lambda head: p2.require(head == 'c' * 40))
    result = control.supersede_prelive(fresh, 'c' * 40, control.SUPERSESSION_CONFIRMATION)
    later = inherited._typed(p3.load_json(Path(result['successor']) / 'operator.json'),
                             control.OperatorConfiguration)
    assert control.storage_check(later)['secrets'] == 'excluded'
    assert len(Path(result['successor']).name.encode('utf-8')) == 151


def test_superseded_predecessor_cannot_provision_under_new_head(unused_success, prepared, monkeypatch):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    control.supersede_unused_acquisition(config, NEXT_HEAD,
                                          control.UNUSED_ACQUISITION_CONFIRMATION)
    monkeypatch.setattr(setup.http.client, 'HTTPSConnection',
                        lambda *a, **kw: pytest.fail('provider call from predecessor'))
    with pytest.raises(credentials.CredentialRefused):
        setup.provision(config, unused_success['review'], *prepared,
            execute_provisioning=True, operator_confirmation=setup.CREATE_CONFIRMATION)
    assert not config.path('create-intent.json').exists()


@pytest.mark.parametrize('attack', ['existing', 'symlink'])
def test_unused_success_destination_collision(unused_success, monkeypatch, tmp_path, attack):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    destination = unused_acquisition_path(config)
    if attack == 'existing':
        destination.mkdir(mode=0o700)
        (destination / 'marker').write_text('preserve')
    else:
        destination.symlink_to(tmp_path)
    with pytest.raises(FileExistsError):
        control.supersede_unused_acquisition(config, NEXT_HEAD,
                                              control.UNUSED_ACQUISITION_CONFIRMATION)
    if attack == 'existing': assert (destination / 'marker').read_text() == 'preserve'
    else: assert destination.is_symlink()


@pytest.mark.parametrize('stage', [1, 6])
def test_unused_success_fsync_failure_blocks_activation(unused_success, monkeypatch, stage):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    original = control._fsync_directory
    calls = []
    def failing(path):
        calls.append(path)
        if len(calls) == stage: raise OSError('synthetic fsync failure')
        return original(path)
    monkeypatch.setattr(control, '_fsync_directory', failing)
    with pytest.raises(OSError):
        control.supersede_unused_acquisition(config, NEXT_HEAD,
                                              control.UNUSED_ACQUISITION_CONFIRMATION)
    destination = unused_acquisition_path(config)
    assert destination.exists()
    fresh = replace(config, storage_root=str(destination), expected_head=NEXT_HEAD,
                    read={**config.read, 'registry_root': str(destination / 'registry')})
    with pytest.raises(Exception): control.storage_check(fresh)


def test_unused_success_late_predecessor_change_blocks_activation(unused_success, monkeypatch):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    destination = unused_acquisition_path(config)
    original = control._fsync_directory
    injected = []
    def mutate(path):
        original(path)
        if path == destination and (destination / 'unused-acquisition-supersession.json').exists() and not injected:
            p3.write_json(config.path('create-intent.json'), {})
            injected.append(True)
    monkeypatch.setattr(control, '_fsync_directory', mutate)
    with pytest.raises(frozen.QualificationError):
        control.supersede_unused_acquisition(config, NEXT_HEAD,
                                              control.UNUSED_ACQUISITION_CONFIRMATION)
    assert injected and (destination / 'unused-acquisition-supersession.pending.json').exists()
    fresh = replace(config, storage_root=str(destination), expected_head=NEXT_HEAD,
                    read={**config.read, 'registry_root': str(destination / 'registry')})
    with pytest.raises(frozen.QualificationError): control.storage_check(fresh)


def test_unused_success_wrong_source_head_rejected(unused_success, monkeypatch):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    with pytest.raises(frozen.QualificationError):
        control.supersede_unused_acquisition(config, 'c' * 40,
                                              control.UNUSED_ACQUISITION_CONFIRMATION)
    assert not unused_acquisition_path(config).exists()


def test_unused_success_cli_is_offline(unused_success, monkeypatch, capsys):
    allow_successor_head(monkeypatch)
    config = unused_success['config']
    assert operator.main(['supersede-unused-acquisition', '--configuration', str(config.path('operator.json')),
        '--new-expected-head', NEXT_HEAD, '--operator-confirmation',
        control.UNUSED_ACQUISITION_CONFIRMATION]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['successor'] == str(unused_acquisition_path(config))
    assert result['network'] == 'not-performed' and result['live_go'] == 'CLOSED'


def test_two_processes_cannot_supersede_unused_success_twice(unused_success):
    config = unused_success['config']
    child = '''
import http.client, socket, ssl, sys, urllib.request, webbrowser
from pathlib import Path
from retry_semantics.study2 import sheets_phase2_control as p2
from retry_semantics.study2 import sheets_phase3_control as p3
from retry_semantics.study2 import sheets_phase3_operator as op
from retry_semantics.study2 import sheets_phase4_control as p4
def denied(*a, **kw): raise AssertionError("network/browser forbidden")
for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
    setattr(socket, name, denied)
http.client.HTTPSConnection.connect = denied
ssl.SSLContext.wrap_socket = denied
urllib.request.urlopen = denied
webbrowser.open = denied
p3.repository_check = lambda head: p2.require(head == "b" * 40)
config = op._typed(p3.load_json(Path(sys.argv[1])), p4.OperatorConfiguration)
try:
    p4.supersede_unused_acquisition(config, "b" * 40, p4.UNUSED_ACQUISITION_CONFIRMATION)
    print("WIN")
except Exception:
    print("BLOCK")
'''
    processes = [subprocess.Popen([sys.executable, '-c', child, str(config.path('operator.json'))],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={}) for _ in range(2)]
    outputs = [process.communicate(timeout=30) for process in processes]
    assert sorted(output.strip() for output, _ in outputs) == ['BLOCK', 'WIN'], outputs
    assert all(process.returncode == 0 for process in processes)
    assert sorted(p.name for p in unused_acquisition_path(config).iterdir()) == [
        'operator.json', 'registry', 'unused-acquisition-supersession.json']
