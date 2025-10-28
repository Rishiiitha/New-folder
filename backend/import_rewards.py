import pandas as pd
from sqlalchemy import create_engine
import sys
import re # Import the regex module

# --- Your Database Configuration ---
DB_USER = "postgres"
DB_PASS = "Veeraragava"
DB_HOST = "localhost"
DB_NAME = "Student_data"
TABLE_NAME = "student_rewards" # The table we created in Step 1
CSV_FILE = "DEPARTMENT-WISE REWARD POINTS as on Tue Oct 28 2025 00_21_37 GMT+0530 (India Standard Time) - CSE.csv"

# Construct the database connection URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

def clean_column_name(col_name):
    """Cleans a single column name."""
    if not isinstance(col_name, str):
        return str(col_name)
    # 1. Convert to lower case
    name = col_name.lower()
    # 2. Replace 'REEDEMED' with 'REDEEMED' specifically
    name = name.replace('reedemed', 'redeemed')
    # 3. Replace any non-alphanumeric characters (like '.', ' ') with an underscore
    name = re.sub(r'[\. ]+', '_', name)
    # 4. Remove any leading/trailing underscores
    name = name.strip('_')
    return name

try:
    # Connect to the database
    engine = create_engine(DATABASE_URL)
    print(f"Connecting to database '{DB_NAME}' at '{DB_HOST}'...")
    
    # 1. Load the CSV file
    print(f"Reading CSV file: {CSV_FILE}...")
    df = pd.read_csv(CSV_FILE, header=4, skiprows=[5])

    # 2. Select only the first 10 columns that matter
    df = df.iloc[:, :10]

    # 3. Clean column names using our new function
    df.columns = [clean_column_name(col) for col in df.columns]

    # 4. Clean numeric data
    # These names now match the cleaned column names
    print("Cleaning data...")
    cols_to_clean = ['cumulative_reward_points', 'redeemed_points', 'balance_points']
    
    for col in cols_to_clean:
        if col not in df.columns:
            print(f"Warning: Expected column '{col}' not found after cleaning. Skipping.")
            continue
            
        # Remove commas, convert to float, handle errors
        df[col] = df[col].astype(str).str.replace(',', '', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # Drop any rows where roll_no is missing, as it's the primary key
    df = df.dropna(subset=['roll_no'])
    
    # Ensure all data is clean before insertion
    df = df.fillna(pd.NA)

    # 5. Import data into PostgreSQL
    print(f"Importing {len(df)} records into table '{TABLE_NAME}'...")
    # 'if_exists='replace'' will drop the table and recreate it.
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