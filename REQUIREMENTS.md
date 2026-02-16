# REQUIREMENTS.md — AI Dev Team

## Project Overview

Build a multi-agent AI development team consisting of a **Manager**, **Business Analyst (BA)**, **Developer (Dev)**, and **Tester**, powered by LangChain and OpenRouter API. The application is exposed as FastAPI REST endpoints for future frontend integration.

---

## Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM Provider | OpenRouter API | Single API, access to multiple models |
| Agent Framework | LangChain + LangGraph | Mature, well-documented, supports multi-agent |
| API Framework | FastAPI | Async, auto OpenAPI docs, modern |
| Memory | SQLite with SQLModel | Persistent conversation history from the start |
| Agent Collaboration | Manager-orchestrated | Manager routes tasks to specialist agents |
| Code Execution | None (write-only) | Agents generate code, don't execute |
| File Access | Yes (designated workspace) | Agents read/write project files |
| Models | Single model → Per-agent config | Start uniform, optimize later |

---

## Step-by-Step Implementation Plan

---

### Step 1: Project Setup & Simple Chatbot

**Goal:** Get a basic chatbot working with OpenRouter via LangChain.

**What you'll learn:** LangChain basics, ChatModel setup, OpenRouter integration, FastAPI basics.

**Tasks:**

1. Initialize Python project with `pyproject.toml` or `requirements.txt`
2. Set up project structure:
   ```
   dev-team/
   ├── app/
   │   ├── __init__.py
   │   ├── main.py              # FastAPI app entry
   │   ├── config.py            # Settings / env vars
   │   └── routers/
   │       └── chat.py          # Chat endpoint
   ├── .env                     # API keys
   ├── .env.example
   ├── requirements.txt
   └── README.md
   ```
3. Install dependencies: `langchain`, `langchain-openai`, `fastapi`, `uvicorn`, `python-dotenv`
4. Configure OpenRouter as a ChatOpenAI provider (OpenRouter is OpenAI-compatible)
5. Create a simple `/chat` POST endpoint that takes a message and returns LLM response
6. Test with curl or Swagger UI

**API Endpoints:**

- `POST /api/v1/chat` — Send a message, get a response
- `GET /api/v1/health` — Health check

**Key Code Concepts:**

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="nvidia/nemotron-3-nano-30b-a3b:free",
    openai_api_key="your-openrouter-key",
    openai_api_base="https://openrouter.ai/api/v1",
)
```

**Acceptance Criteria:**

- [ ] Can send a message and receive an LLM response via API
- [ ] OpenRouter API key loaded from `.env`
- [ ] Swagger docs available at `/docs`

---

### Step 2: Add Conversation Memory

**Goal:** The chatbot remembers previous messages within a session, persisted to SQLite.

**What you'll learn:** LangChain memory with SQL persistence, conversation history, session management, SQLModel.

**Tasks:**

1. Add session/conversation ID support (UUID-based)
2. Set up SQLite database with SQLModel:
   - Create `app/db/` directory with `__init__.py`, `database.py`, and `models.py`
   - Define SQLModel table for sessions and messages
   - Configure database connection with async support (`aiosqlite`)
3. Implement SQLite-backed conversation store using LangChain's `SQLChatMessageHistory`
4. Use `ChatMessageHistory` and `RunnableWithMessageHistory` from LangChain with SQL backend
5. Update `/chat` endpoint to accept an optional `session_id`
6. Add endpoint to list/clear sessions
7. Add system prompt support

**Project Structure Update:**

```
app/
├── db/
│   ├── __init__.py
│   ├── database.py         # SQLite connection and session management
│   └── models.py           # SQLModel database models
```

**API Endpoints (updated):**

- `POST /api/v1/chat` — body: `{ "message": "...", "session_id": "optional-uuid" }`
- `GET /api/v1/sessions` — List active sessions
- `DELETE /api/v1/sessions/{session_id}` — Clear a session
- `GET /api/v1/sessions/{session_id}/history` — Get conversation history

**Key Implementation Details:**

```python
# Using LangChain's SQLChatMessageHistory for persistence
from langchain_community.chat_message_histories import SQLChatMessageHistory

history = SQLChatMessageHistory(
    session_id=session_id,
    connection_string="sqlite:///./chat_history.db"
)
```

**Acceptance Criteria:**

- [ ] Sending messages with the same `session_id` retains conversation context
- [ ] New session created automatically if no `session_id` provided
- [ ] Can retrieve full conversation history for a session
- [ ] Conversation history persists after server restart (SQLite)
- [ ] Sessions and messages are stored in relational database tables

---

### Step 3: Role-Based Agent Personas

**Goal:** Create specialized agent personas (BA, Dev, Tester, Manager) with distinct roles, system prompts, and responsibilities.

**What you'll learn:** System prompt design, structured outputs (JSON), agent specialization, role-based configuration.

**Tasks:**

This step consists of four sub-sections:
1. BA Agent Persona Integration
2. Dev Agent Persona Integration  
3. Tester Agent Persona Integration
4. Manager Agent Persona Integration

---

#### 3.1 BA Agent Persona Integration

**Goal:** Create a Business Analyst (BA) persona that reliably converts vague user requests into structured, testable requirements and user stories.

**What you'll learn:** system prompt design, structured outputs (JSON), clarifying-question loops, lightweight validation.

**Tasks (detailed):**
1. Persona config (example `agent_config.yaml` entry):

```yaml
ba:
  role: "Business Analyst"
  name: "BA"
  model: "nvidia/nemotron-3-nano-30b-a3b:free"
  temperature: 0.5
  system_prompt: |
    You are BA, a Business Analyst. Your job is to analyze user requests, produce clear user stories,
    acceptance criteria, and ask short clarifying questions when requirements are ambiguous. Always
    return structured JSON following the schema requested.
```

2. System prompt template (use for prompt engineering):

```
SYSTEM: You are BA. Input: free-text user request. Output: JSON with keys: title, description,
user_stories (array of {id,title,description,acceptance_criteria}), questions (array of clarifying Qs),
priority. If the request is ambiguous, ask up to 3 clarifying questions instead of producing stories.
```

3. Implement in `app/agents/ba.py`:
- Provide a function `run_ba_analysis(request_text) -> dict` that:
  - Validates request length and canonicalizes whitespace
  - Calls the LLM with system prompt + user text
  - Parses and validates the returned JSON (pydantic model)
  - If LLM returns questions (ambiguity), return them and set status `clarify`
  - Otherwise return structured requirements and user stories

4. Tools & permissions:
- BA gets read access to project docs and conversation history (to ground analysis)
- BA should not write source code files; can create requirement docs (`.md` or `.yaml`)

5. Request/response schema (Pydantic suggested):

```python
class BARequest(BaseModel):
    text: str
    project_id: Optional[str]

class UserStory(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: List[str]

class BAResponse(BaseModel):
    title: str
    description: str
    user_stories: List[UserStory]
    questions: List[str]
    priority: Optional[str]
```

6. Endpoint: `/api/v1/ba/analyze` accepts `BARequest`, returns `BAResponse`.

7. Unit tests and validation:
- Test that ambiguous input generates clarifying questions
- Test that concrete input produces at least one user story with acceptance criteria
- Test JSON parsing resilience and schema validation failures

---

#### 3.2 Dev Agent Persona Integration

**Goal:** Create a Developer (Dev) persona that turns verified requirements into well-structured code, with safe file-write behavior and quality checks.

**What you'll learn:** code generation patterns, tool binding for file operations, safety checks (linters/tests), multi-file planning.

**Tasks (detailed):
1. Persona config sample (`agent_config.yaml`):

```yaml
dev:
  role: "Developer"
  name: "Dev"
  model: "nvidia/nemotron-3-nano-30b-a3b:free"
  temperature: 0.2
  system_prompt: |
    You are Dev. Given verified requirements and user stories, produce a minimal, well-structured
    implementation. Prefer readability and tests. When writing code, return exact file paths and file
    contents in a structured JSON payload. Do not execute code.
```

2. Implement in `app/agents/developer.py`:
- Key function: `async def generate_implementation(task_description: str, user_stories: Optional[List[UserStory]] = None, context: Optional[List[str]] = None, project_id: Optional[str] = None, dry_run: bool = False, explain_changes: bool = True) -> ImplementationResult`
  - Plan: produce a file map (path -> content) before writing anything
  - Uses LangChain's `with_structured_output` for guaranteed valid JSON schema adherence
  - Run static checks (invoke a formatting/linting tool process on the generated code via a CI step — simulated in tests)
  - Return metadata: created_files, diffs, explanations for each file

3. File write safety and sandboxing:
- All writes go through `app/tools/file_tools.py::write_file(path, content, project_id)` which enforces sandboxing and normalization

4. Output format (example JSON):

```json
{
  "plan": [{"path":"app/routes/users.py","summary":"User routes"}],
  "files": [{"path":"app/routes/users.py","content":"..."}],
  "explanations": {"app/routes/users.py":"Why this structure"}
}
```

5. Endpoint: `/api/v1/dev/generate` — accepts task id or analyzed requirements; return plan and (optionally) write files.

6. Validation and tests:
- Lint generated code with a chosen linter (flake8/ruff) in CI or as a test step
- Unit tests that check the `files` JSON is well formed and paths are under workspace
- Integration test: run pytest in a sandboxed environment (optional)

7. Extra features:
- Support a `dry_run` mode where Dev returns the plan but does not write files
- Provide `explain_changes` option where Dev summarizes why files were added/modified

---

#### 3.3 Tester Agent Persona Integration

**Goal:** Create a Tester persona that inspects code artifacts, writes tests, and produces prioritized test plans and risk analyses.

**What you'll learn:** automated test generation, test prioritization, coverage reporting, mapping tests to artifacts.

**Tasks (detailed):
1. Persona config sample:

```yaml
tester:
  role: "Tester"
  name: "Tester"
  model: "nvidia/nemotron-3-nano-30b-a3b:free"
  temperature: 0.1
  system_prompt: |
    You are Tester. Given code artifacts, produce unit and integration test cases, a prioritized test
    plan, and a short risk assessment. Output tests in files and provide commands to run them.
```

2. Implement in `app/agents/tester.py`:
- Key function: `review_and_generate_tests(artifact_refs: List[ArtifactRef]) -> TestPlan`
  - Read the target source files via `read_file` tool
  - Identify public APIs, edge cases, and dependency points
  - Produce test files (pytest style) and a test matrix mapping tests -> source files
  - Provide a prioritized list and estimated effort for each test

3. Output example:

```json
{
  "tests": [{"path":"tests/test_users.py","content":"..."}],
  "matrix": [{"source":"app/routes/users.py","tests":["tests/test_users.py"]}],
  "priority": ["smoke","critical","others"],
  "coverage_commands": "pytest --maxfail=1 --disable-warnings -q"
}
```

4. Endpoint: `/api/v1/tester/review` accepts references to artifacts or project_id and returns a TestPlan and created test files.

5. Validation and CI:
- Run generated tests in a sandboxed environment (optional) and return results as `tool_result`
- Provide a coverage estimate or a guide to run coverage tools

---

#### 3.4 Manager Agent Persona Integration

**Goal:** Create a Manager that orchestrates BA, Dev, and Tester with clear task lifecycle management, retries, and aggregation of outputs.

**What you'll learn:** orchestration patterns, state management, conditional routing, merging agent outputs.

**Tasks (detailed):
1. Persona config sample:

```yaml
manager:
  role: "Manager"
  name: "Manager"
  model: "nvidia/nemotron-3-nano-30b-a3b:free"
  temperature: 0.3
  system_prompt: |
    You are Manager. Receive a user request, decide if BA/Dev/Tester are needed, create tasks with
    clear acceptance criteria, and coordinate agent calls. Keep task state and produce a final
    synthesized response that includes artifacts and next steps.
```

2. Implement manager logic in `app/agents/manager.py`:
- Main function: `route_request(user_request) -> TaskResult`
  - Step A: Triage (is this a small ask the Dev can implement directly, or does it need BA?)
  - Step B: Create Task(s) with unique IDs and status `pending`
  - Step C: Call BA if requirements unclear; wait for `clarify` or `done`
  - Step D: Call Dev with analyzed requirements or plan; validate plan
  - Step E: Send Dev artifacts to Tester for review
  - Step F: Aggregate outputs, update Task `completed` and store artifacts

3. State & persistence:
- Task model should be persisted (SQLite) with fields: id, status, assigned_agents, artifacts, agent_messages, timestamps
- Manager should write audit logs of every agent call including LLM prompts, responses, and retrieved context pointers

4. Tooling & retries:
- Manager uses retriever to fetch relevant project context before calling agents
- Implement retry/backoff for failing agent calls and a `max_retries` policy

5. Example orchestration pseudocode:

```python
def route_request(request):
    task = create_task(request)
    if needs_ba(request):
        ba_resp = BA.run(request)
        if ba_resp.questions:
            task.status = 'waiting_for_clarification'
            return ba_resp.questions
        requirements = ba_resp.user_stories
    else:
        requirements = synth_requirements(request)

    dev_plan = Dev.generate(requirements)
    write_files(dev_plan.files)
    test_plan = Tester.review_and_generate_tests(dev_plan.artifacts)
    task.complete(dev_plan, test_plan)
    return compile_final_response(task)
```

6. Endpoints: `/api/v1/manager/route` — accepts a user request, returns a `task_id` and immediate status; use `/api/v1/team/status/{task_id}` to poll for completion or stream events via SSE.

7. Acceptance criteria and observability:
- Manager must always return a task with traceable agent outputs
- All intermediate artifacts and agent messages stored and queryable via task endpoints
- Provide an event log for streaming clients (tool calls, tool results, tokens)

8. Tests and failure modes:
- Simulate failing Dev outputs and ensure Manager retries/is able to request fixes from Dev
- Ensure Manager safely aborts if required external resources (vector DB, DB) are unavailable and returns clear error messages


### Multi-Agent Orchestration with LangGraph

**Goal:** Implement the full LangGraph-based orchestration of the agent team.

**What you'll learn:** State machines, agent coordination, LangGraph fundamentals.

**Tasks:**
1. Install and configure LangGraph
2. Define `TeamState` structure for shared context
3. Build state graph where:
   - User request enters
   - Manager node analyzes request
   - Routes to appropriate specialist nodes (BA, Dev, Tester)
   - Agents operate using their specialized logic and tools
   - Manager node collects results and synthesizes final response
4. Implement conditional edges for routing decisions
5. Add status tracking across the workflow
6. Integrate with FastAPI endpoints for team interaction
7. Add input validation for multi-agent requests

**Project Structure Update:**
- Enhanced `app/agents/team.py` with LangGraph configuration
- New state definitions in `app/models/state.py`

**API Endpoints:**
- (Existing endpoints updated to use orchestrated flow)

**Acceptance Criteria:**
- [ ] Full end-to-end workflow from user request to synthesized response
- [ ] Each agent operates autonomously but coordinated by Manager
- [ ] State is maintained throughout the workflow
- [ ] All agent contributions are visible in final output

---

### Step 4: Add Tools — File System Operations

**Goal:** Give agents the ability to read and write files in a designated workspace directory.

**What you'll learn:** LangChain tools, tool binding, function calling, agent executor.

**Tasks:**

1. Create a workspace directory concept (`workspace/` folder for each project)
2. Implement LangChain tools:
   - `read_file(path)` — Read file contents from workspace
   - `write_file(path, content)` — Write/create a file in workspace
   - `list_files(directory)` — List files in workspace directory
   - `read_directory_structure()` — Get tree view of workspace
3. Add path validation/sandboxing (prevent reading/writing outside workspace)
4. Upgrade agents from simple chat to tool-using agents using LangChain's agent framework
5. Only give relevant tools to relevant agents (Dev gets write, Tester gets read, etc.)

**Tool assignment per role:**

| Tool | Manager | BA | Dev | Tester |
|---|---|---|---|---|
| read_file | Yes | Yes | Yes | Yes |
| write_file | No | Yes | Yes | Yes |
| list_files | Yes | Yes | Yes | Yes |
| read_directory_structure | Yes | Yes | Yes | Yes |

**Project Structure Update:**

```
app/
├── tools/
│   ├── __init__.py
│   └── file_tools.py       # File system tools
├── agents/
│   ├── base.py             # Now uses create_react_agent or similar
```

**API Endpoints (updated):**

- `POST /api/v1/projects` — Create a new project workspace
- `GET /api/v1/projects` — List projects
- `GET /api/v1/projects/{project_id}/files` — List files in project
- `GET /api/v1/projects/{project_id}/files/{path}` — Read a file

**Acceptance Criteria:**

- [ ] Dev agent can write code files when asked
- [ ] Tester agent can read code and write test files
- [ ] BA agent can write requirements/user story documents
- [ ] All file operations sandboxed to workspace directory
- [ ] File operations visible in API responses (tool call traces)

---

### Step 5: Streaming Responses

**Goal:** Stream agent responses token-by-token via Server-Sent Events (SSE).

**What you'll learn:** LangChain streaming, SSE with FastAPI, async generators.

**Tasks:**

1. Implement SSE streaming endpoint using `StreamingResponse`
2. Stream LLM token output in real-time
3. Stream tool call events (so frontend can show "Agent is reading file X...")
4. Add event types: `token`, `tool_call`, `tool_result`, `done`, `error`
5. Keep the non-streaming endpoint as fallback

**API Endpoints (updated):**

- `POST /api/v1/chat/stream` — SSE streaming chat endpoint

**Event format:**

```
event: token
data: {"content": "Here"}

event: tool_call
data: {"tool": "read_file", "args": {"path": "main.py"}}

event: tool_result
data: {"tool": "read_file", "result": "...file contents..."}

event: done
data: {"session_id": "...", "total_tokens": 150}
```

**Acceptance Criteria:**

- [ ] Responses stream in real-time
- [ ] Tool calls are streamed as distinct events
- [ ] Frontend can consume SSE events to show typing effect + tool usage

---

### Step 6: Multi-Agent System — Manager Orchestration with LangGraph

**Goal:** Implement the Manager agent that orchestrates BA, Dev, and Tester using LangGraph.

**What you'll learn:** LangGraph, multi-agent orchestration, state machines, agent delegation.

**Tasks:**

1. Install and configure LangGraph
2. Define the team state graph:
   ```
   User Request → Manager → [Routes to appropriate agent(s)]
                              ├── BA (if requirements/analysis needed)
                              ├── Dev (if coding needed)
                              └── Tester (if testing needed)
                          → Manager reviews → Response to User
   ```
3. Implement `TeamState` (shared state across agents):
   ```python
   class TeamState(TypedDict):
       messages: list          # Conversation history
       current_task: str       # Current task description
       assigned_to: str        # Which agent is working
       artifacts: dict         # Files created, docs written, etc.
       status: str             # planning, in_progress, review, done
   ```
4. Build the LangGraph state graph with conditional routing
5. Manager decides which agent to invoke based on the user's request
6. Each agent's output feeds back to Manager for review
7. Manager can iterate (e.g., send Dev's code to Tester for review)

**Project Structure Update:**

```
app/
├── agents/
│   ├── manager.py          # Manager orchestration logic
│   ├── ba.py               # BA agent
│   ├── developer.py        # Developer agent
│   ├── tester.py           # Tester agent
│   └── team.py             # LangGraph team graph definition
├── models/
│   └── state.py            # TeamState and related models
```

**API Endpoints (updated):**

- `POST /api/v1/team/chat` — Send a request to the full dev team
- `POST /api/v1/team/chat/stream` — Streaming version
- `GET /api/v1/team/status/{task_id}` — Check team task status

**Acceptance Criteria:**

- [ ] User sends a request like "Build a REST API for user management"
- [ ] Manager analyzes and routes to BA for requirements
- [ ] BA produces user stories, Manager sends to Dev
- [ ] Dev writes code, Manager sends to Tester
- [ ] Tester reviews code and writes test cases
- [ ] Manager compiles final response
- [ ] Each agent's contribution is visible in the response

---

### Step 7: Task Tracking & Workflow State

**Goal:** Track tasks, their status, and the workflow through the agent pipeline.

**What you'll learn:** State management, task lifecycle, async task processing.

**Tasks:**

1. Implement a Task model:
   ```python
   class Task:
       id: str
       title: str
       description: str
       status: str          # pending, in_progress, completed, failed
       assigned_to: str     # agent role
       created_at: datetime
       updated_at: datetime
       artifacts: list      # files produced
       agent_messages: list # conversation between agents
   ```
2. Tasks are created by the Manager when processing user requests
3. Track which agent is working on what
4. Store intermediate agent outputs (BA's requirements, Dev's code, Tester's review)
5. Expose task history and artifacts via API

**API Endpoints (updated):**

- `GET /api/v1/tasks` — List all tasks
- `GET /api/v1/tasks/{task_id}` — Get task details with full agent conversation
- `GET /api/v1/tasks/{task_id}/artifacts` — Get files/documents produced

**Acceptance Criteria:**

- [ ] Full audit trail of what each agent did
- [ ] Can replay the decision-making process
- [ ] Artifacts (code, docs, tests) linked to tasks

---

### Step 8: Add Persistence with SQLite

**Goal:** Persist conversations, tasks, and project data to SQLite.

**What you'll learn:** Database integration, SQLAlchemy/SQLModel, data persistence.

**Tasks:**

1. Add SQLite database with SQLModel or SQLAlchemy
2. Persist:
   - Conversation sessions and message history
   - Task records and status
   - Project metadata
   - Agent artifacts
3. Add database migrations (Alembic)
4. Replace in-memory stores with database-backed stores
5. Use LangChain's `SQLChatMessageHistory` for conversation persistence

**Project Structure Update:**

```
app/
├── db/
│   ├── __init__.py
│   ├── database.py         # DB connection and session
│   ├── models.py           # SQLModel/SQLAlchemy models
│   └── migrations/         # Alembic migrations
```

**Acceptance Criteria:**

- [ ] Application data survives restarts
- [ ] Conversation history persisted and retrievable
- [ ] Task history with full agent interactions stored

---

### Step 9: Per-Agent Model Configuration

**Goal:** Allow different LLM models for different agent roles.

**What you'll learn:** Model routing, cost optimization, configuration management.

**Tasks:**

1. Add per-agent model configuration in settings:
   ```yaml
   agents:
     manager:
       model: "nvidia/nemotron-3-nano-30b-a3b:free"
       temperature: 0.3
     ba:
       model: "nvidia/nemotron-3-nano-30b-a3b:free"
       temperature: 0.5
     dev:
       model: "nvidia/nemotron-3-nano-30b-a3b:free"
       temperature: 0.2
     tester:
       model: "nvidia/nemotron-3-nano-30b-a3b:free"
       temperature: 0.1
   ```
2. Each agent instantiates its own LLM with role-specific settings
3. Add model fallback configuration (if primary model fails, try alternative)
4. Add usage tracking per agent (token counts, costs via OpenRouter)

**API Endpoints (updated):**

- `GET /api/v1/config/agents` — View agent configurations
- `PUT /api/v1/config/agents/{role}` — Update agent model config
- `GET /api/v1/usage` — View token usage and costs per agent

**Acceptance Criteria:**

- [ ] Each agent can use a different model
- [ ] Model configs changeable at runtime via API
- [ ] Token usage tracked per agent

---

### Step 10: Feature-Level Multi-File Projects

**Goal:** Agents can work on multi-file features with full project context.

**What you'll learn:** Context management, RAG-like patterns, project understanding.

**Tasks:**

1. Add project context gathering (read and summarize existing codebase)
2. Implement a project analyzer tool that builds a project map (files, functions, classes)
3. Dev agent creates multiple files in correct structure
4. BA agent creates comprehensive documentation (multiple docs)
5. Tester agent creates test files that correspond to source files
6. Add context window management (summarize large files, prioritize relevant context)

**RAG/retrieval for BA Agent** (moved from Step 3.1):
- When `project_id` is provided, BA should call a retriever (vector DB or file search) to fetch relevant docs and include short summaries in the prompt (top-k snippets)
- Store a pointer to retrieved docs in task artifacts
- This provides context grounding for BA analysis based on existing project documentation

**RAG/retrieval for Dev Agent** (moved from Step 3.2):
- Before generation, Dev should retrieve relevant code context (from vector DB or file search) so it can reference existing modules and avoid duplicate implementations
- Use a retriever to get top-k code snippets and include them in the planning prompt
- This enables context-aware code generation that respects existing patterns and architecture

**RAG/retrieval for Tester Agent** (moved from Step 3.3):
- Tester should retrieve related code snippets and previous bug reports from project history to prioritize tests
- Store references to where each test originated
- Use historical bug data to identify high-risk areas that need more thorough testing
- Retrieve similar test patterns from existing test suites for consistency

**New tools:**

- `analyze_project()` — Returns project structure with summaries
- `search_code(query)` — Search for patterns in project files
- `create_directory(path)` — Create directories in workspace

**Acceptance Criteria:**

- [ ] Can request "Add user authentication to the project"
- [ ] BA produces requirements, Dev creates multiple files (routes, models, middleware)
- [ ] Tester creates corresponding test files
- [ ] All files properly reference each other

---

### Step 11: Error Handling, Logging & Observability

**Goal:** Production-ready error handling, structured logging, and LLM call tracing.

**What you'll learn:** Observability, tracing, production hardening.

**Tasks:**

1. Add structured logging (JSON format) with Python's `logging` or `structlog`
2. Add global error handling middleware in FastAPI
3. Add request ID tracking across the full pipeline
4. Integrate LangSmith or LangFuse for LLM call tracing (optional but recommended)
5. Add retry logic for LLM API calls
6. Rate limiting on API endpoints
7. Input validation and sanitization

**Acceptance Criteria:**

- [ ] All errors return consistent JSON error responses
- [ ] Every request traceable end-to-end
- [ ] LLM calls visible in tracing dashboard
- [ ] Graceful handling of API failures

---

### Security, Safety & Operational Requirements

These requirements capture high-priority safety, validation, and operational controls discovered during a recent review. They must be treated as mandatory design constraints before enabling agent file writes or persisting full agent transcripts.

- **LLM output validation (Critical):** All structured outputs produced by agents (BA, Dev, Tester, Manager) MUST be validated against a formal schema (JSON Schema or Pydantic model). On validation failure, the system MUST automatically re-prompt the model with (a) the original output, (b) the validation error details, and (c) a concise instruction to return only the corrected structured payload. Use function-calling / structured output features where available. Enforce a capped retry loop (e.g., 3 attempts) and a clear, auditable fallback error when retries are exhausted.

- **File-write safety (High):** Implement and enforce a single `app/tools/file_tools.py::write_file(path, content, project_id, *, dry_run=False)` API that:
  - canonicalizes and normalizes paths and refuses `..` segments or absolute paths
  - enforces a workspace whitelist (writes only under `workspace/{project_id}`)
  - refuses writes to protected paths (`.git/`, CI configs, system paths) unless explicitly approved via an elevated human-approval workflow
  - enforces size limits and optional content-type checks
  - supports `dry_run=True` to return diffs without mutating disk
  - logs intended writes (path, size, checksum) to an audit store before applying

- **Secrets, redaction & audit logs (High):** Do not persist raw prompts/responses that may contain secrets or PII without redaction. Implement a redaction pipeline that removes API keys, tokens, private keys, and emails before storing. If full transcripts are required for debugging, encrypt them at rest and restrict access via RBAC. Document retention policies and provide configurable retention/rotation.

- **Orchestration semantics & reliability (Medium):** Manager endpoints that start long-running work SHOULD return `202 Accepted` with a `task_id` and accept idempotency keys. Persist task state (SQLite or small job DB) and expose status/streaming endpoints. Implement `max_retries`, exponential backoff, last_attempt, retry_count, and error_reason fields on task records.

- **RAG / retrieval safety (Medium):** When including retrieved context in prompts, always attach provenance (source pointer, character offsets, short summary). Limit the total injected characters and sanitize retrieved text to remove instruction-like fragments or code fences that may prompt-inject the agent. Store fingerprints for traceability.

- **Configuration, determinism & testing (Low):** Standardize canonical config paths (e.g. `app/config/agents.yaml` or `agent_config.yaml` — pick one and document). Prefer low temperature settings for structured outputs. Add deterministic unit tests that mock LLMs and retrievers, and CI jobs that run linters/formatters (`ruff`/`black`) on generated code artifacts.

**Immediate recommended engineering tasks:**
1. Add authoritative Pydantic/JSON Schema definitions to `app/models/schemas.py` and implement the validation + re-prompt loop for all agent output paths.
2. Create `app/tools/file_tools.py` (if not present) implementing the safety checklist above and add unit tests for path canonicalization, whitelist enforcement, and dry-run behavior.
3. Add a short section in `REQUIREMENTS.md` (this file) describing audit log retention and redaction rules and wire those rules into the Manager's audit logging design.


### Step 12: Authentication & Multi-Tenancy

**Goal:** Add API authentication and support for multiple users.

**What you'll learn:** API security, JWT tokens, user isolation.

**Tasks:**

1. Add API key or JWT-based authentication
2. User isolation — each user has their own projects and sessions
3. Workspace isolation — each user's files are separate
4. Add user management endpoints

**API Endpoints (updated):**

- `POST /api/v1/auth/register` — Register a new user
- `POST /api/v1/auth/login` — Login and receive JWT token
- `GET /api/v1/auth/me` — Get current user info

**Acceptance Criteria:**

- [ ] API endpoints require authentication
- [ ] Users can only access their own data
- [ ] Workspace directories isolated per user

---

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| LLM Framework | LangChain, LangGraph |
| LLM Provider | OpenRouter API (OpenAI-compatible) |
| Web Framework | FastAPI |
| Server | Uvicorn |
| Database | In-memory → SQLite (Step 8) |
| ORM | SQLModel or SQLAlchemy |
| Migrations | Alembic |
| Auth | python-jose (JWT) |
| Config | python-dotenv, Pydantic Settings |
| Logging | structlog |
| Tracing | LangSmith / LangFuse (optional) |

---

## Final Project Structure (after all steps)

```
dev-team/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, lifespan, middleware
│   ├── config.py                  # Settings, env loading
│   ├── dependencies.py            # FastAPI dependency injection
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── chat.py                # Individual agent chat endpoints
│   │   ├── team.py                # Team orchestration endpoints
│   │   ├── projects.py            # Project management endpoints
│   │   ├── tasks.py               # Task tracking endpoints
│   │   ├── auth.py                # Authentication endpoints
│   │   └── config_router.py       # Configuration endpoints
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                # Base agent class
│   │   ├── personas.py            # Persona definitions & prompts
│   │   ├── manager.py             # Manager agent
│   │   ├── ba.py                  # Business Analyst agent
│   │   ├── developer.py           # Developer agent
│   │   ├── tester.py              # Tester agent
│   │   └── team.py                # LangGraph team orchestration
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── file_tools.py          # File system operations
│   │   └── project_tools.py       # Project analysis tools
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py             # Pydantic request/response models
│   │   └── state.py               # LangGraph state definitions
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py            # DB connection
│   │   ├── models.py              # DB models
│   │   └── migrations/            # Alembic
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chat_service.py        # Chat business logic
│   │   ├── team_service.py        # Team orchestration logic
│   │   ├── project_service.py     # Project management logic
│   │   └── task_service.py        # Task tracking logic
│   └── middleware/
│       ├── __init__.py
│       ├── auth.py                # Auth middleware
│       ├── logging.py             # Request logging
│       └── error_handler.py       # Global error handling
├── workspace/                     # Agent workspace (project files)
├── tests/
│   ├── __init__.py
│   ├── test_chat.py
│   ├── test_team.py
│   └── test_tools.py
├── agent_config.yaml              # Agent personas & model configs
├── .env
├── .env.example
├── requirements.txt
├── REQUIREMENTS.md
└── README.md
```

---

## API Endpoint Summary (all steps combined)

| Method | Endpoint | Step | Description |
|---|---|---|---|
| GET | `/api/v1/health` | 1 | Health check |
| POST | `/api/v1/chat` | 1 | Chat with an agent |
| POST | `/api/v1/chat/stream` | 5 | Streaming chat (SSE) |
| GET | `/api/v1/sessions` | 2 | List sessions |
| GET | `/api/v1/sessions/{id}/history` | 2 | Get session history |
| DELETE | `/api/v1/sessions/{id}` | 2 | Delete session |
| GET | `/api/v1/agents` | 3 | List agent personas |
| POST | `/api/v1/projects` | 4 | Create project |
| GET | `/api/v1/projects` | 4 | List projects |
| GET | `/api/v1/projects/{id}/files` | 4 | List project files |
| GET | `/api/v1/projects/{id}/files/{path}` | 4 | Read a file |
| POST | `/api/v1/team/chat` | 6 | Chat with full dev team |
| POST | `/api/v1/team/chat/stream` | 6 | Streaming team chat |
| GET | `/api/v1/team/status/{task_id}` | 6 | Check team task status |
| GET | `/api/v1/tasks` | 7 | List tasks |
| GET | `/api/v1/tasks/{id}` | 7 | Task details |
| GET | `/api/v1/tasks/{id}/artifacts` | 7 | Task artifacts |
| GET | `/api/v1/config/agents` | 9 | Agent configs |
| PUT | `/api/v1/config/agents/{role}` | 9 | Update agent config |
| GET | `/api/v1/usage` | 9 | Token usage stats |
| POST | `/api/v1/auth/register` | 12 | Register user |
| POST | `/api/v1/auth/login` | 12 | Login |
| GET | `/api/v1/auth/me` | 12 | Current user info |

---

## Learning Progression Summary

| Step | What You Build | Key Learning |
|---|---|---|
| 1 | Simple chatbot API | LangChain + OpenRouter + FastAPI basics |
| 2 | Conversational memory | Session management, message history |
| 3 | Role-based personas | System prompts, prompt engineering |
| 4 | File system tools | LangChain tools, function calling, agents |
| 5 | Streaming responses | SSE, async streaming |
| 6 | Multi-agent team | LangGraph, orchestration, state machines |
| 7 | Task tracking | Workflow state, audit trails |
| 8 | Database persistence | SQLite, SQLModel, migrations |
| 9 | Per-agent models | Model routing, cost optimization |
| 10 | Multi-file features | Context management, project analysis |
| 11 | Observability | Logging, tracing, error handling |
| 12 | Auth & multi-tenancy | Security, user isolation |
