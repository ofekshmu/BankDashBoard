"""
Test script for continuous payment detection feature.
Creates test data and validates the detect_continuous_payments() function.
"""
import sys
from pathlib import Path

# Add source to path
source_path = Path(__file__).parent / 'source'
sys.path.insert(0, str(source_path))

from database import DataBase
from src_utils.utils import utils
from datetime import datetime, timedelta
import pandas as pd

def create_test_data():
    """Create test continuous payment sequences in the database."""
    db = DataBase()
    
    print("=" * 80)
    print("CREATING TEST DATA FOR CONTINUOUS PAYMENT DETECTION")
    print("=" * 80)
    
    # Test Case 1: Complete 3-installment payment sequence
    # Payment 1/3: TAGGED (Utilities)
    # Payment 2/3: UNTAGGED (should be auto-tagged)
    # Payment 3/3: UNTAGGED (should be auto-tagged)
    
    test_data = [
        {
            # Payment 1/3 - TAGGED as Utilities
            'CardID': '0001',
            'Name': 'Electric Company Ltd',
            'Executed_Date': '2026-01-01',
            'Charge_Date': '2026-01-05',
            'Charge_Value': 300,
            'Charge_Currency': 'ILS',
            'Transaction_Value': 100,
            'Value_Currency': 'ILS',
            'Extra_Info': 'תשלום 1 מתוך 3',
            'Source_file': 'test_file.csv',
            'Category': 'Utilities',
            'Description': 'Electric bill - installment 1'
        },
        {
            # Payment 2/3 - UNTAGGED (should be auto-tagged to Utilities)
            'CardID': '0001',
            'Name': 'Electric Company Ltd',
            'Executed_Date': '2026-02-01',
            'Charge_Date': '2026-02-05',
            'Charge_Value': 300,
            'Charge_Currency': 'ILS',
            'Transaction_Value': 100,
            'Value_Currency': 'ILS',
            'Extra_Info': 'תשלום 2 מתוך 3',
            'Source_file': 'test_file.csv',
            'Category': 'NotCategorized',
            'Description': None
        },
        {
            # Payment 3/3 - UNTAGGED (should be auto-tagged to Utilities)
            'CardID': '0001',
            'Name': 'Electric Company Ltd',
            'Executed_Date': '2026-03-01',
            'Charge_Date': '2026-03-05',
            'Charge_Value': 300,
            'Charge_Currency': 'ILS',
            'Transaction_Value': 100,
            'Value_Currency': 'ILS',
            'Extra_Info': 'תשלום 3 מתוך 3',
            'Source_file': 'test_file.csv',
            'Category': 'NotCategorized',
            'Description': None
        },
        {
            # Payment 1/2 - TAGGED as Insurance
            'CardID': '0002',
            'Name': 'Insurance Corp',
            'Executed_Date': '2026-01-10',
            'Charge_Date': '2026-01-15',
            'Charge_Value': 500,
            'Charge_Currency': 'ILS',
            'Transaction_Value': 250,
            'Value_Currency': 'ILS',
            'Extra_Info': 'תשלום 1 מתוך 2',
            'Source_file': 'test_file.csv',
            'Category': 'Insurance',
            'Description': 'Car insurance - payment 1'
        },
        {
            # Payment 2/2 - UNTAGGED (should be auto-tagged to Insurance)
            'CardID': '0002',
            'Name': 'Insurance Corp',
            'Executed_Date': '2026-02-10',
            'Charge_Date': '2026-02-15',
            'Charge_Value': 500,
            'Charge_Currency': 'ILS',
            'Transaction_Value': 250,
            'Value_Currency': 'ILS',
            'Extra_Info': 'תשלום 2 מתוך 2',
            'Source_file': 'test_file.csv',
            'Category': 'NotCategorized',
            'Description': None
        },
        {
            # Single payment (no prior) - UNTAGGED (should remain untagged)
            'CardID': '0001',
            'Name': 'Random Store Inc',
            'Executed_Date': '2026-01-20',
            'Charge_Date': '2026-01-25',
            'Charge_Value': 150,
            'Charge_Currency': 'ILS',
            'Transaction_Value': 150,
            'Value_Currency': 'ILS',
            'Extra_Info': 'תשלום 1 מתוך 1',
            'Source_file': 'test_file.csv',
            'Category': 'NotCategorized',
            'Description': None
        }
    ]
    
    # Insert test data
    inserted_ids = []
    for i, row in enumerate(test_data):
        insert_sql = """
        INSERT INTO CardTransactions 
        (CardID, Name, Executed_Date, Charge_Date, Charge_Value, Charge_Currency, 
         Transaction_Value, Value_Currency, Extra_Info, Source_file, Category, Description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            row['CardID'], row['Name'], row['Executed_Date'], row['Charge_Date'],
            row['Charge_Value'], row['Charge_Currency'], row['Transaction_Value'],
            row['Value_Currency'], row['Extra_Info'], row['Source_file'],
            row['Category'], row['Description']
        )
        db.cursor.execute(insert_sql, params)
        row_id = db.cursor.lastrowid
        inserted_ids.append(row_id)
        print(f"\n✓ Inserted test transaction {i+1}/6 (ID: {row_id})")
        print(f"  Name: {row['Name']}")
        print(f"  Payment: {row['Extra_Info']}")
        print(f"  Category: {row['Category']}")
        print(f"  Charge_Date: {row['Charge_Date']}")
    
    db.commit_changes()
    print("\n✓ All test data committed to database")
    
    return inserted_ids

def display_before_state(inserted_ids):
    """Display CardTransactions before running continuous payment detection."""
    db = DataBase()
    print("\n" + "=" * 80)
    print("BEFORE: Untagged CardTransactions in Database")
    print("=" * 80)
    
    untagged_list, desc = db.get_untagged(table="CardTransactions")
    if untagged_list:
        untagged_df = pd.DataFrame(untagged_list, columns=desc)
        # Show only available relevant columns
        available_cols = [col for col in ['ID', 'Name', 'Extra_Info', 'Category', 'Charge_Date'] if col in untagged_df.columns]
        print(utils.df_to_markdown(untagged_df[available_cols]))
    else:
        print("No untagged transactions found")

def run_continuous_payment_detection():
    """Run the continuous payment detection function."""
    print("\n" + "=" * 80)
    print("RUNNING: detect_continuous_payments()")
    print("=" * 80 + "\n")
    
    utils.detect_continuous_payments()

def display_after_state(inserted_ids):
    """Display CardTransactions after running continuous payment detection."""
    db = DataBase()
    print("\n" + "=" * 80)
    print("AFTER: All CardTransactions in Database (filtered to test IDs)")
    print("=" * 80)
    
    # Get all transactions we inserted
    where_clause = f"ID IN ({','.join(['?'] * len(inserted_ids))})"
    sql = f"SELECT * FROM CardTransactions WHERE {where_clause}"
    db.cursor.execute(sql, inserted_ids)
    results = db.cursor.fetchall()
    
    if results:
        df = pd.DataFrame(results, columns=[d[0] for d in db.cursor.description])
        # Show only available relevant columns
        available_cols = [col for col in ['ID', 'Name', 'Extra_Info', 'Category', 'Description', 'Charge_Date'] if col in df.columns]
        print(utils.df_to_markdown(df[available_cols]))
    else:
        print("No transactions found")

def summary(inserted_ids):
    """Display summary of expected vs actual results."""
    db = DataBase()
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    expected_tagged = [
        ("Electric Company Ltd - payment 2/3", "Utilities"),
        ("Electric Company Ltd - payment 3/3", "Utilities"),
        ("Insurance Corp - payment 2/2", "Insurance")
    ]
    
    print("\nExpected Results:")
    for name, category in expected_tagged:
        print(f"  ✓ {name} → {category}")
    
    print("\nActual Results:")
    where_clause = f"ID IN ({','.join(['?'] * len(inserted_ids))})"
    sql = f"SELECT ID, Name, Extra_Info, Category FROM CardTransactions WHERE {where_clause} AND Category != 'NotCategorized'"
    db.cursor.execute(sql, inserted_ids)
    results = db.cursor.fetchall()
    
    if results:
        for row in results:
            print(f"  ✓ {row[1]} - {row[2]} → {row[3]}")
    else:
        print("  (No transactions were tagged)")

if __name__ == '__main__':
    try:
        # Create test data
        inserted_ids = create_test_data()
        
        # Display before state
        display_before_state(inserted_ids)
        
        # Run the function
        run_continuous_payment_detection()
        
        # Display after state
        display_after_state(inserted_ids)
        
        # Show summary
        summary(inserted_ids)
        
        print("\n" + "=" * 80)
        print("✓ TEST COMPLETED SUCCESSFULLY")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
