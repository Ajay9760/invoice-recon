import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./recon.db")
VALID_CURRENCIES = {"INR", "USD", "EUR", "GBP"}
TOLERANCE = 0.02  # max allowed difference (in currency units) for amount comparisons
