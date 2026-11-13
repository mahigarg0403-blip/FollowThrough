# Follow Through

> **Turn "we should" into "who, by when, and did it happen."**
> 
> 

**Follow Through** is an AI follow-up agent built for **Nonilion** chat workspaces. Unlike standard meeting summarizers that stop at a recap, Follow Through turns meeting transcripts into verified action items, resolves ambiguous ownership by asking the room, generates structured deliverables on demand, and actively chases task owners until the work is marked done.

Built by **Team PistaShew** (Mahi Garg, Bhoomi Shree, Priyal Modi) for **InnoVortex 4.0**.

---

## 🔗 Quick Links

* **Live Deployment:** 'https://followthrough-sb1e.onrender.com` / 'https://www.nonilion.com/room/MobileRoom1794553247470'


* **Demo Video:** https://drive.google.com/file/d/16r0_7yVJCGo_H719kjfCjvUhdHUdWMHu/view?usp=sharing



---

## ✨ What It Does

1. **Upload:** Drop a `.txt` meeting transcript into a Nonilion room and `@FollowThrough`.


2. **Extract (Never Guesses):** Extracts decisions and action items with an **Owner**, **Due Date**, and the **verbatim quote** from the transcript that proves it. Every quote and owner is validated in code against the raw transcript—if ownership isn't explicit, the agent never hallucinates a name.


3. **Ask:** Collects all unowned tasks into **one grouped question** to the room. Teammates can claim tasks in chat, or unanswered items automatically become `UNASSIGNED` after 30 seconds.


4. **Deliver:** Generates structured deliverables directly from stored task data on command:


* **Action Items CSV** (`action_items.csv`)


* **Markdown Meeting Minutes** (`minutes.md`)


* **HTML Status Report**


* **Workload Chart** (open tasks per owner, highlighting `Unassigned`)


* **Grounded Q&A** (answers questions like *"What's open for Priya?"* strictly from the task store, and politely declines out-of-scope actions like sending emails by offering a ready-to-send draft instead).




5. **Chase:** DMs task owners when items are due (with automatic room fallback if a member is unreachable), tracks `"done"`, `"snooze"`, and `"blocked"` replies, escalates after repeated nudges, and posts live progress updates + updated workload charts to the channel.



---

## 📸 Preview

*(Replace `docs/screenshot.png` with a screenshot of FollowThrough extracting tasks, posting the workload chart, and chasing owners in Nonilion)*

---

## 🏗️ Architecture & Project Structure

Follow Through uses a **single-source-of-truth task store**. The LLM is called **only once** during transcript extraction; all downstream exports, charts, Q&A responses, and reminders read strictly from validated records in storage.

```text
followthrough/
├── main.py                  # Entry point, command routing, and event loop[cite: 13, 21]
├── requirements.txt         # Python dependencies[cite: 21]
├── .env.example             # Required environment variables (no secrets)[cite: 12, 21]
├── data/
│   ├── sample_transcript.txt # Sample 5-minute meeting transcript for testing[cite: 14, 21]
│   └── sample_tasks.json    # Expected structured task records[cite: 14, 21]
├── src/
│   ├── store.py             # Task persistence and owner normalization[cite: 14, 21]
│   ├── agent/
│   │   ├── nonilion.py      # Nonilion MCP / HTTP client, DMs, and file uploads[cite: 4, 14, 21]
│   │   ├── extract.py       # LLM extraction + verbatim substring/owner checks[cite: 14, 21]
│   │   └── ask.py           # Grouped ownership question & timeout handling[cite: 14, 21]
│   ├── outputs/
│   │   ├── export.py        # CSV and Markdown minutes generators[cite: 14, 21]
│   │   ├── chart.py         # Workload chart generation[cite: 15, 21]
│   │   └── qa.py            # Store-grounded Q&A and email draft fallback[cite: 15, 21]
│   └── chase/
│       └── chase.py         # Owner reminders, reply tracking, and progress posts[cite: 15, 21]
├── docs/                    # Pitch deck, script, and judge Q&A guide[cite: 12, 21]
└── demo/                    # 5-minute demo run sheet and backup video[cite: 12, 21]

```

---

## 🚀 Getting Started

### 1. Prerequisites

* Python 3.11+


* A Nonilion Pro / Bot account & MCP/API credentials


* LLM API key (Anthropic / OpenAI-compatible endpoint configured in `.env`)



### 2. Local Setup

```bash
# Clone the repository
git clone https://github.com/<your-org-or-username>/followthrough.git
cd followthrough

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

```

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env

```

| Variable | Description | Example |
| --- | --- | --- |
| `NONILION_URL` | Nonilion MCP / workspace endpoint

 | `https://...` |
| `NONILION_TOKEN` | Bot authentication token

 | `your_bot_token` |
| `LLM_API_KEY` | API key for structured extraction

 | `sk-...` |
| `OWNER_HANDLES` | JSON map of owner names to exact Nonilion display names

 | `{"priya": "Bhoomi Shree", "arjun": "Priyal Modi"}` |
| `AUTO_CHASE` | Enable (`1`) or disable (`0`) background timer nudges

 | `0` |

### 4. Run the Bot

```bash
python main.py[cite: 13]

```

---

## ☁️ Deploying on Render

1. Create a new **Web Service** on [Render](https://render.com/) connected to this repository.


2. Set the build and start commands:
* **Build Command:** `pip install -r requirements.txt`


* **Start Command:** `python main.py`




3. Add all variables from `.env.example` under **Environment** in the Render dashboard (set `AUTO_CHASE=0` for controlled live demos).



---

## 💬 Chat Commands (Inside Nonilion)

Mention `@FollowThrough` in the workspace room:

| Command / Action | What Follow Through Does |
| --- | --- |
| Upload `.txt` + `@FollowThrough` | Extracts decisions & tasks, verifies quotes, asks about unowned tasks

 |
| `1 Arjun` *(replying to grouped question)* | Assigns task #1 to Arjun; remaining tasks auto-mark `UNASSIGNED` after 30s

 |
| `@FollowThrough chart` | Posts the open-tasks-per-owner workload breakdown & visual chart

 |
| `@FollowThrough csv` | Exports and attaches `action_items.csv`

 |
| `@FollowThrough minutes` | Exports and attaches `minutes.md`

 |
| `@FollowThrough report` | Generates and attaches the formatted HTML task report

 |
| `@FollowThrough What's open for Priya?` | Lists Priya's open tasks with deadlines and verbatim source quotes

 |
| `@FollowThrough Email this to the client` | Explains it cannot send emails externally and provides a ready-to-copy draft

 |
| `@FollowThrough chase now` | Triggers owner DMs (or room fallback reminders) for open tasks

 |
| `done 1` / `priya: done` | Marks the task complete and posts an updated team progress summary + chart

 |

---

## 🛡️ Known Limitations & Honest Design

* **Strict Grounding:** Follow Through intentionally refuses to guess owners or deadlines not supported by the transcript.


* **External Actions:** It does not send external emails or modify third-party calendars directly; it drafts messages inside Nonilion instead.


* **Transcript Quality:** Extraction accuracy depends on speaker attribution in the uploaded meeting transcript.
