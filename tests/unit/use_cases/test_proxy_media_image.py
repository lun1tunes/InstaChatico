import asyncio
import pytest

from core.use_cases.proxy_media_image import (
    ProxyMediaImageUseCase,
    MediaImageProxyError,
)


class FakeMedia:
    def __init__(self, media_url=None, children_media_urls=None):
        self.media_url = media_url
        self.children_media_urls = children_media_urls


class FakeMediaRepository:
    def __init__(self, media_by_id):
        self._media_by_id = media_by_id
        self.requested_ids = []

    async def get_by_id(self, media_id):
        self.requested_ids.append(media_id)
        return self._media_by_id.get(media_id)


class FakeFetchResult:
    def __init__(self, status=200, content_type="image/jpeg", cache_control=None, chunks=None):
        self.status = status
        self.content_type = content_type
        self.cache_control = cache_control
        self._chunks = chunks or [b"data"]
        self.closed = False

    def iter_bytes(self):
        async def generator():
            for chunk in self._chunks:
                yield chunk
        return generator()

    async def close(self):
        self.closed = True


class FakeMediaProxyService:
    def __init__(self, fetch_result=None, error=None):
        self._fetch_result = fetch_result
        self._error = error
        self.requested_urls = []

    async def fetch_image(self, url: str):
        self.requested_urls.append(url)
        if self._error:
            raise self._error
        return self._fetch_result


def repo_factory_builder(repository):
    def factory(*, session):
        return repository
    return factory


@pytest.mark.asyncio
async def test_proxy_media_image_success():
    media = FakeMedia(media_url="https://cdninstagram.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    fetch_result = FakeFetchResult(chunks=[b"a", b"b"], cache_control="public")
    proxy_service = FakeMediaProxyService(fetch_result=fetch_result)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    result = await use_case.execute("media1")

    collected = []
    async for chunk in result.content_stream:
        collected.append(chunk)

    assert collected == [b"a", b"b"]
    assert result.content_type == "image/jpeg"
    assert result.headers["Cache-Control"] == "public"
    assert proxy_service.requested_urls == ["https://cdninstagram.com/image.jpg"]


@pytest.mark.asyncio
async def test_proxy_media_image_child_index():
    media = FakeMedia(children_media_urls=["https://cdninstagram.com/child.jpg"])
    repository = FakeMediaRepository(media_by_id={"media1": media})
    fetch_result = FakeFetchResult()
    proxy_service = FakeMediaProxyService(fetch_result=fetch_result)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    await use_case.execute("media1", child_index=0)
    assert proxy_service.requested_urls == ["https://cdninstagram.com/child.jpg"]


@pytest.mark.asyncio
async def test_proxy_media_image_media_not_found():
    repository = FakeMediaRepository(media_by_id={})
    proxy_service = FakeMediaProxyService(fetch_result=FakeFetchResult())

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("missing")

    assert exc.value.status_code == 404
    assert exc.value.code == 4040


@pytest.mark.asyncio
async def test_proxy_media_image_invalid_child_index():
    media = FakeMedia(children_media_urls=["https://cdninstagram.com/child.jpg"])
    repository = FakeMediaRepository(media_by_id={"media1": media})
    proxy_service = FakeMediaProxyService(fetch_result=FakeFetchResult())

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1", child_index=2)

    assert exc.value.code == 4043


@pytest.mark.asyncio
async def test_proxy_media_image_invalid_scheme():
    media = FakeMedia(media_url="ftp://cdninstagram.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    proxy_service = FakeMediaProxyService(fetch_result=FakeFetchResult())

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert exc.value.code == 4003


@pytest.mark.asyncio
async def test_proxy_media_image_host_not_allowed():
    media = FakeMedia(media_url="https://example.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    proxy_service = FakeMediaProxyService(fetch_result=FakeFetchResult())

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert exc.value.code == 4004


@pytest.mark.asyncio
async def test_proxy_media_image_fetch_service_error():
    media = FakeMedia(media_url="https://cdninstagram.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    proxy_service = FakeMediaProxyService(error=RuntimeError("boom"))

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert exc.value.code == 5005


@pytest.mark.asyncio
async def test_proxy_media_image_non_success_status():
    media = FakeMedia(media_url="https://cdninstagram.com/image.jpg")
    repository = FakeMediaRepository(media_by_id={"media1": media})
    fetch_result = FakeFetchResult(status=404)
    proxy_service = FakeMediaProxyService(fetch_result=fetch_result)

    use_case = ProxyMediaImageUseCase(
        session=None,
        media_repository_factory=repo_factory_builder(repository),
        proxy_service=proxy_service,
        allowed_host_suffixes=["cdninstagram.com"],
    )

    with pytest.raises(MediaImageProxyError) as exc:
        await use_case.execute("media1")

    assert fetch_result.closed is True
    assert exc.value.code == 5003
