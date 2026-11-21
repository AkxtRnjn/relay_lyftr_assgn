# Relay | Lyftr AI full-stack assignment

Relay is a multi-turn chat app built with React, FastAPI, LiteLLM and SQLite. Each reply shows its model, source, latency and token usage. You can reproduce a key failure on a single request and inspect the resulting conversation in SQLite through the history endpoint.

**Windows quick start:** Extract the project and double-click **run.cmd**. The launcher installs missing dependencies and starts both services. See [RUN.md](RUN.md) for first-run setup and troubleshooting.

## 1. Live URLs

| Deliverable | Status |
| --- | --- |
| Public frontend | Pending deployment |
| Public backend and health endpoint | Pending deployment |
| Public GitHub repository | Pending publication |
| 2–3 minute narrated demo | Pending recording |

**Deployment recipe.** Push the contents of this folder to your public repository. For the backend, choose a Docker host that supports a persistent writable volume. Use `backend` as the build context, run its Dockerfile, route HTTPS traffic to container port 8000 and mount storage at `/data`. Give the service user (UID 10001) write access to that mount. Configure the backend variables from the table below, including two provider keys, and use `/health` as the readiness path. Use one replica and one Uvicorn worker.

For the frontend, configure a static host with root directory `frontend`, build command `npm ci && npm run build` and output directory `dist`. At build time, set `VITE_API_URL` to the public HTTPS backend origin. Add the public HTTPS frontend origin to backend `ALLOWED_ORIGINS` and restart the backend. Run the verification script against that backend, then open the public frontend in a private browser window and send a message. Replace the status entries above with the working URLs.

## 2. Run locally: with Docker and without

Extract the ZIP first. Open the extracted **lyftr-chat** folder in File Explorer, type `powershell` in the address bar and press Enter. The current folder should contain `docker-compose.yml`, `.env.example` and this README.

### Windows with Docker Desktop

Start Docker Desktop with the Linux container engine. Check that both commands succeed.

```powershell
docker version
docker compose version
```

Create your local configuration once.

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace both placeholders in `LLM_API_KEYS` with **two distinct active keys** that can call the configured model. Save the file as exactly `.env`. The default model uses OpenAI. To test with Gemini using a free-tier project, follow **Test with Gemini on a free-tier project** in [RUN.md](RUN.md). A provider account with API access and available quota is required for live inference.

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Start-Process http://localhost:3000
```

The first build downloads Python and JavaScript dependencies. Health should report `status = ok`, the configured key count, and `cache_enabled = True`. Sending a message verifies that a key actually works. If GNU Make is installed, `make up` starts the same stack and `make down` stops it. Plain PowerShell can use `docker compose down`. The named volume retains history across these stops.

### Windows development without Docker

For everyday use, run.cmd serves the bundled React build with Python alone. The following two-terminal setup is for developers who want frontend hot reload. To refresh the bundled copy after editing the UI, run `npm.cmd run build -- --outDir local-ui` in frontend with VITE_API_URL set to http://localhost:8000.

Install **64-bit Python 3.12** with the Python launcher and **Node.js 22** with npm. In the project root, create and edit `.env` as above. Change **DATABASE_URL** in that file to `sqlite:///./data/app.db`. This path is relative to the backend's working directory. Use two PowerShell windows.

**Window 1 · API** — start from the project root. Calling the virtual environment's Python directly works without activating a PowerShell script.

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**Window 2 · UI** — open another PowerShell in the project root.

```powershell
Set-Location frontend
$env:VITE_API_URL = "http://localhost:8000"
npm.cmd ci
npm.cmd run dev -- --host localhost --port 3000 --strictPort
```

Open [the local chat](http://localhost:3000). Stop each process with Ctrl+C. The native database is in `backend/data/app.db`. The Docker database is in its named volume.

| Setting | Purpose |
| --- | --- |
| LLM_API_KEYS | Backend secret. Comma-separated keys, in failover order. |
| LLM_MODEL | One LiteLLM provider/model identifier accessible to every key. |
| LLM_API_BASE | Optional compatible endpoint base URL. Leave blank for the provider default. |
| DATABASE_URL | Use `sqlite:////data/app.db` in Docker and `sqlite:///./data/app.db` for native Windows. |
| ALLOWED_ORIGINS | Comma-separated browser origins including scheme and port, without trailing slashes. |
| ENABLE_FAILURE_SIMULATION | Set to `true` on the assignment deployment to enable the demo header. |
| VITE_API_URL | Browser-visible API origin. Rebuild the production frontend after changing it. |
| LITELLM_LOCAL_MODEL_COST_MAP | Use LiteLLM's bundled model metadata when set to `True`. |

**Troubleshooting**

| Symptom | Check |
| --- | --- |
| Docker cannot connect to its engine | Start Docker Desktop and wait for `docker version` to print the Server section. |
| Backend is unhealthy | Run `docker compose logs --tail 80 backend`. Check key count, database path and volume permissions. |
| Health succeeds, chat returns 503 | Check provider quota and model access for both keys. Remove any simulated failure header. Keys in the same provider project can share quota. |
| Chat reports a connection error | Open the backend health URL in the browser. Match the exact UI origin in `ALLOWED_ORIGINS` and check the frontend build's API URL. |
| Port already in use | Use `Get-NetTCPConnection -LocalPort 3000,8000 -State Listen` to identify the process occupying an assignment port. |
| PowerShell blocks npm.ps1 | Use `npm.cmd` as shown above. |

## 3. Design decisions: key fallback, caching, SQLite session storage

- **Key fallback.** The gateway calls LiteLLM once per credential in configured order. SDK retries are disabled. A failed provider call, timeout or unusable reply advances to the next credential. The API returns a bounded key alias and the number of earlier failed attempts. Exhaustion returns HTTP 503 with a JSON detail. The request-scoped simulation hook skips exactly the selected credentials and bypasses cache reads so it can demonstrate a real fallback even on a warm prompt.
- **Caching.** LiteLLM's built-in local cache stores successful answers and their provider-reported token counts for one hour. Its key hashes the model and canonical JSON for the entire ordered message list, including the system prompt. New sessions can reuse identical inputs. Follow-up prompts with different histories have different keys. A hit returns the stored text and usage with a null key ID and zero fallback attempts. Latency is measured on each request. Restarting the backend clears the in-memory cache.
- **SQLite.** Startup creates the schema and session-order index. Each successful turn writes the user message, assistant reply, metadata and prompt update in one transaction. Failed turns leave history intact. A bounded set of process-local locks serializes turns for the same session. SQLite WAL permits concurrent readers. Single-worker deployment keeps the cache and session locks coherent. Each browser page load creates a fresh session ID.
- **Token accounting.** The input count covers that call's system prompt, prior turns and new message. The output count covers the current reply. A cache hit displays the stored counts for the original completion and makes zero provider calls.

## 4. Verification: how to see failover, cache hits and per-message token usage

**With two real keys**, start the app, then open PowerShell at the project root. This smoke test makes live calls that use provider quota. It prints the metadata side by side and stops at the first failed check.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
# For a deployed backend, substitute its actual HTTPS origin:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -BaseUrl "https://YOUR-BACKEND"
```

The script generates a unique first message for each run, reuses it in a second session, asks a follow-up, simulates 429 and 500 on the first key, and simulates total failure. It then reads history and verifies that the failed turn added no rows. The process-scoped execution policy applies only to this invocation.

| Request | Expected result |
| --- | --- |
| GET /health | 200 with readiness, key count and cache flag |
| POST /chat with a fresh session and unique message | LIVE_INFERENCE with the answering key and per-call token counts |
| Same first message and system prompt in another new session | LLM_CACHE, identical reply and usage, null key_id, lower latency |
| Same session with a follow-up | The provider receives prior turns and returns new usage |
| X-Simulate-Failure header set to key_1=429 or key_1=500 | Real answer from key_2 with one fallback when key_2 is healthy |
| X-Simulate-Failure set to *=429 | 503 with detail “all providers unavailable” |
| Blank or oversized message | 422 with detail and no history write |
| GET /sessions/{session_id}/messages | User and assistant messages in order. Unknown ID returns 404. |

**Try it in the UI.** Send “Remember the word saffron.” Ask “Which word?” and inspect the metadata under each answer. Click **New chat**, submit the exact original first message and compare its source, latency and tokens with the first reply. Copy the session ID before starting another chat to inspect its stored history.

**Check persistence with Docker.** After running the smoke test, copy the history URL it printed. Run `docker compose restart backend`, wait for health to return, then open that same history URL again.

**Run backend tests without paid credentials.** In the native Windows setup, run from the project root. The tests use a temporary SQLite database and an HTTP provider running on loopback. They exercise actual LiteLLM calls, cache reads, HTTP errors, session isolation, concurrent turns, validation and restart persistence.

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**2–3 minute recording guide.** Record the deployed app and your own narration. Spend the first 40 seconds showing a conversation and its metadata. Start a new session and repeat the first prompt to show the cache. At around 1:10, run the script against the public backend and explain the switch to key_2. Finish by opening the health and history URLs, showing the failed turn was discarded, and pointing to the repository. Keep credentials and the contents of .env off screen. Submit the four public links using the [assignment form](https://docs.google.com/forms/d/e/1FAIpQLSfaPS5_NliZuEjhYXppeafBrNM9u0hp-q-vT8vDuv9GU-0THA/viewform).

## 5. Setup Used: your editor and AI tools

Built and edited with OpenAI Codex in a Linux shell workspace. The project uses Python, React, Vite and Docker Compose. The Windows commands target Windows PowerShell and use .cmd and .exe explicitly where execution-policy differences matter.

## 6. Bonus features (if any): what you added beyond the requirements and why

The session panel shows gateway readiness and lets you set a system prompt before the first message. New chat creates a fresh session without a page reload. A failed send restores the draft so you can retry. The Windows verification script also works against the public deployment, making the same checks repeatable during review.
