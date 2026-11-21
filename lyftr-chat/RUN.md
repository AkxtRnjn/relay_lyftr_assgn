# Run Lyftr Chat on Windows

**Extract the entire ZIP, open the lyftr-chat folder and double-click run.cmd.** File Explorer may show it as **run** with type **Windows Command Script**. This one launcher starts the API and the chat interface. You can leave the backend and frontend folders alone.

## What you need

| Item | When you need it |
| --- | --- |
| 64-bit CPython 3.10 or newer with pip and venv | Install once on your computer. Python 3.12 is the version used for the app test. The launcher checks your existing installation first. |
| Windows PowerShell and a web browser | PowerShell runs the launcher. Your browser displays the chat. |
| Internet access and two distinct provider API keys | Internet access downloads missing Python packages. Live chat uses two keys with access to the same model, so it can switch keys after a provider failure. The default model is openai/gpt-4o-mini. |

The ZIP includes a built copy of the React interface. Node.js and npm are for editing or rebuilding that interface. Docker Desktop, Git, Make and a separate database installation are optional for this launcher. Python includes SQLite.

## If you saw the App Installer error

The earlier launcher searched specifically for Python 3.12 and tried winget when it missed that version. Download and extract the updated ZIP. To use an existing project folder, copy the updated project files over it and keep your local .env and backend/data folder.

The new launcher checks the project's Python environment, the Windows Python launcher, PATH, registered installations and common install folders. It prints the selected version and executable. If your Python is elsewhere, open the terminal where Python already works and run:

```powershell
python -c "import sys, struct; print(sys.executable); print(sys.version); print(struct.calcsize('P') * 8)"
```

If you normally start Python with `py`, use `py -3` in place of `python`. The first output line is the path to paste when run.cmd asks for **python.exe**. The last line should say **64**. If you need to install Python, pressing Enter at that prompt uses winget when available. You can also use the [official Windows Python installer](https://www.python.org/downloads/windows/) with pip enabled.

## Test with Gemini on a free-tier project

The assignment accepts Gemini. OpenAI is the example default in this package. To use Gemini with your existing Windows installation:

1. Press Ctrl+C if run.cmd is waiting for a key. Open the folder containing run.cmd.
2. Open .env in Notepad. If it does not exist, copy .env.example to .env first.
3. In [Google AI Studio](https://aistudio.google.com/apikey), select your free-tier project and create two distinct API keys. Check that your project has free quota for Gemini 3.1 Flash-Lite. Leave billing disabled for free-only testing.
4. Update these three existing settings in .env. Replace the placeholders with the actual keys, separated by a comma. Keep the other settings.

```dotenv
LLM_MODEL=gemini/gemini-3.1-flash-lite
LLM_API_KEYS=first-gemini-key,second-gemini-key
LLM_API_BASE=
```

5. Save .env, double-click run.cmd and send a message. Both keys in one project share its quota. Use the assignment's simulated failure header to demonstrate a key switch while quota is available.

For backend contract tests without a provider account, see the offline-provider test instructions in README.md.

## First launch and later runs

1. Double-click **run.cmd** or run `.\run.cmd` in PowerShell from the extracted project folder.
2. Wait while it creates or reuses **backend/.venv** and installs missing packages. This project-local folder keeps the app's libraries together. You install Python itself only once.
3. When prompted, paste each of your two API keys and press Enter. The characters stay hidden while you type. The launcher saves them in the project's local .env for future runs.
4. When the browser opens, send a message. If needed, open [the chat](http://localhost:3000) yourself. The [API health endpoint](http://127.0.0.1:8000/health) shows readiness and the configured key count.

Keep the launcher window open during use. Press **Ctrl+C** there to stop both services. Double-click the same file to restart. Chat history is stored in backend/data/app.db with the default settings.

If a port is occupied, stop the previous launcher or Docker instance first. If health works but chat returns “all providers unavailable”, check the model, key permissions and quota in .env and restart. See [README.md](README.md) for Docker, frontend development and deployment.

## Return to a previous conversation

Choose **Recent chats** in the sidebar. Each entry shows its opening message and the last six characters of its ID, so two chats with the same opening question are distinguishable. Opening one restores its replies and per-request metadata from SQLite. Sending another message continues that session. A page refresh starts a blank chat and keeps the recent list in the same browser.

For a chat created before this feature, choose **Open by session ID**. Double-click **list-chats.cmd** in your existing project folder to list saved conversations from the original database.

Copy the ID next to the opening message, paste it into **Open by session ID**, then click **Open chat**. The conversation will also appear in Recent chats.
