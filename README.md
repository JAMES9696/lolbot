# Project Chimera - LoL Discord Bot

An AI-powered League of Legends Discord bot that provides intelligent match analysis and personalized insights using Riot Games API and LLM integration.

## 🚀 P1 Phase Features

- ✅ Discord bot initialization with discord.py
- ✅ `/bind` slash command for account linking interface
- ✅ Hexagonal architecture structure
- ✅ Type-safe data contracts with Pydantic V2
- ✅ Environment-based configuration
- ✅ Health check and logging system

## 📋 Prerequisites

- Python 3.11+
- Discord Bot Token
- Redis (for future task queue integration)
- PostgreSQL (for future database integration)

## 🛠️ Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd lolbot/.conductor/jackson
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and add your Discord bot token:

```env
DISCORD_BOT_TOKEN=your_actual_bot_token_here
DISCORD_GUILD_ID=your_test_server_id  # Optional, for development
```

### 5. Set Up Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section
4. Copy the bot token to your `.env` file
5. Enable necessary intents:
   - Server Members Intent
   - Message Content Intent (for future features)

### 6. Invite Bot to Server

Generate an invite link with these permissions:
- `bot` and `applications.commands` scopes
- Permissions: Send Messages, Embed Links, Use Slash Commands

### 7. Run the Bot

```bash
python main.py
```

## 🏗️ Project Structure

```
.
├── src/
│   ├── core/           # Domain logic (independent of external systems)
│   ├── adapters/       # External system integrations
│   │   └── discord_adapter.py  # Discord bot implementation
│   ├── contracts/      # Pydantic data models
│   │   ├── user_binding.py     # Riot-Discord binding models
│   │   └── discord_interactions.py  # Discord command models
│   └── config.py       # Environment configuration
├── main.py            # Entry point
├── requirements.txt   # Python dependencies
└── .env.example      # Environment template
```

## 📝 Available Commands

### `/bind [region] [force_rebind]`
Link your Discord account with your League of Legends account.
- `region`: Your LoL server region (default: NA)
- `force_rebind`: Force new binding even if already linked

### `/unbind`
Unlink your Discord account from your League of Legends account.

### `/profile`
View your linked League of Legends profile information.

## 🔄 Development Workflow

### Hot Reload (Vibe Coding)

The bot supports hot reload for rapid development. Install watchdog and use:

```bash
watchmedo auto-restart -d src -p "*.py" -- python main.py
```

### Type Checking

```bash
mypy src/
```

### Code Formatting

```bash
black src/ main.py
ruff check src/ main.py
```

### Testing

```bash
pytest tests/ -v --asyncio-mode=auto
```

## 📊 Architecture Principles

This project follows **Hexagonal Architecture** (Ports & Adapters):

- **Core (`src/core/`)**: Pure business logic, no external dependencies
- **Adapters (`src/adapters/`)**: External system integrations (Discord, Riot API, Database)
- **Contracts (`src/contracts/`)**: Shared data models using Pydantic V2

Key constraints:
- All data models use Pydantic V2 with strict type checking
- Async/await throughout for non-blocking operations
- Configuration via environment variables only (no hardcoding)
- Structured logging with correlation IDs

## 🚧 P2+ Roadmap

- [ ] Riot API integration with Cassiopeia
- [ ] PostgreSQL database for user bindings
- [ ] Redis task queue for async processing
- [ ] RSO OAuth flow for account verification
- [ ] `/讲道理` command for AI-powered match analysis
- [ ] LLM integration (Gemini) for insights
- [ ] TTS integration (豆包) for voice responses

## 🤝 Contributing

This is CLI 1 (The Frontend) of the Project Chimera multi-CLI architecture:

- **CLI 1 (Frontend)**: Discord interactions, immediate responses
- **CLI 2 (Backend)**: Async task processing, API calls
- **CLI 3 (Observer)**: System monitoring, health checks
- **CLI 4 (Lab)**: Data exploration, algorithm testing

When contributing:
1. Follow hexagonal architecture patterns
2. Use type hints and Pydantic models
3. Write tests for new features
4. Keep response times under 3 seconds

## 📜 License

[Your License Here]

## 🆘 Support

For issues or questions, please open an issue on GitHub.