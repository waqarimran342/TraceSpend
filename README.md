# TraceSpend

TraceSpend is a receipt auditing and split-billing application developed for the Banana Hacks 2026 hackathon. The app allows users to upload a receipt image, extract key values using OCR, review parsed amounts, detect mismatches, and split the bill among people.

## Team Members

- Waqar Imran — Team Leader
- Taha Nadeem — Frontend
- Ahad Ata — Backend
- Ahmer Ijaz — AI integration and Testing

## Project Overview

TraceSpend helps users:
- upload a receipt photo
- detect and highlight suspicious totals, taxes, and fees
- manually correct extracted numbers
- review audit findings
- calculate shared expenses among participants
- use AI-assisted review for ambiguous values

## Tech Stack

- Python
- FastAPI
- OpenCV / Pillow
- OCR with Tesseract and pytesseract
- HTML / CSS / JavaScript frontend
- pytest for automated testing

## Local Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/waqarimran342/TraceSpend.git
   cd TraceSpend
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Ensure Tesseract OCR is available on your machine:
   - Windows: install Tesseract and make sure `tesseract.exe` is on PATH
   - Or use the default installation directory: `C:\Program Files\Tesseract-OCR\tesseract.exe`

## Run the Application

Start the backend and frontend app with:

```bash
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/
```

## Run Tests

```bash
pytest -q
```

## Notes

This project is designed for receipt auditing and quick validation of totals before final payment or reimbursement decisions. It is intended to assist users in reviewing receipts, not to replace official accounting or legal validation.
