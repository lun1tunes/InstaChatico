# Unit Tests

Fast, isolated tests with mocked dependencies.

## Structure:

```
unit/
├── repositories/          # Repository layer tests
│   └── test_repositories.py
├── services/              # Service layer tests (one file per service)
│   ├── test_classification_service.py
│   ├── test_answer_service.py
│   ├── test_instagram_service.py
│   └── ... (add more as needed)
├── use_cases/             # Use case tests (TODO)
├── agents/                # Agent tool tests (TODO)
└── schemas/               # Schema validation tests (TODO)
```

## Running:

```bash
# All unit tests
pytest tests/unit/ -m unit

# Specific layer
pytest tests/unit/repositories/ -v
pytest tests/unit/services/ -v
```
