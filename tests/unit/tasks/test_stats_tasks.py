import pytest

from core.tasks.stats_tasks import record_follower_snapshot_task_async
from core.use_cases.record_follower_snapshot import FollowersSnapshotError


class DummySession:
    pass


class DummySessionContext:
    def __init__(self):
        self.session = DummySession()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class StubUseCase:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = 0

    async def execute(self):
        self.calls += 1
        if self.should_fail:
            raise FollowersSnapshotError("boom")
        return {"snapshot_date": "2025-11-17", "followers_count": 200}


class StubOAuthService:
    def __init__(self, tokens):
        self.tokens = tokens
        self.calls = 0

    async def get_tokens(self, *_args, **_kwargs):
        self.calls += 1
        return self.tokens


class StubContainer:
    def __init__(self, use_case, tokens):
        self.use_case = use_case
        self.oauth_service = StubOAuthService(tokens)
        self.sessions = []
        self.oauth_sessions = []

    def record_follower_snapshot_use_case(self, session):
        self.sessions.append(session)
        return self.use_case

    def oauth_token_service(self, *, session):
        self.oauth_sessions.append(session)
        return self.oauth_service


@pytest.mark.unit
class TestRecordFollowerSnapshotTask:
    @pytest.mark.asyncio
    async def test_task_success(self, monkeypatch):
        use_case = StubUseCase()
        container = StubContainer(use_case, tokens={"access_token": "token"})

        monkeypatch.setattr("core.tasks.stats_tasks.get_container", lambda: container)
        monkeypatch.setattr("core.tasks.stats_tasks.get_db_session", lambda: DummySessionContext())

        result = await record_follower_snapshot_task_async()

        assert result["status"] == "ok"
        assert result["followers_count"] == 200
        assert use_case.calls == 1
        assert len(container.sessions) == 1

    @pytest.mark.asyncio
    async def test_task_failure(self, monkeypatch):
        use_case = StubUseCase(should_fail=True)
        container = StubContainer(use_case, tokens={"access_token": "token"})

        monkeypatch.setattr("core.tasks.stats_tasks.get_container", lambda: container)
        monkeypatch.setattr("core.tasks.stats_tasks.get_db_session", lambda: DummySessionContext())

        result = await record_follower_snapshot_task_async()

        assert result["status"] == "error"
        assert "reason" in result
        assert use_case.calls == 1

    @pytest.mark.asyncio
    async def test_task_skips_when_missing_tokens(self, monkeypatch):
        use_case = StubUseCase()
        container = StubContainer(use_case, tokens=None)

        monkeypatch.setattr("core.tasks.stats_tasks.get_container", lambda: container)
        monkeypatch.setattr("core.tasks.stats_tasks.get_db_session", lambda: DummySessionContext())

        result = await record_follower_snapshot_task_async()

        assert result == {"status": "skipped", "reason": "missing_auth"}
        assert use_case.calls == 0
