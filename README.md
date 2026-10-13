# UFC-predictor

This project attempts to predict the winner of a UFC fight using statistics and betting odds. The goal is to beat the betting market.

# How to Install

### Requirements
- Python 3.12 or newer
- ~2 GB of free disk space for the downloaded pages

### 1. Clone the repository and create a virtual environment

```bash
git clone https://github.com/<your-username>/UFC-predictor.git
cd UFC-predictor

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

### 2. Install the dependencies

```bash
pip install -r requirements.txt
playwright install chromium        # browser used by the scraper
```

### 3. Scrape UFCStats and build the database

```bash
python download_pages.py           # downloads every event, fight and fighter page (takes a few hours)
python build_db.py                 # parses the pages into ufc.db (SQLite)
```

The scraper saves pages locally, so it is only run once, and information is later read from disk.

### 5. Run the model

```bash
jupyter notebook model.ipynb
```

Then choose **Kernel → Restart & Run All**. Building the training rows takes about 6 minutes, and the grid searches take a few more.