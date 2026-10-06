"""Provider capability routing for an explicitly selected deployment partition."""
from __future__ import annotations
import json
import time
from retry_semantics.baselines import collection
from retry_semantics.baselines.partitions import assert_entry, selected_entries


def forbidden_provider(*args, **kwargs):
    raise collection.CollectionRefused('provider capability forbidden in selected partition')


def github_runtime(package):
    # Google OAuth modules and ticket execution are unreachable in this factory.
    from retry_semantics.study2.provider_paper_io import DurablePaperEvidence, PaperRequest, one_shot_http
    credential = None
    last_family = None
    def send(request):
        nonlocal credential
        if credential is None:
            from prepare_no_model_precollection import local_github_credential
            credential = local_github_credential()
        return one_shot_http(request, credential=credential)
    def before_family(entry, directory):
        nonlocal last_family
        assert_entry('github-vm', entry)
        if entry['source_family_id'] == last_family:
            return
        lock = package['lock']
        ev = DurablePaperEvidence(directory / 'family_preflight', provider='github',
            family_id=entry['source_family_id'], arm_id='FAMILY_PREFLIGHT_NOT_POLICY',
            manifest_sha256=lock['schedule_sha256'], runtime_sha256=package['execution_runtime_files'])
        values = []
        for url in ('https://api.github.com/user', 'https://api.github.com/repos/' + lock['github_repository'],
                    'https://api.github.com/rate_limit'):
            response = ev.record('FAMILY_READINESS_GET_NOT_POLICY_LIST', PaperRequest('GET', url,
                (('Accept', 'application/vnd.github.raw+json'), ('X-GitHub-Api-Version', '2022-11-28')), b''), send)
            if response.error or response.status != 200:
                raise collection.CollectionRefused('GitHub family access/quota preflight failed; stop')
            values.append(json.loads(response.body))
        user, repo, rate = values[0], values[1], values[2]['resources']['core']
        if (user.get('id') != lock['github_principal_id'] or repo.get('id') != lock['github_repository_id']
                or repo.get('full_name') != lock['github_repository'] or not repo.get('private')
                or not repo.get('has_issues') or rate.get('remaining', 0) < 180
                or rate.get('reset', 0) <= time.time()):
            raise collection.CollectionRefused('GitHub family scope/principal/quota differs; stop')
        last_family = entry['source_family_id']
    return send, before_family


def sheets_runtime(package, output, client):
    # GitHub credential loading is unreachable in this factory.
    from retry_semantics.study2.provider_paper_io import DurablePaperEvidence, one_shot_http
    import run_sheets_paper_live_readiness_session as oauth
    import run_sheets_paper_append_qualification_session as access
    from retry_semantics.study2.sheets_replication import PacedSession
    session = None
    last_family = None
    def send(request):
        if session is None:
            raise collection.CollectionRefused('Sheets session not qualified')
        return session.send(request)
    def before_family(entry, directory):
        nonlocal session, last_family
        assert_entry('sheets-mac', entry)
        if entry['source_family_id'] == last_family:
            return
        lock = package['lock']
        if session is None:
            ev = DurablePaperEvidence(output / 'sheets_session', provider='sheets',
                family_id='TOKEN_SESSION', arm_id='TOKEN_SESSION_NOT_POLICY',
                manifest_sha256=lock['schedule_sha256'], runtime_sha256=package['execution_runtime_files'])
            session = PacedSession(acquire=lambda: oauth.acquire_session_authority(client),
                transport=one_shot_http, event=ev.event)
        changed = session.ensure(2100)
        if session.app_identity != lock['sheets_app_public_sha256']:
            raise collection.CollectionRefused('Sheets OAuth app differs; stop')
        if changed:
            folder = directory / 'family_access'
            folder.mkdir()
            principal = access._drive_evidence(evidence_dir=folder,
                paper_id=package['sheets_topology']['spreadsheet_id'], bearer=session.token.value,
                drive_get=access.drive_get_once)[0]
            if principal != lock['sheets_principal']:
                raise collection.CollectionRefused('Sheets principal/ACL differs; stop')
        last_family = entry['source_family_id']
    return send, before_family


def executor_for(package, output, client):
    partition = package['partition']
    entries = selected_entries(package['schedule'], package['partition_manifest'], partition)
    frozen = {entry['schedule_index']: entry for entry in entries}
    github_send = sheets_send = before_family = forbidden_provider
    if partition == 'github-vm':
        github_send, before_family = github_runtime(package)
    elif partition == 'sheets-mac':
        sheets_send, before_family = sheets_runtime(package, output, client)
    elif partition != 'tickets-local':
        raise collection.CollectionRefused('no all-partitions execution mode')
    def execute(entry, directory):
        assert_entry(partition, entry)
        if frozen.get(entry['schedule_index']) != entry:
            raise collection.CollectionRefused('entry differs from selected frozen partition')
        return collection.execute_arm(entry, directory, package, github_send=github_send,
            sheets_send=sheets_send, before_provider_family=before_family)
    return execute
