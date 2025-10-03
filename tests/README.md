# InstaChatico Test Suite

Comprehensive test suite for the InstaChatico Instagram webhook application.

## 📋 Test Coverage

### Unit Tests (`tests/unit/`)
- ✅ **Pydantic Schemas** - Validation, serialization, edge cases
- ✅ **Services** - Classification, Answer, Media, Media Analysis
- ✅ **Utilities** - Helper functions, task helpers
- ✅ **Models** - Database model validation

### Integration Tests (`tests/integration/`)
- ✅ **API Endpoints** - Webhook, test endpoints, error handling
- ✅ **Database Operations** - CRUD operations, relationships
- ✅ **Task Execution** - Celery task integration

## 🚀 Running Tests

### Install Test Dependencies

```bash
# Inside Docker container
docker exec -it instagram_api bash
cd /app
poetry install --with dev
```

### Run All Tests

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=src/core --cov-report=html
```

### Run Specific Test Categories

```bash
# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run tests by marker
pytest -m unit
pytest -m api
pytest -m service
pytest -m slow  # Slow-running tests
```

### Run Specific Test Files

```bash
# Test schemas only
pytest tests/unit/test_schemas.py

# Test services only
pytest tests/unit/test_services.py

# Test API endpoints only
pytest tests/integration/test_api_endpoints.py
```

### Run Specific Test Functions

```bash
# Run specific test class
pytest tests/unit/test_schemas.py::TestClassificationRequest

# Run specific test method
pytest tests/unit/test_schemas.py::TestClassificationRequest::test_valid_request
```

## 📊 Coverage Report

After running tests with coverage:

```bash
# View HTML coverage report
open htmlcov/index.html

# View terminal coverage report
pytest --cov=src/core --cov-report=term-missing
```

Current coverage target: **≥70%**

## 🔧 Test Configuration

### pytest.ini
- Async mode: auto
- Coverage: src/core
- Markers: unit, integration, slow, api, service, task

### conftest.py Fixtures

**Database Fixtures:**
- `test_db_engine` - In-memory SQLite engine
- `test_db_session` - Test database session
- `sample_media` - Sample media object
- `sample_comment` - Sample Instagram comment

**API Fixtures:**
- `api_client` - FastAPI TestClient

**Mock Data:**
- `sample_media_data` - Media API response
- `sample_comment_data` - Comment data
- `sample_webhook_payload` - Instagram webhook payload

**Mock Services:**
- `mock_openai_response` - Mocked OpenAI API
- `mock_instagram_api` - Mocked Instagram API
- `mock_celery_task` - Mocked Celery task

## 🎯 Writing New Tests

### Example Unit Test

```python
import pytest
from core.schemas.classification import ClassificationResponse

def test_classification_response():
    """Test creating a classification response."""
    response = ClassificationResponse(
        status="success",
        comment_id="test_123",
        classification="question / inquiry",
        confidence=95
    )

    assert response.status == "success"
    assert response.confidence == 95
```

### Example Integration Test

```python
import pytest

@pytest.mark.asyncio
async def test_media_service(test_db_session, sample_media):
    """Test media service database integration."""
    from core.services.media_service import MediaService

    service = MediaService()
    media = await service.get_or_create_media(
        sample_media.id,
        test_db_session
    )

    assert media.id == sample_media.id
```

### Example API Test

```python
def test_webhook_endpoint(api_client):
    """Test webhook POST endpoint."""
    response = api_client.post(
        "/api/v1/webhook/",
        json={"test": "data"}
    )

    assert response.status_code in [200, 422]
```

## 🐛 Debugging Tests

### Run with Debug Output

```bash
# Show print statements
pytest -s

# Show local variables on failure
pytest -l

# Drop into debugger on failure
pytest --pdb
```

### Run Failed Tests Only

```bash
# Re-run last failed tests
pytest --lf

# Re-run failed, then all
pytest --ff
```

## 📝 Test Markers

Use markers to organize tests:

```python
@pytest.mark.unit
def test_something():
    pass

@pytest.mark.slow
def test_long_running():
    pass

@pytest.mark.api
def test_endpoint():
    pass
```

## ⚡ CI/CD Integration

Add to your CI pipeline:

```yaml
test:
  script:
    - poetry install --with dev
    - pytest --cov=src/core --cov-report=xml
    - coverage report --fail-under=70
```

## 🔍 Test Best Practices

1. **Isolate tests** - Each test should be independent
2. **Use fixtures** - Reuse common setup/teardown
3. **Mock external services** - Don't call real APIs in tests
4. **Test edge cases** - Empty inputs, boundary values, errors
5. **Meaningful names** - Test names should describe what they test
6. **One assertion concept** - Test one thing per test function
7. **Arrange-Act-Assert** - Follow AAA pattern

## 📚 Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)
