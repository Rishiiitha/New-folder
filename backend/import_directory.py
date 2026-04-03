import pandas as pd
from sqlalchemy import create_engine, text  # <-- 1. IMPORT 'text'
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# --- Your Database Configuration ---
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME")
TABLE_NAME = "student_directory"

# This matches your log
CSV_FILE = "Copy of 2024-2028 Batch Review 1 (Upto 08_03_2025) - Sheet1.csv" 

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

try:
    engine = create_engine(DATABASE_URL)
    print(f"Connecting to database '{DB_NAME}' at '{DB_HOST}'...")
    
    print(f"Reading CSV file: {CSV_FILE}...")
    
    df = pd.read_csv(CSV_FILE, header=0)

    # 2. Select and rename the columns we need
    df = df.rename(columns={
        'Mail id': 'email', 
        'Register No.': 'roll_no'
    })
    
    df = df[['email', 'roll_no']]

    # 3. Clean the data
    print("Cleaning data...")
    df = df.dropna() 
    
    df['email'] = df['email'].str.lower().str.strip()
    df['roll_no'] = df['roll_no'].str.upper().str.strip()
    
    df = df[df['email'].str.contains('@')]
    df = df[df['roll_no'].str.len() > 5]


    # 4. Import data into PostgreSQL
    print(f"Importing {len(df)} records into table '{TABLE_NAME}'...")
    
    df.to_sql(TABLE_NAME, engine, if_exists='replace', index=False)

    # 5. Set the PRIMARY KEY and UNIQUE constraint
    # --- 2. THIS IS THE FIX ---
    # Use engine.begin() for a transaction and wrap SQL in text()
    print("Setting primary key and unique constraints...")
    with engine.begin() as con:
        con.execute(text(f'ALTER TABLE {TABLE_NAME} ADD PRIMARY KEY (email);'))
        con.execute(text(f'ALTER TABLE {TABLE_NAME} ADD CONSTRAINT roll_no_unique UNIQUE (roll_no);'))

    print("\nSuccessfully imported student directory!")

except FileNotFoundError:
    print(f"Error: The file '{CSV_FILE}' was not found.")
    print("Please make sure it's in the 'backend' directory.")
except KeyError as e:
    print(f"Error: A column was not found. {e}")
    print("Please check the 'rename' section of the script and your CSV headers.")
except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(1)