# Mock Legacy Credit Union Admin

Small local application for the interface.ai computer-use automation take-home.

## Workflow

1. Search for a member.
2. View the member profile and current accounts.
3. Choose **Open New Sub-account**.
4. Select Savings or Checking.
5. Continue to **Review New Sub-account**.
6. Stop at checkpoint `REVIEW_READY`.

The app intentionally does not implement the irreversible "create account" action.

## Demo records

- `12345` — valid member
- `56789` — valid member
- `99999` — returns `MEMBER_NOT_FOUND`

## Run

From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload
```

Open:

`http://127.0.0.1:8000`

## Happy-path manual test

1. Enter `12345`.
2. Click **Search Member**.
3. Click **Open New Sub-account**.
4. Select **Savings**.
5. Click **Continue**.
6. Verify the page says `CHECKPOINT: REVIEW_READY`.

## Business-outcome test

1. Return to the search page.
2. Enter `99999`.
3. Click **Search Member**.
4. Verify the page says `OUTCOME: MEMBER_NOT_FOUND`.
