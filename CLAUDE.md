# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains an **Invoice Processing System** (发票智能筛选系统) for employee reimbursement at 深圳前海微众银行股份有限公司.

There are two implementations:

1. `invoice_processor/` - primary implementation (PDF text extraction + Markdown report)
2. `invoice_reimbursement/` - alternative implementation (OCR/image-first + Excel report)

Unless user asks otherwise, work on **`invoice_processor/`**.

## Running the Primary System

From repo root (`D:\workspace\invoice-dqc`):

```powershell
# activate venv
.\.venv\Scripts\Activate.ps1

# install deps
python -m pip install -r .\invoice_processor\requirements.txt

# run
python .\invoice_processor\main.py --month 2026-02

# optional args
python .\invoice_processor\main.py --month 2026-02 --invoice-pool invoice --output-dir output
```

## Current Runtime Model (Important)

`invoice_processor` now uses a **full rebuild** model per run:

1. Clear `output/` at startup (best-effort; locked paths are skipped with warning)
2. Read invoices **only from `invoice/*.pdf`**
3. Recognize + validate + select
4. Write results to `output/{month}/`, `output/unused/`, `output/errors/`
5. Generate `output/报销报告_{month}.md`

### What it no longer does

- No incremental backup to `invoice_bak/`
- No loading/merging historical selected invoices from `output/{month}/`
- No moving/renaming files in `invoice/`

## Architecture (`invoice_processor/`)

Pipeline:

```
main.py (CLI)
  ↓
InvoiceProcessor (orchestrator)
  ├─ InvoiceRecognizer (pdfplumber -> PyMuPDF fallback)
  ├─ InvoiceValidator (business rules)
  ├─ InvoiceSelector (combination optimization)
  ├─ FileManager (clear output + copy files)
  └─ ReportGenerator (Markdown report)
```

## Core Components

| File | Responsibility |
|---|---|
| `processor.py` | Orchestration: scan invoice pool, recognize/validate/select, write output |
| `recognizer.py` | Extract invoice fields (date, amount, buyer/seller, items, type) |
| `validator.py` | Rule checks (period, header/tax id, blacklist, type constraints) |
| `selector.py` | Per-type combination selection with 30% over-limit tolerance |
| `file_manager.py` | Clear `output/`; copy selected/unused/error files to output folders |
| `reporter.py` | Generate and print markdown summary |
| `models.py` | `InvoiceInfo`, `InvoiceType`, `InvoiceStatus`, `SelectionResult` |
| `config.py` | Company info, limits, keywords, blacklist, error codes |

## File Operations (Current Behavior)

`FileManager` uses **copy**, not move:

- `SELECTED` -> copy to `output/{month}/`
- `UNUSED` -> copy to `output/unused/`
- `ERROR` -> copy to `output/errors/`

Source files in `invoice/` remain unchanged.

## Directory Structure

```text
invoice/                         # input invoice pool (source of truth)
invoice_processor/               # primary system
invoice_reimbursement/           # alternative system
output/
  ├── {YYYY-MM}/                # selected invoices
  ├── unused/                   # unused invoices
  ├── errors/                   # invalid invoices
  └── 报销报告_{YYYY-MM}.md      # markdown report
```

## Business Rules (from `config.py`)

### Subsidy limits

- Dining (餐饮): 680.00
- Transport (交通): 500.00
- Communication (通讯): 300.00

### Validation highlights

1. Invoice date must be in allowed billing window (`ALLOWED_BILLING_PERIOD_MONTHS`, default 3)
2. Buyer name + buyer tax id must match `COMPANY_INFO`
3. Blacklist suppliers are rejected (`BLACKLIST_SUPPLIERS`)
4. Duplicate invoice numbers in same run are marked duplicate (`is_duplicate=True`)

## Recognizer Notes

`recognizer.py` includes:

- Date extraction fallback chain (explicit field -> near tax authority text -> generic date)
- Buyer/seller extraction for normal and split-line layouts
- Extra fallback for column-style name+tax-id blocks (recently added)

## Selection Strategy (`selector.py`)

Per type:

- Keep only valid, non-duplicate invoices
- Try all combinations (`itertools.combinations`)
- Target closest to type limit, allow up to `1.3 * limit`
- Prefer fewer invoices / lower over-limit when scores tie

## Naming Conventions (`models.py`)

Output file naming:

- Selected: `{type}_{amount}_{id}.pdf`
- Unused: `[EXTRA]{type}_{amount}_{id}.pdf`
- Error: `[ERROR-{code}]{type}_{amount}_{id}.pdf`
- Duplicate: `[ERROR-DUP]{original_name}`

## Alternative System (`invoice_reimbursement/`)

Used only when explicitly requested.

```powershell
cd .\invoice_reimbursement
python -m pip install -r requirements.txt
python .\main.py --month 2026-02 --employee "张三"
```

## Documentation

- `invoice_processor/README.md`
- `invoice_processor/发票处理规则说明.md`