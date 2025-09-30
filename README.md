# InstaChatico

An intelligent Instagram webhook handler that processes comments and messages using AI-powered responses.

## 🏗️ Project Structure

```
/var/www/instachatico/app/
├── src/                          # Application source code
│   ├── main.py                   # FastAPI application entry point
│   ├── celery_worker.py         # Celery worker entry point
│   ├── api_v1/                  # API v1 routes
│   │   ├── comment_webhooks/    # Instagram webhook handlers
│   │   ├── docs/                # API documentation endpoints
│   │   └── telegram/            # Telegram integration
│   ├── core/                    # Core business logic
│   │   ├── agents/              # AI agents and instructions
│   │   ├── celery_app.py       # Celery application configuration
│   │   ├── config.py           # Application configuration
│   │   ├── logging_config.py   # Logging setup
│   │   ├── models/             # SQLAlchemy models
│   │   ├── services/           # Business logic services
│   │   ├── tasks/              # Celery tasks
│   │   └── utils/              # Utility functions
│   └── conversations/           # Conversation data storage
│
├── database/                    # Database-related files
│   ├── migrations/             # Alembic migrations
│   │   ├── versions/           # Migration scripts
│   │   ├── env.py             # Alembic environment
│   │   └── script.py.mako     # Migration template
│   ├── alembic.ini            # Alembic configuration
│   └── init.sql               # PostgreSQL initialization script
│
├── scripts/                     # Utility scripts
│   └── signature_calculator.py  # Instagram signature calculation helper
│
├── docker/                      # Docker and infrastructure
│   ├── docker-compose.yml      # Docker Compose configuration
│   ├── Dockerfile              # Container build instructions
│   └── config/                 # Service configurations
│       ├── redis/              # Redis configuration
│       │   ├── redis.conf      # Redis settings
│       │   └── entrypoint.sh   # Redis startup script
│       └── dozzle/             # Log viewer configuration
│           └── users.yml       # Dozzle user authentication
│
├── .gitignore                   # Git ignore rules
├── pyproject.toml              # Poetry dependencies and project metadata
├── poetry.lock                 # Locked dependency versions
└── README.md                   # This file
```

## 🚀 Getting Started

### Prerequisites

- Docker and Docker Compose
- Poetry (for local development)
- Python 3.11+

### Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Application
PORT=4291
HOST=0.0.0.0

# Database
DATABASE_URL=postgresql+asyncpg://lun1z:lun1z@postgres:5432/instagram_db

# Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Instagram
INSTA_TOKEN=your_instagram_token
INSTAGRAM_API_VERSION=v23.0
APP_SECRET=your_app_secret

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Telegram (for notifications)
TG_TOKEN=your_telegram_bot_token
TG_CHAT_ID=your_chat_id
TG_CHAT_ALERTS_THREAD_ID=thread_id_for_alerts
TG_CHAT_LOGS_THREAD_ID=thread_id_for_logs

# Documentation
DOCS_USERNAME=admin
DOCS_PASSWORD=secure_password

# Logging
LOGS_LEVEL=INFO
LOGS_LEVEL_POSTGRES=INFO
LOGS_LEVEL_CELERY=INFO
LOGS_LEVEL_REDIS=WARNING

# Development
DEVELOPMENT_MODE=false
```

### Running with Docker

1. **Navigate to the docker directory:**
   ```bash
   cd /var/www/instachatico/app/docker
   ```

2. **Start all services:**
   ```bash
   docker-compose up -d
   ```

3. **View logs:**
   ```bash
   docker-compose logs -f
   ```
   
   Or access Dozzle at `http://localhost:57928` for a web-based log viewer.

4. **Stop services:**
   ```bash
   docker-compose down
   ```

### Running Locally (Development)

1. **Install dependencies:**
   ```bash
   poetry install
   ```

2. **Activate virtual environment:**
   ```bash
   poetry shell
   ```

3. **Run database migrations:**
   ```bash
   alembic -c database/alembic.ini upgrade head
   ```

4. **Start the API server:**
   ```bash
   cd src
   uvicorn main:app --host 0.0.0.0 --port 4291 --reload
   ```

5. **Start Celery worker (in another terminal):**
   ```bash
   cd src
   celery -A celery_worker worker --loglevel=INFO --concurrency=4 -Q llm_queue,instagram_queue
   ```

6. **Start Celery beat (in another terminal):**
   ```bash
   cd src
   celery -A celery_worker beat --loglevel=INFO
   ```

## 🏛️ Architecture

### Services

- **API (FastAPI)**: Main web server handling Instagram webhooks
- **Celery Worker**: Async task processor for AI operations
- **Celery Beat**: Scheduled task manager
- **PostgreSQL**: Primary database
- **Redis**: Message broker and cache
- **Dozzle**: Docker log viewer

### Key Components

1. **Webhook Handler** (`src/api_v1/comment_webhooks/`):
   - Receives Instagram webhook events
   - Validates X-Hub-Signature-256 signatures
   - Queues events for processing

2. **AI Agents** (`src/core/agents/`):
   - Classify incoming messages
   - Generate contextual responses
   - Maintain conversation history

3. **Celery Tasks** (`src/core/tasks/`):
   - `classification_tasks`: Message classification
   - `answer_tasks`: Response generation
   - `instagram_reply_tasks`: Instagram API interactions
   - `telegram_tasks`: Notification sending

4. **Database Models** (`src/core/models/`):
   - User profiles
   - Conversation history
   - Message tracking

## 🔧 Development

### Database Migrations

Create a new migration:
```bash
cd /var/www/instachatico/app
alembic -c database/alembic.ini revision --autogenerate -m "Description"
```

Apply migrations:
```bash
alembic -c database/alembic.ini upgrade head
```

Rollback migration:
```bash
alembic -c database/alembic.ini downgrade -1
```

### Testing Webhooks

Use the signature calculator to generate valid webhook signatures:

```bash
cd /var/www/instachatico/app
python scripts/signature_calculator.py
```

### Code Formatting

Format code with Black:
```bash
poetry run black src/
```

## 📊 Monitoring

- **Application Logs**: Access via Dozzle at `http://localhost:57928`
- **Database**: PostgreSQL on port `59731`
- **Redis**: Redis on port `6379`
- **API**: FastAPI on port `4291`

## 🔒 Security Notes

1. Never commit `.env` files or secrets
2. The signature calculator script contains sensitive data - keep it secure
3. Dozzle users.yml contains hashed passwords - rotate regularly
4. Always validate Instagram webhook signatures in production
5. Use `DEVELOPMENT_MODE=false` in production

## 📝 API Documentation

When the application is running, API documentation is available at:
- **Swagger UI**: `http://localhost:4291/docs` (requires authentication)
- **ReDoc**: `http://localhost:4291/redoc` (requires authentication)

Authentication credentials are set via `DOCS_USERNAME` and `DOCS_PASSWORD` environment variables.

## 🐛 Troubleshooting

### Common Issues

1. **Celery worker not finding tasks**:
   - Ensure you're running from the `src/` directory
   - Check that all task modules are imported in `celery_worker.py`

2. **Database connection errors**:
   - Verify `DATABASE_URL` in `.env`
   - Check PostgreSQL is running: `docker-compose ps`

3. **Webhook signature validation failing**:
   - Verify `APP_SECRET` matches Instagram app settings
   - Check signature calculation script matches middleware

4. **Import errors**:
   - Verify you're in the correct directory
   - Check Python path includes `/app/src`

## 📄 License

Private project - All rights reserved

## 👤 Author

Mikhail Denisov (denisovmvtmb@yandex.ru)
