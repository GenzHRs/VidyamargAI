import asyncio
import json
from datetime import datetime, timedelta
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect
from app.core.config import Settings, settings
from app.core.security import get_password_hash, verify_password, hash_token
from app.models.models import User, Candidate, CandidateResume, CandidateProfile, OTP, UserRefreshToken
from app.services.storage import storage_service, safe_object_path
from conftest import headers

@pytest.mark.parametrize('path', ['/api/v1/db-test', '/api/v1/auth/test-resend-directly'])
def test_diagnostics_removed(environment, path):
    client, *_ = environment
    assert client.get(path).status_code == 404

def test_health_and_openapi(environment):
    client, *_ = environment
    assert client.get('/health').json() == {'status': 'ok'}
    schema = client.get('/openapi.json').json()
    assert len(schema['paths']) > 80
    assert '/api/v1/db-test' not in schema['paths']

def test_secret_validation():
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY='short')
    with pytest.raises(ValidationError):
        Settings(HR_SYNC_SECRET='short')

def test_long_password_is_not_truncated():
    password = 'é' * 90
    hashed = get_password_hash(password)
    assert verify_password(password, hashed)
    assert not verify_password(password[:35], hashed)
    assert not verify_password('x', 'corrupt-hash')

@pytest.mark.parametrize('folder,name', [('..','outside'),('/tmp','outside'),('resumes','../outside'),('resumes','..\\outside'),('resumes','bad\nname')])
def test_path_traversal_rejected(environment, folder, name):
    with pytest.raises(ValueError):
        storage_service.upload_file(folder, name, b'private')
    with pytest.raises(ValueError):
        storage_service.get_file_content(folder, name)
    with pytest.raises(ValueError):
        storage_service.delete_file(folder, name)

def test_symlink_escape_rejected(environment, tmp_path):
    *_, root = environment
    try:
        (root/'escape').symlink_to(root.parent, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation not permitted by current OS user privileges")
    with pytest.raises(ValueError):
        safe_object_path('escape', 'outside')

def test_private_file_ownership(environment):
    client, db, owner, other, admin, candidate, _ = environment
    url = storage_service.upload_file('resumes','synthetic.pdf', b'%PDF-1.4 synthetic fixture', 'application/pdf')
    db.add(CandidateResume(candidate_id=candidate.id, resume_url=url)); db.commit()
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(other)).status_code == 404
    for user in (owner, admin):
        response = client.get(url, headers=headers(user))
        assert response.status_code == 200
        assert response.content == b'%PDF-1.4 synthetic fixture'
        assert 'no-store' in response.headers['cache-control']

def test_candidate_profiles_are_scoped(environment):
    client, db, owner, other, admin, candidate, _ = environment
    db.add(CandidateProfile(candidate_id=candidate.id, skills_graph='{"Python": 1}')); db.commit()
    url=f'/candidates/profile/{candidate.id}'
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(other)).status_code == 404
    assert client.get(url, headers=headers(owner)).json()['skills_graph'] == {'Python': 1}
    assert client.post('/candidates', headers=headers(owner), json={'id': 'arbitrary-other-user'}).json()['id'] == str(candidate.id)

def test_signup_atomic_and_admin_disabled(environment):
    client, db, *_ = environment
    payload = dict(email='new@example.com', password='long-password', full_name='New', role='super_admin', security_key='configured-admin-key')
    assert client.post('/api/v1/auth/signup', json=payload).status_code == 403
    payload['role']='candidate'
    response=client.post('/api/v1/auth/signup', json=payload)
    assert response.status_code == 200
    user=db.query(User).filter_by(email=payload['email']).one()
    assert db.query(Candidate).filter_by(user_id=user.id).count() == 1
    assert client.post('/api/v1/auth/signup', json=payload).status_code == 400

def test_login_rate_limit(environment):
    client, *_ = environment
    statuses=[client.post('/api/v1/auth/login', data={'username':'owner@example.com','password':'wrong'}).status_code for _ in range(6)]
    assert statuses == [401]*5 + [429]

def test_password_reset_consumes_code_and_revokes_refresh(environment):
    client, db, owner, *_ = environment
    code='123456'
    otp=OTP(email=owner.email, otp=hash_token(owner.email+':'+code+':'+settings.SECRET_KEY), expiry_time=datetime.utcnow()+timedelta(minutes=5), used=False)
    db.add(otp); db.add(UserRefreshToken(user_id=owner.id, token_hash='synthetic', expires_at=datetime.utcnow()+timedelta(days=1))); db.commit()
    payload={'email':owner.email,'code':code,'new_password':'new-long-password'}
    assert client.post('/api/v1/auth/reset-password',json=payload).status_code == 200
    db.refresh(owner)
    assert verify_password('new-long-password',owner.password_hash)
    assert db.query(UserRefreshToken).filter_by(user_id=owner.id).count() == 0
    assert client.post('/api/v1/auth/reset-password',json=payload).status_code == 400

def test_password_reset_is_rate_limited(environment):
    client, *_ = environment
    payload={'email':'owner@example.com','code':'000000','new_password':'new-password'}
    statuses=[client.post('/api/v1/auth/reset-password',json=payload).status_code for _ in range(6)]
    assert statuses == [400]*5+[429]

def test_otp_delivery_no_secret_in_logs(environment, monkeypatch, caplog):
    client, db, owner, *_ = environment
    from app.api.routers import auth
    delivered=[]
    monkeypatch.setattr(auth,'send_otp_html_email',lambda email,code,db: delivered.append(code))
    response=client.post('/api/v1/auth/forgot-password',json={'email':owner.email})
    assert response.status_code == 200
    row=db.query(OTP).filter_by(email=owner.email).one()
    assert row.otp != delivered[0]
    assert delivered[0] not in response.text and delivered[0] not in caplog.text

def test_sync_requires_secret(environment, monkeypatch):
    client, *_ = environment
    payload={'job_id':'j1','tenant_slug':'test','action':'create'}
    assert client.post('/api/v1/sync/jobs',json=payload).status_code == 503
    monkeypatch.setattr(settings,'HR_SYNC_SECRET','test-secret-that-is-long-enough-for-use')
    assert client.post('/api/v1/sync/jobs',json=payload).status_code == 401
    assert client.post('/api/v1/sync/jobs',json=payload,headers={'X-Sync-Secret':'bad'}).status_code == 401
    # Valid secret advances to payload validation before SQL.
    assert client.post('/api/v1/sync/jobs',json={**payload,'action':'typo'},headers={'X-Sync-Secret':settings.HR_SYNC_SECRET}).status_code == 422

def test_sync_stage_cross_user_read_rejected(environment):
    client, _, owner, other, *_ = environment
    assert client.get('/api/v1/sync/stages/'+owner.email).status_code == 401
    assert client.get('/api/v1/sync/stages/'+owner.email,headers=headers(other)).status_code == 403

def test_kernel_not_fake_success(environment):
    client, _, owner, *_ = environment
    body={'session_id':'s','candidate_id':'c','query':'find work'}
    assert client.post('/tush-ai/chat',json=body).status_code == 401
    assert client.post('/tush-ai/chat',json=body,headers=headers(owner)).status_code == 501
    # Verify production agent endpoints enforce authentication and reject unauthenticated requests
    assert client.post('/api/v1/agent/chat', json={'message':'find jobs for me'}).status_code == 401
    assert client.post('/api/v1/agent/confirm-action', json={'action_id':'act_1','action_type':'apply','payload':{},'confirmed':True}).status_code == 401


def test_websocket_owner_and_cleanup(environment):
    client, _, owner, *_ = environment
    from app.core.ws import manager
    token=headers(owner)['Authorization'].split(' ',1)[1]
    with client.websocket_connect('/ws/'+owner.email) as ws:
        ws.send_json({'token':token})
        # Health round trip gives server an opportunity to process authentication.
        import time
        for _ in range(100):
            if owner.email in manager.active_connections: break
            time.sleep(.005)
        assert owner.email in manager.active_connections
    for _ in range(100):
        if owner.email not in manager.active_connections: break
        time.sleep(.005)
    assert owner.email not in manager.active_connections

def test_websocket_cannot_join_admin_room(environment):
    client, _, owner, *_ = environment
    with client.websocket_connect('/ws/admin') as ws:
        ws.send_json({'token':headers(owner)['Authorization'].split(' ',1)[1]})
        with pytest.raises(WebSocketDisconnect): ws.receive_text()

def test_websocket_invalid_token(environment):
    client, *_ = environment
    with client.websocket_connect('/ws/owner@example.com') as ws:
        ws.send_json({'token':'invalid'})
        with pytest.raises(WebSocketDisconnect): ws.receive_text()

def test_unavailable_ai_does_not_award_grade():
    from app.api.routers.learning import evaluate_written_answers_ai, evaluate_interview_transcript_ai
    for function in (evaluate_written_answers_ai,evaluate_interview_transcript_ai):
        with pytest.raises(HTTPException) as exc:
            function('["Explain SQL"]', json.dumps({'0':'unrelated '*200}))
        assert exc.value.status_code == 503

def test_resume_requires_real_pdf(environment):
    client, _, owner, *_=environment
    response=client.post('/api/v1/candidates/resume', headers=headers(owner), files={'file':('fake.pdf',b'not PDF','application/pdf')})
    assert response.status_code == 400

def test_resume_rejects_oversized_upload(environment):
    client, _, owner, *_=environment
    response=client.post('/api/v1/candidates/resume', headers=headers(owner), files={'file':('big.pdf',b'%PDF-'+b'x'*(5*1024*1024),'application/pdf')})
    assert response.status_code == 400

def test_offline_resume_does_not_invent_qualifications():
    import fitz
    from app.services.orchestrator import fallback_pymupdf_pipeline
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((50,50),'Synthetic Candidate\nowner@example.com\nPython SQL')
        result = fallback_pymupdf_pipeline(document.tobytes())
    edu = json.loads(result['education']) if isinstance(result['education'], str) else result['education']
    exp = json.loads(result['experience']) if isinstance(result['experience'], str) else result['experience']
    assert edu == []
    assert exp == []
    opps = result.get('parsed_json', {}).get('opportunities') or result.get('opportunities') or {}
    assert isinstance(opps, dict)
    assert result['analysis_status'] in ('partial', 'completed')
    skill_names = [s['name'] if isinstance(s, dict) else s for s in result.get('skills', [])]
    assert 'Python' in skill_names

def test_job_verification_never_fetches_attacker_url(monkeypatch):
    from app.tools.verification import VerificationTool, VerificationArgs
    import httpx
    def fail(*a,**kw): raise AssertionError('Network call not allowed')
    monkeypatch.setattr(httpx, 'AsyncClient', fail)
    result=asyncio.run(VerificationTool()._run(None,1,VerificationArgs(jobs=[{'apply_url':'http://169.254.169.254/metadata'}])))
    assert result[0]['verification_status'] == 'unverified'

def test_lexical_fallback_preserves_token_overlap():
    from app.services.embedding_service import embedding_service, cosine_similarity
    a=embedding_service._generate_fallback_embedding('python sql developer')
    b=embedding_service._generate_fallback_embedding('python sql')
    c=embedding_service._generate_fallback_embedding('botany irrigation')
    assert cosine_similarity(a,b) > cosine_similarity(a,c)

def test_candidate_progress_websocket_room(environment):
    client, _, owner, _, _, candidate, _ = environment
    from app.core.ws import manager
    room=f'candidate_{candidate.id}'
    with client.websocket_connect('/ws/'+room) as ws:
        ws.send_json({'token':headers(owner)['Authorization'].split(' ',1)[1]})
        import time
        for _ in range(100):
            if room in manager.active_connections:break
            time.sleep(.005)
        assert room in manager.active_connections
    for _ in range(100):
        if room not in manager.active_connections:break
        time.sleep(.005)
    assert room not in manager.active_connections
