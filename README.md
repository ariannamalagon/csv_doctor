# CSV Doctor

A simple CLI to clean CSV files (standardize column names/values, coerce dates/numbers, drop duplicates) and save a `{file}_cleaned.csv` alongside the input.

## Features
- Standardizes column names ("Date Paid" → `date_paid`)
- Lowercases/strips `category` and `description`
- Parses `date` to datetime (invalid → NaT)
- Converts `amount` to numeric (invalid → NaN)
- Drops duplicate rows
- Handles multiple files in one run with basic error messages

## Requirements
- Python 3.10+
- pandas (see `requirements.txt`)

## Setup
```bash
cd csv_doctor
python -m venv .venv
.\.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Usage
From the repo root:
```bash
cd csv_doctor
python -m src.main
```
Then follow the prompts:
1) Enter a CSV filename or full path.
2) Add more files? (y/n)
3) The cleaned files are written next to the originals as `{filename}_cleaned.csv`.

## Expected Columns
The cleaner assumes these columns exist:
- `date`
- `amount`
- `category`
- `description`

## Error Handling
- Warns if file not found or not `.csv`
- Handles empty/parse errors gracefully
- Reports missing expected columns
- Reports permission/save errors

## Project Structure
- `src/main.py` — CLI entry point and file orchestration
- `src/file_utils.py` — Cleaning helpers/ functions
- `data_storage/` — Place your input CSVs (outputs are written alongside)
