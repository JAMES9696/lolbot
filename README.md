# Project Chimera - LoL Discord Bot Data Contracts

## 🎯 Project Overview

Project Chimera is an AI-powered League of Legends Discord bot that provides deep match analysis using the Riot API Match-V5 Timeline data. As CLI 4 (The Lab), I've established the comprehensive data contracts that form the foundation of our entire system.

## 📊 Core Data Contracts

All data models are built using **Pydantic V2** with strict type checking and MyPy validation. The contracts are located in `src/contracts/` and serve as the authoritative source of truth for the entire project.

### Contract Modules

- **`common.py`** - Base models, enums, and shared types
- **`events.py`** - Timeline event models (20+ event types)
- **`timeline.py`** - Match timeline and frame data structures
- **`match.py`** - Match information and participant data
- **`summoner.py`** - Summoner profiles and account data

### Key Features

✅ **100% Type Safe** - All models pass MyPy strict mode
✅ **Pydantic V2** - Modern validation with computed fields
✅ **No Optional[]** - Uses `Type | None` syntax throughout
✅ **Frozen Models** - Immutable data structures where appropriate
✅ **Comprehensive Coverage** - All Match-V5 Timeline fields modeled

## 🚀 Quick Start

### Installation

```bash
# Install dependencies with Poetry
poetry install

# Or with pip
pip install -r requirements.txt
```

### Environment Setup

Copy `.env.example` to `.env` and add your credentials:

```bash
cp .env.example .env
```

### Type Checking

```bash
# Run MyPy type checking
python -m mypy src/contracts --config-file mypy.ini
```

## 📈 Data Model Architecture

### Timeline Structure

```python
MatchTimeline
├── TimelineMetadata
│   ├── match_id
│   ├── data_version
│   └── participants (PUUIDs)
└── TimelineInfo
    ├── frames (every 60 seconds)
    │   ├── participant_frames
    │   │   ├── champion_stats
    │   │   ├── damage_stats
    │   │   └── position
    │   └── events
    ├── game_id
    └── participants (ID to PUUID mapping)
```

### Event Types

Our contracts support all 20+ event types from the Riot API:

- **Combat Events**: CHAMPION_KILL, CHAMPION_SPECIAL_KILL
- **Objective Events**: ELITE_MONSTER_KILL, BUILDING_KILL, TURRET_PLATE_DESTROYED
- **Item Events**: ITEM_PURCHASED, ITEM_SOLD, ITEM_DESTROYED, ITEM_UNDO
- **Vision Events**: WARD_PLACED, WARD_KILL
- **Game Flow Events**: GAME_END, PAUSE_START, PAUSE_END
- **Special Events**: DRAGON_SOUL_GIVEN, CHAMPION_TRANSFORM, OBJECTIVE_BOUNTY

## 🔬 V1 Scoring Algorithm Design

Based on our Timeline analysis, the scoring algorithm evaluates:

### Performance Metrics (Weights)

1. **Combat Efficiency (30%)**
   - KDA ratio and kill participation
   - Damage share vs gold share
   - Death timing impact

2. **Economic Management (25%)**
   - Gold efficiency curve
   - CS/min relative to role
   - Item spike timing

3. **Objective Control (25%)**
   - Dragon/Baron participation
   - Tower damage contribution
   - Objective setup (vision before objectives)

4. **Vision & Map Control (10%)**
   - Wards placed per minute
   - Control ward uptime
   - Ward clearing efficiency

5. **Team Contribution (10%)**
   - Assist ratio
   - Teamfight presence
   - Damage mitigation for team

## 📝 API Exploration

The `notebooks/riot_api_exploration.ipynb` contains:
- Detailed Match-V5 Timeline structure analysis
- Critical event identification for scoring
- Frame-based performance metric extraction
- LLM prompt engineering considerations

## 🤝 Integration Points

### For CLI 2 (Backend)
The data contracts in `src/contracts/` are your authoritative models. Use them directly:

```python
from src.contracts import MatchTimeline, ChampionKillEvent

# Parse API response
timeline = MatchTimeline(**riot_api_response)

# Type-safe access
participant_id = timeline.get_participant_by_puuid(puuid)
kill_participation = timeline.get_kill_participation(participant_id)
```

### For CLI 1 (Frontend)
Import participant and match models for Discord display:

```python
from src.contracts import Participant, MatchInfo

# Display player stats with full type safety
def format_player_stats(participant: Participant) -> str:
    return f"{participant.champion_name}: {participant.kda:.2f} KDA"
```

## 🔒 Type Safety Guarantees

All models enforce:
- Strict field validation (no extra fields allowed)
- Range constraints (e.g., participant_id: 1-10)
- Required vs optional fields with `| None` syntax
- Immutable structures where appropriate (frozen=True)
- Computed properties with @computed_field

## 📚 Next Steps

### P2 Phase
- Implement Riot API adapters using these contracts
- Set up PostgreSQL models based on contract schemas
- Create serialization/deserialization utilities

### P3 Phase
- Implement V1 scoring algorithm using Timeline data
- Create LLM prompt templates with structured data
- Design aggregation functions for match analysis

### P4 Phase
- Optimize for TTS emotion detection
- Add community features data structures
- Implement caching strategies

### P5 Phase (Voice & AI Solidification)
- TTS voice synthesis adapter with timeouts and graceful degradation
- Webhook UX enhanced with optional "点击收听 AI 语音" link
- Emotion mapping finalized (score → emotion) for voice modulation
- System prompts versioned and configurable (see `src/prompts/system_prompts.py`)
- Deployment and setup: `docs/volcengine_tts_setup.md`

Compliance Note (Riot):
- Do not imply Riot endorsement; avoid competitive advantage claims
- Respect Discord 2000-char limit; no toxic or disallowed content
- If TTS is commercial/VIP, obtain Riot’s prior written approval

## 🛠️ Development Tools

- **Python 3.12+** - Required for modern type hints
- **Pydantic V2** - Data validation and serialization
- **MyPy** - Static type checking
- **Jupyter** - Data exploration and algorithm prototyping
- **Poetry** - Dependency management

## 📖 Documentation

All models are self-documenting through:
- Type annotations
- Field descriptions
- Docstrings
- Computed properties
- Validation constraints

## ✅ Definition of Done

- [x] Complete Pydantic V2 data models for all Timeline structures
- [x] 100% MyPy strict mode compliance
- [x] Comprehensive event type coverage
- [x] Jupyter notebook with API exploration
- [x] Integration examples and documentation
- [x] Type-safe helper methods (get_participant_by_puuid, etc.)

---

*Data contracts established by CLI 4 (The Lab) - The authoritative source of truth for Project Chimera*
