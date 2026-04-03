import pandas as pd
from sqlalchemy import create_engine
import sys
import re 

DB_USER = "postgres"
DB_PASS = "Veeraragava"
DB_HOST = "localhost"
DB_NAME = "Student_data"
TABLE_NAME = "student_rewards" 
CSV_FILE = "DEPARTMENT-WISE REWARD POINTS as on Tue Oct 28 2025 00_21_37 GMT+0530 (India Standard Time) - CSE.csv"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

def clean_column_name(col_name):
    """Cleans a single column name."""
    if not isinstance(col_name, str):
        return str(col_name)
    name = col_name.lower()
    name = name.replace('reedemed', 'redeemed')
    name = re.sub(r'[\. ]+', '_', name)
    name = name.strip('_')
    return name

try:
    engine = create_engine(DATABASE_URL)
    print(f"Connecting to database '{DB_NAME}' at '{DB_HOST}'...")
    
    print(f"Reading CSV file: {CSV_FILE}...")
    df = pd.read_csv(CSV_FILE, header=4, skiprows=[5])

    df = df.iloc[:, :10]

    df.columns = [clean_column_name(col) for col in df.columns]

    print("Cleaning data...")
    cols_to_clean = ['cumulative_reward_points', 'redeemed_points', 'balance_points']
    
    for col in cols_to_clean:
        if col not in df.columns:
            print(f"Warning: Expected column '{col}' not found after cleaning. Skipping.")
            continue
        df[col] = df[col].astype(str).str.replace(',', '', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['roll_no'])
    df = df.fillna(pd.NA)

    print(f"Importing {len(df)} records into table '{TABLE_NAME}'...")
    df.to_sql(TABLE_NAME, engine, if_exists='replace', index=False)

    print("\nSuccessfully imported data into the database!")
    print(f"Check your '{TABLE_NAME}' table in the '{DB_NAME}' database.")

except FileNotFoundError:
    print(f"Error: The file '{CSV_FILE}' was not found.")
    print("Please make sure the script is in the same directory as the CSV.")
except ImportError:
    print("Error: Missing required libraries.")
    print("Please run: pip install pandas sqlalchemy psycopg2-binary")
except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(1)