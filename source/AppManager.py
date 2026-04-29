from Parser import Parser
from Card import Card
from Bank import Bank
from Context import Context
from Constants import Local, Paths
from Constants import INVESTMENT_CATEGORY, GOLDEN_COLOR_PALLETE, GeneralPlot, Trans_Type
from src_utils.utils import utils
from database import DataBase
from front.Graphics import Graphics
from src_utils.calculations import SimpleMath
from src_utils.ExcelReader import ExcelManager
from src_utils.AppManagerUtils import AppManagerUtils
import webbrowser
from Configurations.Formats import Formats, Context_class
import pandas as pd
from os import listdir
import numpy as np
import seaborn as sns
from Exporter import Exporter

class AppManager:

    def __init__(self, skip_parser=False):
        res = utils.validate_formats()
        res2 = utils.validate_constants()

        result, log, df = utils.handle_withdrawals()
        if result:
            utils.log(f"{log}", 'system')
            if not df.empty:
                utils.log(f"Matched Withdrawals:\n{utils.df_to_markdown(df)}")
        else:
            utils.log(f"Withdrawals handling failed: {log}", 'error')

        if type(res2) == str:
            utils.log(res2, 'error')
        else:
            utils.log(f'Constants validation result: {res2}', 'system')

        if type(res) == str:
            utils.log(res, 'error')
        else:
            utils.log(f'Format validation result: {res}', 'system')

        if utils.validate_BankTransactions():
            utils.log("Bank Transactions validation passed!")
        else:
            utils.log("Bank Format Vlidation Failed!", 'warning')

        if not skip_parser:
            self.parser = Parser()

    def menu(self):
        while True:
            match utils.template_menu(options=['Update/Parse files',
                                             'Show statistics',
                                             'Delete file information',
                                             'Search transactions ',
                                             'Update existing file',
                                             'Execute SQL query on db',
                                             'Open File Organizer',
                                             'add cash transaction',
                                             'Export Excel',
                                             'Insert other account status',
                                             'Advanced Search',
                                             'Debug value mismatch'],
                                             msg='Hello Ofek! What would you like to do today?',
                                             exit=True,
                                             col_space=33):
            
                case 0:
                    return
                case 1:
                    self.load_data()
                    utils.tagger_refresh()
                    utils.detect_continuous_payments()
                    self.tag_data()
                case 2:
                    self.analysis()
                case 3:
                    self.delete_file_info()
                case 4:
                    self.search_transaction()
                case 5:
                    self.update_existing_file_v2()
                case 6:
                    self.execute_sql()
                case 7:
                    df, color_coded_df = utils.read_present_table()
                    utils.create_html_with_colored_dates(df, color_coded_df, output_file_path=Paths.ORGANIZER_TABLE_NAME)
                case 8:
                    self.add_cash_transaction()
                case 9:
                    self.exporter_function()
                case 10:
                    self.Insert_other_account_status()
                case 11:
                    self.advanced_search()
                case 12:
                    self.debug_value_mismatch()
                case _:
                    utils.log("Please insert a valid number.",'system')

    def add_cash_transaction(self):
        from Constants import Paths
        import json
        import os

        # 1. category and name
        category, name = utils.handle_categories()

        while category == "" or category == "「Back to menu」" or category == "「Skip」" or name == "":
            utils.log("Insert a valid input.", "system")
            category, name = utils.handle_categories()

        # 2. Amount
        while True:
            amount_str = input("Enter the amount (positive number): ")
            try:
                amount = float(amount_str)
                break
            except ValueError:
                utils.log("Invalid number format.", "warning")

        # 3. Currency
        currency_json_path = os.path.join(Paths.Currency_JSON, "currencies.json")
        if os.path.exists(currency_json_path):
            with open(currency_json_path, "r", encoding="utf-8") as f:
                currency_list = json.load(f)
        else:
            currency_list = [
                "JPY (¥)",
                "ILS (₪)",
                "Euro (€)"
            ]

        currency_options = currency_list + ["Add new currency"]
        currency_idx = utils.template_menu(currency_options, "Choose the currency:")
        if currency_idx == len(currency_options) - 1:
            new_currency = input("Enter new currency name: ")
            if new_currency and new_currency not in currency_list:
                currency_list.append(new_currency)
                with open(currency_json_path, "w", encoding="utf-8") as f:
                    json.dump(currency_list, f, ensure_ascii=False)
            currency = new_currency
        else:
            currency = currency_options[currency_idx]

        # 4. Date
        executed_date = utils.parse_date_from_user(return_type="datetime")

        review = f"""
            Name: {name}
            Amount: {amount} {currency}
            Category: {category}
            Date: {executed_date}"""
                    
        result = utils.template_menu(["Yes", "No"], f"This is a review of the information you entered:\n{review}\n, Insert?")
        if result == 1:
            utils.log("Insertion cancelled by user.", "system")
            return False
            
        # Save to DB
        from database import DataBase
        DataBase().insert_Cash_Transaction(name, 
                                           executed_date,
                                           amount,
                                           currency,
                                           category)

        DataBase().commit_changes()
        utils.log(f"Cash transaction added!", "system")
        return True

    def Insert_other_account_status(self) -> None:
        DataBase().create_other_account_table()

        while(True):
            res = utils.template_menu(["Insert new account status",
                                       "Delete account related entries",
                                       "Delete an account entry by id",
                                       "Exit"],
                                       "What would you like to do?")
            
            match res:
                case 0:
                    # Get account name (exclude read-only virtual accounts)
                    _READONLY_ACCOUNTS = ["נכס שלום שבזי"]
                    account_names = [a for a in DataBase().get_all_account_names()
                                     if a not in _READONLY_ACCOUNTS]
                    account_names.append("Add a new account")
                    
                    # Let user choose from list or add new
                    idx = utils.template_menu(account_names, "Choose an account Or add a new one:")
                    
                    if idx == len(account_names) - 1:
                        # User chose to add new account
                        account_name = input("Please insert the new account name: ")
                    else:
                        account_name = account_names[idx]
                    
                    # Get date
                    res = utils.template_menu(["Today", "Different date"],
                                              "Do you want to use today's date or a different date?\nPick an option:")
                    from datetime import datetime
                    if res == 0:
                        date = datetime.today().strftime("%Y-%m-%d")
                    else:
                        date = input("Please insert the date in the following format: YYYY-MM-DD: ")
                        while True:
                            try:
                                datetime.strptime(date, '%Y-%m-%d')
                                break
                            except ValueError:
                                date = input("Invalid date format. Please insert the date in YYYY-MM-DD format: ")
                    
                    # Get balance
                    utils.log("Please insert the current account Balance:")
                    value = int(input())
                    
                    # Insert new status (will create account if doesn't exist)
                    DataBase().insert_other_account_status(account_name, date, value, None)
                    DataBase().commit_changes()
                    utils.log(f"Account status added for {account_name}")
                    
                case 1:
                    # Get account names from database
                    account_names = DataBase().get_all_account_names()
                    
                    # Let user choose from list
                    idx = utils.template_menu(account_names, "Choose an account to delete:")
                    account_name = account_names[idx]
                    
                    DataBase().delete_account(account_name)
                    DataBase().commit_changes()
                case 2:
                    # Get all entries
                    utils.log("Current entries:\n")
                    entries = DataBase().get_account_entries()
                    for entry in entries:
                        utils.log(f"ID: {entry[0]}, Date: {entry[1]}, Value: {entry[2]}")
                    
                    entry_id = input("\nEnter the ID of the entry to delete: ")
                    try:
                        entry_id = int(entry_id)
                        if DataBase().delete_account_entry(entry_id):
                            utils.log(f"Successfully deleted entry {entry_id}")
                        else:
                            utils.log("Failed to delete entry")
                    except ValueError:
                        utils.log("Invalid ID entered")
                case 3:
                    break
                case _:
                    utils.log("Something went wrong in 'Insert_other_account_status'", "error")

    def exporter_function(self) -> None:

        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        # Get the first day of the current month
        first_day_current_month = datetime.today().replace(day=1)

        # Get the first day of the last month
        first_day_last_month = first_day_current_month - relativedelta(months=1)

        # Get the first day of the current year
        first_day_current_year = datetime.today().replace(month=1, day=1)
        
        first_day_last_year = first_day_current_year - relativedelta(years=1)

        exporter = Exporter()
        bank_df1, card_df1 = exporter.export_bank_transactions(since_d=first_day_current_month)
        bank_df2, card_df2 = exporter.export_bank_transactions(since_d=first_day_last_month)
        bank_df3, card_df3 = exporter.export_bank_transactions(since_d=first_day_current_year)
        bank_df4, card_df4 = exporter.export_bank_transactions(since_d=first_day_last_year)

        exporter.add_sheet(sheet_name='current month ' + first_day_current_month.strftime("%Y-%m-%d"), bank_df=bank_df1, card_df=card_df1)
        exporter.add_sheet(sheet_name='last month ' + first_day_last_month.strftime("%Y-%m-%d"), bank_df=bank_df2, card_df=card_df2)
        exporter.add_sheet(sheet_name='current year ' + first_day_current_year.strftime("%Y-%m-%d"), bank_df=bank_df3, card_df=card_df3)
        exporter.add_sheet(sheet_name='last year ' + first_day_last_year.strftime("%Y-%m-%d"), bank_df=bank_df4, card_df=card_df4)

    def search_transaction(self) -> None:
        """
        The function will ask the user for a substring and search for a transaction containing the substring.
        all transaction fitting will be printed
        """

        utils.log("Please insert a substring to search a transaction by, ENTER to go back.")
        
        input_str = " "
        
        while(True):
            input_str = input()
            if len(input_str) == 0:
                break
            df = DataBase().query_by_substring(input_str)
            utils.log(df.to_markdown())
        
    def advanced_search(self) -> None:
        """Interactive transaction search with multiple filters"""
        query_params = {}
        df = None

        while True:
            # If we have results, show them
            if df is not None:
                utils.log(f"\nFound {len(df)} transactions:")
                print(utils.df_to_markdown(df))
                
                if len(df) == 0:
                    # Reset search if no results found
                    query_params = {}
                    df = None
                    continue

            # Show search options
            options = [
                "Add date range filter",
                "Add name/description filter",
                "Add value range filter", 
                "Add table filter (Bank/Card)",
                "Add category filter",
                "Clear all filters",
                "Exit search"
            ]
            
            # Remove options that are already applied
            if 'date_range' in query_params:
                options.remove("Add date range filter")
            if 'name' in query_params:
                options.remove("Add name/description filter")
            if 'value_range' in query_params:
                options.remove("Add value range filter")
            if 'table' in query_params:
                options.remove("Add table filter (Bank/Card)")
            if 'category' in query_params:
                options.remove("Add category filter")

            choice = utils.template_menu(options, "\nSelect search filter to add:", col_space=40)

            match options[choice]:
                case "Add date range filter":
                    date_type = utils.template_menu(
                        ["Search by month", "Search by year"],
                        "Select date filter type:"
                    )
                    
                    if date_type == 0:  # Month
                        year = input("Enter year (YYYY): ")
                        month = input("Enter month (1-12): ")
                        try:
                            year = int(year)
                            month = int(month)
                            if 1 <= month <= 12:
                                from datetime import datetime, timedelta
                                start_date = datetime(year, month, 1).strftime('%Y-%m-%d')
                                end_date = (datetime(year, month + 1, 1) - timedelta(days=1)).strftime('%Y-%m-%d') \
                                    if month < 12 else datetime(year, 12, 31).strftime('%Y-%m-%d')
                                query_params['date_range'] = (start_date, end_date)
                            else:
                                utils.log("Invalid month", "warning")
                        except ValueError:
                            utils.log("Invalid date format", "warning")
                    
                    else:  # Year
                        year = input("Enter year (YYYY): ")
                        try:
                            year = int(year)
                            start_date = f"{year}-01-01"
                            end_date = f"{year}-12-31"
                            query_params['date_range'] = (start_date, end_date)
                        except ValueError:
                            utils.log("Invalid year format", "warning")

                case "Add name/description filter":
                    text = input("Enter text to search in name/description: ")
                    if text:
                        query_params['name'] = text

                case "Add value range filter":
                    try:
                        min_val = input("Enter minimum value (or press Enter to skip): ")
                        max_val = input("Enter maximum value (or press Enter to skip): ")
                        if min_val or max_val:
                            query_params['value_range'] = (
                                float(min_val) if min_val else None,
                                float(max_val) if max_val else None
                            )
                    except ValueError:
                        utils.log("Invalid number format", "warning")
                        continue

                case "Add table filter (Bank/Card)":
                    table_choice = utils.template_menu(
                        ["Bank Transactions", "Card Transactions"], 
                        "Select transaction type:"
                    )
                    query_params['table'] = "BankTransactions" if table_choice == 0 else "CardTransactions"

                case "Add category filter":
                    categories = DataBase().get_all_category_names()
                    cat_idx = utils.template_menu(categories, "Select category:")
                    query_params['category'] = categories[cat_idx]

                case "Clear all filters":
                    query_params = {}
                    df = None
                    continue

                case "Exit search":
                    return

            # Execute search with current parameters
            df = DataBase().search_transactions(query_params)

    def execute_sql(self):
        pw = input("Please confirm password for this action: ")
        if pw != "ofek":
            utils.log("Bad password", "system")
            return False

        def original_command():
            res = False
            while not res:
                query = input("Write your query:\n")
                res = DataBase().execute_query(query)
                if res:
                    break
                utils.log("Bad query, Try again...\nPlease Insert you query: ")
            ans = input("query is valid, Confirm? y/n\n")
            if ans == 'y':
                DataBase().commit_changes()
                return True
            else:
                utils.log("Changes not set...")

        res = utils.template_menu(['Write an original SQL command',
                                   'Reset a transaction category to "NotCategorized"',
                                   'Change transaction category by ID',
                                   'Change an existing category',
                                   'Delete a transaction',
                                   'Edit transaction description',
                                   'Fix Date Bug for cal',
                                   'Update all "Cal-Shufersal" formats to "Cal" in File table',
                                   'Exclude Transaction',
                                   'Delete a cash transaction entery by ID'
                                   'DateBase date fix'], 'Pick one of the following:', col_space=60)
        match res:
            case 0:
                original_command()
            case 1:
                DataBase().reset_category_by_id()
                DataBase().commit_changes()
            case 2:
                DataBase().change_category_by_id()
                DataBase().commit_changes()
            case 3:
                utils.change_an_existing_category_name()
            case 4:
                utils.delete_a_transaction()
            case 5:
                DataBase().change_description_by_id()
                DataBase().commit_changes()
            case 6:
                DataBase().fix_cal_date_bug()
                input("Continue?")
                DataBase().commit_changes()
            case 7:
                # New feature: Update all "Cal-Shufersal" formats to "Cal" in File table
                sql = "UPDATE File SET Format = 'Cal' WHERE Format = 'Cal-Shufersal';"
                DataBase().execute_query(sql)
                DataBase().commit_changes()
                utils.log('All "Cal-Shufersal" formats updated to "Cal" in File table.', 'system')
            case 8:
                utils.exclude_transaction()
            case 9:
                utils.delete_cash_transaction_by_id()
            case 10:
                utils.fix_database_dates()
            case _:
                utils.log('Something went wrong in "execute_sql"', 'error')

    def update_existing_file_v2(self):
        update_file_lst = listdir(Paths.UPDATE_FOLDER)
        if len(update_file_lst) == 0:
            utils.log(f"{Paths.UPDATE_FOLDER} is Empty. Returning to menu..", "system")
            return False

        new_file_id = utils.template_menu(update_file_lst,
                                          f"Choose a file to update from.")
        new_file_name = update_file_lst[new_file_id]

        files_df = DataBase().get_file_table()
        print(files_df.to_markdown())
        existing_file_id = utils.template_menu(list(files_df["File_Name"]),
                                               "Please choose what file do you want to update and delete.")
        existing_file_name = list(files_df['File_Name'])[existing_file_id]
        existing_file_format = list(files_df['Format'])[existing_file_id]
        existing_file_card = list(files_df['Card_Number'])[existing_file_id]

        ack = utils.template_menu(["Yes", "No"], f"The following process wil replace {existing_file_name} with {new_file_name}, Continue?")    
        if ack == 0:
            utils.log(f"Moving the new file: {new_file_name}, from the 'to_update' folder to the inputs folder...", 'system')
            utils.move_file_to_directory(file_path=f"{Paths.UPDATE_FOLDER}/{new_file_name}",
                                         destination_directory=Paths.INPUT_FOLDER)
            utils.log("Done." 'system')

            utils.log(f"Moving existing (old file) {existing_file_name}  file to 'removed' folder...", 'system')
            utils.move_file_to_directory(file_path=f"{Paths.VERIFIED_FOLDER}/{existing_file_format}/{existing_file_name}",
                                         destination_directory=f"removed")
            utils.log("Done." 'system')
            
            try:
                existing_data = DataBase().get_data_by_file_name(existing_file_name, existing_file_card)
                DataBase().drop_file(existing_file_name, existing_file_format, existing_file_card)

                self.parser = Parser.getInstance(newInstance=True)
                self.load_data()

                # becuase the file that is being updaed has to be pf the same defenition (format, card_id)
                # we can use the existing file card number here ->
                new_data = DataBase().get_data_by_file_name(new_file_name, existing_file_card)

                flag = True
                matched_t = 0
                for entry_ex in existing_data:
                    for entry_new in new_data:
                        if entry_ex[1:-1] == entry_new[1:-1]:    # equal
                            DataBase().set_category(entry_new[1], entry_new[0], entry_ex[-1])
                            matched_t += 1
                            flag = False
                            break
                    if flag:
                        res = utils.template_menu(['Abort update', 'Skip entry, its not important...'],
                                                  f'Did not found a correspinding entry for\n{entry_ex}\nin the new file.\n\
                                                  What would you like to do?')
                        match res:
                            case 0:
                                ExcelManager().close_and_kill_excel()
                                utils.log("Moving file back to update folder...", 'system')
                                utils.move_file_to_directory(file_path=f"{Paths.INPUT_FOLDER}/{new_file_name}",
                                                             destination_directory=Paths.UPDATE_FOLDER)
                                utils.log("Done." 'system')

                                utils.log("Moving file back to input folder...", 'system')
                                utils.move_file_to_directory(file_path=f"removed/{existing_file_name}",
                                                             destination_directory=Paths.INPUT_FOLDER)
                                utils.log("Done." 'system')

                                DataBase().drop_file(new_file_name, existing_file_format, existing_file_card)
                                self.parser = Parser.getInstance(newInstance=True)
                                self.load_data()

                            case 1:
                                pass
                            case _:
                                utils.log('internal error at file update', 'error')
                    flag = True

                utils.log(f'matched_transactions: {matched_t},\n\
                            transactions in existing file: {len(existing_data)}\n\
                            transactions in new file: {len(new_data)}', 'system')
            except Exception as e:
                utils.log(f"Procedure failed, Moving files back... The error:\n{e}", 'system')
                utils.log("Moving file back to update folder...", 'system')
                utils.move_file_to_directory(file_path=f"{Paths.INPUT_FOLDER}/{new_file_name}",
                                             destination_directory=Paths.UPDATE_FOLDER)
                utils.log("Done." 'system')

                utils.log("Moving file back to input folder...", 'system')
                removed_root = existing_file_name.split("\\")[-1]
                add_root = existing_file_name.split("\\")[0]
                utils.move_file_to_directory(file_path=f"removed/{removed_root}",
                                             destination_directory=f"{add_root}/{Paths.INPUT_FOLDER}")
                utils.log("Done." 'system')
                utils.log(f"{e}", 'system')

            DataBase().commit_changes()
            utils.log('Update process completed!', 'system')
            return True

    def delete_file_info(self):
        lst_names = DataBase().get_file_names()
        utils.log("Select the file you want to delete:")
        st = f"\n     {'File Name':30s}{'Format':22s}{'Card Number':17s}{'Last updated'}\n"
        for idx, name in enumerate(lst_names):
            st += f"{idx} -> {utils.heb_conversion(name[0]):30s}{name[1]:22s}{name[2]:17s}{name[3]}\n"
        utils.log(st, 'system')

        while True:
            answer = input()
            if not answer.isnumeric():
                utils.log("Bad input.. try again", "system")
                continue
            if not (int(answer) >= 0 and int(answer) < len(lst_names)):
                utils.log("Bad input.. try again", "system")
                continue
            answer = int(answer)
            break

        selected_file = lst_names[answer]
        DataBase().drop_file(selected_file[0], selected_file[1], selected_file[2])
        DataBase().commit_changes()

    def tag_data(self):
        """
        The function will check for untagged data and offer to tag it.
        """

        def make_readable(df: pd.DataFrame) -> pd.DataFrame:
            """Improve tables readability for printing purposes"""
            df['Name'] = df['Name'].apply(lambda x: utils.heb_conversion(x))
            df['Extra_Info'] = df['Extra_Info'].apply(lambda x: utils.heb_conversion(x))
            df['Source_file'] = df['Source_file'].apply(lambda x: utils.heb_conversion(x))
            return df

        def pretty_print_series(my_series: pd.Series) -> None:
            """
            Takes the original df created from the transactions and changes it for better
            readability. The function prints the result.
            """
            if my_series['Charge_Currency'] is not None:
                currency = my_series['Charge_Currency']
            else:
                currency = '₪'
            my_series = my_series.drop('Charge_Currency')
            
            my_series['Charge_Value/Out'] = str(my_series['Charge_Value/Out']) + f" {currency}"
            my_series['Transaction_Value/Income'] = str(my_series['Transaction_Value/Income']) + ' ₪'
            my_series['Executed_Date'] = my_series['Executed_Date'][:-9]
            print(f"\n{'-'*15} Tag the following {'-'*15}")
            if my_series['TableName'] == 'CardTransactions':
                my_series.index = ['Table Name',
                                    'Transaction ID',
                                    'Executed Date',
                                    'Name',
                                    'Card ID',
                                    'Charge Value',
                                    'Transaction Value',
                                    'More Info',
                                    'Source file name'] # type: ignore
            else:
                my_series.index = ['Table Name',
                                    'Transaction ID',
                                    'Executed Date',
                                    'Name',
                                    'Reference ID',
                                    'Outgoing',
                                    'Incoming',
                                    'More Info',
                                    'Source file name'] # type: ignore

            for index, value in my_series.items():
                print(f"{index:28s}{value}")
            print("\n")

        skip_list = []
        lst, desc = DataBase().get_untagged()
        df = pd.DataFrame(lst, columns=desc)
        df['Original_Name'] = df['Name']
        df = make_readable(df)

        utils.log(f"There are {len(lst)} untagged Transactions.\nChoose a category or create a new one.", "system")
        while not df.empty:
            for _, row in df.iterrows():

                # taggable items that are marked as "Skip", are added to the 'skip_list',
                # these items will be ignored until the next run
                if row['ID'] in skip_list:
                    continue
                pretty_print_series(row.drop('Original_Name'))
                res, description = utils.handle_categories()
                if res == "「Skip」":
                    skip_list.append(row['ID'])
                    utils.log("Skipped...", "system")
                    continue
                elif res == "「Back to menu」":
                    utils.log("Returning to menu...", "system")
                    return
                else:
                    # --------------- Auto Tagger function ---------------
                    if utils.auto_tagger(row['Original_Name']) != 'No Match':
                        if utils.template_menu(['no', 'yes'], f"Does all transactions with the name {row['Name']} belong to category {utils.heb_conversion(res)}?"):
                            tag_status_res = utils.auto_tagger(row['Original_Name'], res)
                        else:
                            tag_status_res = utils.auto_tagger(row['Original_Name'], 'No Match')
                    else:
                        tag_status_res = 'No Match'
                    # -----------------------------------------------------
                    DataBase().set_category(table_name=row['TableName'], id=row['ID'], category=res)
                    if len(description) > 1:
                        DataBase().set_transaction_description(description, row['TableName'], row['ID'])
                    utils.log("Tag saved.", "system")
                    DataBase().commit_changes()
                # ---------------- Fill in similar rows ----------------
                if tag_status_res != 'No Match':
                    res_df = DataBase().get_by_name_uncategorized(row['TableName'], row['Original_Name'])
                    if not res_df.empty:
                        if tag_status_res is None:
                            res_x = utils.template_menu(['Yes', 'No'],
                                                        "There are untagged transaction with the same name. Do you want apply to all?")
                        else:
                            res_x = 0
                        if res_x == 0:    # Yes -> 0
                            for _, row_x in res_df.iterrows():
                                DataBase().set_category(table_name=row['TableName'], id=row_x['ID'], category=res)
                            DataBase().commit_changes()
                            utils.log("Updated the following:\n")
                            res_df = make_readable(res_df)
                            print(res_df.to_markdown())
                            break   # In case latter transaction were updated, it is needed to read the table again
                                    # So information wont repeat for the user.
                # -------------------------------------------------------
            lst, desc = DataBase().get_untagged()
            df = pd.DataFrame(lst, columns=desc)
            df['Original_Name'] = df['Name']
            df = make_readable(df)

        utils.log("There is No data to tag, You are all good!", "system")

    def load_data(self):
        context = Context()
        Context.counter = 0
        while next(self.parser):
            file_name, format_name = self.parser.get_next()

            format_data = Formats.FORMATS[format_name]
            class_type = format_data["Context"]

            if class_type == Context_class.Bank:
                context.setFile(Bank(file_name, format_data))

            elif class_type == Context_class.Card:
                context.setFile(Card(file_name, format_data))

            else:
                utils.log("The file type is not supported", 'error')

            Context.counter += 1
            context.render()

    def analysis(self):
        match utils.template_menu(["General Statistics", "Pick a category/Bussines name"], "Pick an option:", exit=True):
            case 0:
                return
            case 1:
                self.general_analysis()
            case 2:
                self.category_analysis()
            case _:
                utils.log("Unreachable point reached...", "error")

    def category_analysis(self, category=None, business=None):

        name_for_analysis = ""
        category_for_analysis = ""

        if category is not None:
            case = 1
            category_for_analysis = category
        elif business is not None:
            case = 2
            name_for_analysis = business
        else:
            case = utils.template_menu(["Analyze a category", "Analayze a Business"], "Pick an option:", exit=True)
            match case:
                case 0:
                    return
                case 1:
                    options = utils.get_saved_categories()
                    idx, sub_options = utils.typer_template_menu(options, "Pick a Category:")
                    category_for_analysis = sub_options[idx]
                case 2:
                    options = DataBase().get_all_business_names()
                    idx, sub_options = utils.typer_template_menu(options, "Pick a Bussines:")
                    name_for_analysis = sub_options[idx]
                case _:
                    utils.log("Unreachable point reached...", "error")

        # Slug for web integration
        import re as _re_cat
        _raw_name = category_for_analysis if case == 1 else name_for_analysis
        _slug_name = _re_cat.sub(r'[^\w\u0590-\u05FF]', '_', _raw_name).strip('_')
        _slug = ('cat_' if case == 1 else 'biz_') + _slug_name

        def get_monthly_average(data: pd.DataFrame) -> float:
            """
            Returns category/business monthly average over all months
            all months is defined as the amount of months between the earliest month in the df to the current month.
            Calculates the average using the 'Final_Value' column in the dataframe
            
            arguments: 
            data: pd.DataFrame - the dataframe containing the transactions
            returns:
            float - the monthly average
            """

            from datetime import datetime
            #convert date string column to datetime
            data['Date'] = pd.to_datetime(data['Date'])
            sum = data['Final_Value'].sum()
            # calculate the amount of months between the earliest month in the df to the current month
            month_count = (datetime.now().year - data['Date'].min().year) * 12 + (datetime.now().month - data['Date'].min().month) + 1
            return round(sum / month_count, 2)
        
        def get_recent_monthly_average(data: pd.DataFrame, window_size: int=5):
            """
            Returns category/business monthly average over the last @window_size months
            Calculates the average using the 'Final_Value' column in the dataframe
            
            arguments:
                data: pd.DataFrame - the dataframe containing the transactions
                window_size: int - the number of months to consider for the average
            returns:
                float - the recent monthly average

            """
            from dateutil.relativedelta import relativedelta
            from datetime import datetime

            # Convert dates and filter last 5 months
            # Use midnight so transactions on the 1st of the current month are excluded
            current_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            x_months_ago = current_date - relativedelta(months=window_size)
            
            data['Date'] = pd.to_datetime(data['Date'])
            mask = (data['Date'] >= x_months_ago) & (data['Date'] < current_date)
            data = data[mask]
            
            return round(data['Final_Value'].sum() / window_size, 2)

        def get_monthly_active_stats(data: pd.DataFrame) -> tuple[float, float]:
            """
            return the active monthly average and standard deviation of the given data frame.
            Active monthly average is defined as the average of all months that had at least one transaction
            arguments:
                data: pd.DataFrame - the dataframe containing the transactions
            returns:
                float - the active monthly average
                float - the active monthly standard deviation
            """
            data['Date'] = pd.to_datetime(data['Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y-%m'))
            data = data.groupby('Date').sum(numeric_only=True)
            return data['Final_Value'].mean() , data['Final_Value'].std()        
       
        def yearly_average(data: pd.DataFrame) -> tuple[float, float]:
            """
            return the active yearly average and standard deviation of the given data frame.
            Active yearly average is defined as the average of all years that had at least one transaction
            arguments:
                data: pd.DataFrame - the dataframe containing the transactions
            returns:
                float - the active yearly average
                float - the active yearly standard deviation
            """
            data['Date'] = pd.to_datetime(data['Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y'))
            data = data.groupby('Date').sum(numeric_only=True)
            return data['Final_Value'].mean() , data['Final_Value'].std()                
        
        def total_spendings(data: pd.DataFrame) -> float:
            """
            Returns  total spendings
            """
            return data['Final_Value'][data['Final_Value'] < 0].sum()

        def total_income(data: pd.DataFrame) -> float:
            """
            Returns total income
            """
            return data['Final_Value'][data['Final_Value'] > 0].sum()

        def get_associated(data: pd.DataFrame, case: int) -> list[str]:
            """
            return all associated business/category names with the given category/business of @data df
            arguments:
                data: pd.DataFrame - the dataframe containing the transactions
                case: int - 1 for category analysis, 2 for business analysis
            returns:
                list[str] - list of associated names
            """

            if case == 1:
                data = data[['Name','Final_Value','Category']].groupby('Name').sum()
            elif case == 2:
                data = data[['Name','Final_Value','Category']].groupby('Category').sum()
            else:
                utils.log("Unreachable point reached...", "error")
            
            return Graphics.plot_pie_distribution(data)
        
        # -------------------------- Plot general graph --------------------------
        if case == 2:
            spendings_sum, spendings_sum_overall_inc, earnings_sum = SimpleMath.get_monthly_shifted(shift=6, category=None, business=name_for_analysis)
        elif case == 1:
            spendings_sum, spendings_sum_overall_inc, earnings_sum = SimpleMath.get_monthly_shifted(shift=6, category=category_for_analysis, business=None)
        else:
            utils.log("Unreachable point reached...", "error")

        Graphics.plot_general(spendings_sum, spendings_sum_overall_inc, earnings_sum, title_ext='Category_analysis', topic = name_for_analysis, fig_size=(8, 5))
        # --------------------------

        # Monthly chart data for Chart.js
        from datetime import datetime as _cat_dt
        from dateutil.relativedelta import relativedelta as _cat_rd
        _shift = 6
        _now = _cat_dt.now()
        _month_labels = [(_now - _cat_rd(months=i)).strftime('%m/%Y') for i in range(_shift)]
        monthly_chart_data = [
            {'month': _month_labels[i], 'spending': round(abs(float(spendings_sum[i])), 2), 'income': round(float(earnings_sum[i]), 2)}
            for i in range(_shift - 1, -1, -1)
        ]

        # Fetch all transactions (no category pre-filter) so that apply_splits_to_df()
        # can correctly replace split-originals with their split children before we
        # filter by category.  Without this, a split transaction would still appear
        # under its original category and its splits would be invisible.
        _db_inst = DataBase()
        _name_f  = name_for_analysis  if name_for_analysis  else None

        _bank_raw = _db_inst.get_transactions('BankTransactions', category_filter=None, name_filter=_name_f)
        _bank_raw = _db_inst.apply_splits_to_df(_bank_raw)
        if category_for_analysis:
            _bank_raw = _bank_raw[_bank_raw['Category'] == category_for_analysis].reset_index(drop=True)

        _card_raw = _db_inst.get_transactions('CardTransactions', category_filter=None, name_filter=_name_f)
        _card_raw = _db_inst.apply_splits_to_df(_card_raw)
        if category_for_analysis:
            _card_raw = _card_raw[_card_raw['Category'] == category_for_analysis].reset_index(drop=True)

        df_bank_transactions = SimpleMath.process_prices(_bank_raw, general_analysis=False)
        df_card_transactions = SimpleMath.process_prices(_card_raw, general_analysis=False)
        

        if df_card_transactions.empty:
            utils.log("No card transactions found for the selected month.", "warning")
        else:
            df_card_transactions=df_card_transactions[['ID',
                                                        'TableName', 
                                                        'CardID',
                                                        'Name',
                                                        'Executed_Date',
                                                        'Charge_Date',
                                                        'Charge_Value',
                                                        'Charge_Currency',
                                                        'Value_Currency',
                                                        'Final_Value',
                                                        'Category',
                                                        'Extra_Info',
                                                        'Description',
                                                        'Transaction_Type']]
            
        proceessed_card_transactions_df = df_card_transactions.rename(columns={'Executed_Date': 'Date'})

        if df_bank_transactions.empty:
            utils.log("No bank transactions found for the selected month.", "warning")
        else:
            df_bank_transactions=df_bank_transactions[['ID',
                                                        'TableName', 
                                                        'Name',
                                                        'Date', 
                                                        'Final_Value',
                                                        'Category',
                                                        'Extra_Info',
                                                        'Description',
                                                        'Transaction_Type']]
        
        data = pd.concat([df_bank_transactions, proceessed_card_transactions_df], ignore_index=True)

        analisys_data = data.copy()
        active_average, active_sd = get_monthly_active_stats(analisys_data.copy())

        # Pie chart data for Chart.js — separate spending and earning pies
        _group_col = 'Name' if case == 1 else 'Category'

        def _build_pie(df, top_n=8):
            if df.empty: return []
            grouped = (df.assign(Final_Value=df['Final_Value'].abs())
                         .groupby(_group_col)['Final_Value'].sum()
                         .sort_values(ascending=False))
            items = [{'name': str(n), 'value': round(float(v), 2)}
                     for n, v in grouped.items() if v > 0]
            if len(items) > top_n:
                _others = sum(x['value'] for x in items[top_n:])
                items = items[:top_n]
                if _others > 0:
                    items.append({'name': 'אחר', 'value': round(_others, 2)})
            return items

        _df_spend = analisys_data[analisys_data['Final_Value'] < 0][[_group_col, 'Final_Value']].copy()
        _df_earn  = analisys_data[analisys_data['Final_Value'] > 0][[_group_col, 'Final_Value']].copy()
        spending_pie_data = _build_pie(_df_spend)
        earning_pie_data  = _build_pie(_df_earn)

        utils.create_html_name_analysis({"subtitle": "Specific Analysis",
                                         "Category/business name": category_for_analysis if case == 1 else name_for_analysis,
                                         "type": "category" if case == 1 else "business",
                                         "slug": _slug,
                                         "Monthly Average": get_monthly_average(analisys_data.copy()),
                                         "Recent Monthly Average": get_recent_monthly_average(analisys_data.copy(), window_size=5),
                                         "Monthly Active Average": active_average,
                                         "Monthly Active Standard Deviation": active_sd,
                                         "Yearly Average": yearly_average(analisys_data.copy())[0],
                                         "Total Spendings": total_spendings(analisys_data.copy()),
                                         "Total Income": total_income(analisys_data.copy()),
                                         "monthly_chart_data": monthly_chart_data,
                                         "spending_pie_data": spending_pie_data,
                                         "earning_pie_data":  earning_pie_data,
                                         "transactions": analisys_data})
        if category is None and business is None:
            webbrowser.open(r'source\html\Category_output.html')

    def general_analysis(self, t=None):
        from datetime import datetime
        if t is None:
            # -----
            match utils.template_menu(["Current Month",
                                    "Last Month",
                                    "Pick A date"],
                                    "General Analisys: Choose one of the following options:",
                                    exit=True):

                case 0:
                    return
                case 1:
                    t = datetime.now()
                case 2:
                    from dateutil.relativedelta import relativedelta
                    t = datetime.now() - relativedelta(months=1)
                case 3:
                    t = utils.parse_date_from_user(day=False, return_type="datetime")
                case _:
                    utils.log("Unreachable point reached...", "error")

        data = {}
        
        # Add linear plots data
        def get_accounts_data() -> tuple:
            """Get historical balance data for all accounts.
            Returns (accounts_data_ils, accounts_raw_meta) where:
              - accounts_data_ils: {account: [(date, ils_value), ...]} — all values in ILS
              - accounts_raw_meta: {account: {last_currency, last_raw_value, currencies, rate, rate_cur}}
            """
            accounts_data = {}
            accounts_raw_meta = {}

            # Get main bank account data (always ILS)
            bank_df = DataBase().get_monthly_bank_balances()
            accounts_data['Main Bank'] = list(zip(bank_df['Date'], bank_df['Balance']))
            _bank_last = float(bank_df['Balance'].iloc[-1]) if len(bank_df) > 0 else 0.0
            accounts_raw_meta['Main Bank'] = {
                'last_currency': 'ILS', 'last_raw_value': _bank_last,
                'currencies': {'ILS'}, 'rate': None, 'rate_cur': None,
            }

            # Fetch FX rates once for currency conversion (non-ILS → ILS)
            import urllib.request as _ureq, json as _json_fx
            try:
                with _ureq.urlopen('https://api.exchangerate-api.com/v4/latest/ILS', timeout=5) as _r:
                    _ils_data = _json_fx.loads(_r.read())
                _ils_to_x = _ils_data.get('rates', {})
                _fx_to_ils = {c: 1.0 / r for c, r in _ils_to_x.items() if r}
                _fx_to_ils['ILS'] = 1.0
            except Exception:
                _fx_to_ils = {'ILS': 1.0, 'USD': 3.72, 'EUR': 4.01, 'JPY': 0.025}

            # Get other accounts data (values stored in original currency, convert to ILS)
            other_accounts_df = DataBase().get_account_entries_with_dates()
            for account in other_accounts_df['AccountName'].unique():
                account_df = other_accounts_df[other_accounts_df['AccountName'] == account].sort_values('Date')
                # Build ILS-converted history (for totals / charts)
                entries = []
                for _, row in account_df.iterrows():
                    val = float(row['Value'])
                    cur = (str(row.get('Currency', 'ILS') or 'ILS')).strip().upper()
                    if cur != 'ILS':
                        val = val * _fx_to_ils.get(cur, 1.0)
                    entries.append((row['Date'], val))
                accounts_data[account] = entries

                # Build raw metadata for display
                last_row = account_df.iloc[-1]
                last_cur  = (str(last_row.get('Currency', 'ILS') or 'ILS')).strip().upper()
                last_val  = float(last_row['Value'])
                all_curs  = {
                    (str(c) or 'ILS').strip().upper()
                    for c in account_df['Currency'] if c and str(c).strip()
                } or {'ILS'}
                non_ils = all_curs - {'ILS'}
                rate, rate_cur = None, None
                if len(all_curs) == 2 and non_ils:
                    rate_cur = next(iter(non_ils))
                    rate = _fx_to_ils.get(rate_cur)
                accounts_raw_meta[account] = {
                    'last_currency':  last_cur,
                    'last_raw_value': last_val,
                    'currencies':     all_curs,
                    'rate':           rate,
                    'rate_cur':       rate_cur,
                }

            # Calculate total sum across all accounts (ILS)
            all_dates = sorted(set(date for data in accounts_data.values() for date, _ in data))
            total_sums = []
            for date in all_dates:
                total = 0
                for data in accounts_data.values():
                    # Find the closest previous date's value
                    valid_entries = [(d, v) for d, v in data if d <= date]
                    if valid_entries:
                        total += max(valid_entries, key=lambda x: x[0])[1]
                total_sums.append((date, total))

            accounts_data['Total'] = total_sums

            return accounts_data, accounts_raw_meta

        # Get accounts data — הון עצמי will be added after mortgage section
        utils.log("Generating linear plots for all accounts...", "system")
        accounts_data, accounts_raw_meta = get_accounts_data()
        # NOTE: plot_linear_plots_graph is called later, after הון עצמי is added
        
        transactions_df = AppManagerUtils.retrieve_and_initialize_data(t)

        # ---- Card validation data ----
    
        card_validation_df = utils.card_charge_validation(transactions_df, t)
        utils.log(card_validation_df.to_markdown(), "debug")

        # --------------------------- Cash Flow ---------------------------
        utils.log("generating cash flow data...", "system")

        # Monthly cash transactions df
        mct_df = utils.get_cash_transactions(t)
        Graphics.plot_monthly_cash_distribution(mct_df)

        cash_information_data = {
            "Monthly Earned Cash": 0.0 if mct_df.empty else mct_df[mct_df['Amount'] > 0]['Amount'].sum(),
            "Monthly Spent Cash": 0.0 if mct_df.empty else mct_df[mct_df['Amount'] < 0]['Amount'].sum(),
            "Monthly Cash Transactions": mct_df,
            "Accumulative Cash Balance": utils.accumulate_cash_Balance()
        }

        try:
            _cash_history = utils.cash_monthly_history()
        except Exception as _ce:
            utils.log(f"cash_monthly_history failed: {_ce}", "warning")
            _cash_history = []
        accounts_data['Cash'] = _cash_history if _cash_history else [
            (datetime.now(), cash_information_data["Accumulative Cash Balance"])
        ]

        
        def handle_spendings_pie_plot():
            color_pallete = sns.light_palette("#f66b85", n_colors=10, reverse=True)
            cash_flow_row = {"Name": "מזומן", "Category": "מזומן", "Description/Charge_Currency": None , "Final_Value": cash_information_data['Monthly Spent Cash']}
            temp_df = transactions_df[(transactions_df['Final_Value'] < 0)]
            temp_df = pd.concat([temp_df, pd.DataFrame([cash_flow_row])], ignore_index=True)

            return Graphics.plot_transactions_pie_chart(temp_df.groupby("Category").sum(numeric_only=True), 
                                                                    "Spendings", 
                                                                    color_pallete)

        utils.log("Generating spending pie charts...", "system")
        high_std_spendings = handle_spendings_pie_plot()

        # Capture spendings data for interactive chart (exclude investments — shown in their own donut)
        _sp_df = transactions_df[(transactions_df['Final_Value'] < 0) & (transactions_df['Category'] != INVESTMENT_CATEGORY)].copy()
        _sp_cash = {"Name": "מזומן", "Category": "מזומן", "Final_Value": cash_information_data['Monthly Spent Cash']}
        _sp_df = pd.concat([_sp_df, pd.DataFrame([_sp_cash])], ignore_index=True)
        _sp_grouped = _sp_df.groupby("Category")['Final_Value'].sum().abs()
        data['spendings_by_cat'] = {str(k): round(float(v), 2) for k, v in _sp_grouped.items() if v > 0}

        def handle_earnings_pie_plot():
            color_pallete = sns.light_palette("#4fba89", n_colors=10, reverse=True)

            cash_flow_row = {"Name": "מזומן", "Category": "מזומן", "Final_Value": cash_information_data['Monthly Earned Cash']}
            temp_df = transactions_df[(transactions_df['Final_Value'] > 0)]
            temp_df = pd.concat([temp_df, pd.DataFrame([cash_flow_row])], ignore_index=True)

            return Graphics.plot_transactions_pie_chart(temp_df.groupby("Category").sum(numeric_only=True),
                                                        "Earnings",
                                                        color_pallete)

        utils.log("Generating earnings pie charts...", "system")
        high_std_earnings = handle_earnings_pie_plot()

        # Capture earnings data for interactive chart
        _ea_df = transactions_df[transactions_df['Final_Value'] > 0].copy()
        _ea_cash = {"Name": "מזומן", "Category": "מזומן", "Final_Value": cash_information_data['Monthly Earned Cash']}
        _ea_df = pd.concat([_ea_df, pd.DataFrame([_ea_cash])], ignore_index=True)
        _ea_grouped = _ea_df.groupby("Category")['Final_Value'].sum()
        data['earnings_by_cat'] = {str(k): round(float(v), 2) for k, v in _ea_grouped.items() if v > 0}

        def handle_investments_pie_plot():
            color_pallete = GOLDEN_COLOR_PALLETE
            temp_df = transactions_df[(transactions_df["Category"] == INVESTMENT_CATEGORY)]
            Graphics.plot_transactions_pie_chart(temp_df,
                                                "Investments",
                                                color_pallete)

        utils.log("Generating investments pie charts...", "system")
        handle_investments_pie_plot()

        # Capture investments data for interactive chart
        _inv_df = transactions_df[transactions_df["Category"] == INVESTMENT_CATEGORY].copy()
        if not _inv_df.empty:
            _inv_df['_label'] = _inv_df.apply(
                lambda r: str(r['Description/Charge_Currency'] if pd.notna(r.get('Description/Charge_Currency')) else r['Name']),
                axis=1
            )
            _inv_grouped = _inv_df.groupby('_label')['Final_Value'].sum().abs()
            data['investments_by_name'] = {str(k): round(float(v), 2) for k, v in _inv_grouped.items() if v > 0}
        else:
            data['investments_by_name'] = {}

        # ----- General
        utils.log("Generating general bar plot...", "system")
        spendings_sum, spendings_sum_overall_inc, earnings_sum = SimpleMath.get_monthly_shifted(shift=10)

        Graphics.plot_general(spendings_sum,
                              spendings_sum_overall_inc,
                              earnings_sum,
                              lp_Overall_income=True,
                              lp_user_defined=False)

        # Capture general chart data for interactive chart
        from Constants import GENERAL_PLOT as _GP
        _gen_delta = 0 if _GP.SHOW_CURRENT_MONTH else 1
        data['general_months'] = [
            (datetime.now() - pd.DateOffset(months=i + _gen_delta)).strftime('%b %Y')
            for i in range(10)
        ]
        # Split spendings into pure-spend (no investments) and investments portion
        data['general_spendings']    = [round(float(abs(v)), 2) for v in spendings_sum_overall_inc]
        data['general_investments']  = [round(float(abs(s) - abs(n)), 2)
                                        for s, n in zip(spendings_sum, spendings_sum_overall_inc)]
        data['general_earnings']     = [round(float(v), 2) for v in earnings_sum]
        data['general_net']          = [round(float(e + s), 2) for e, s in zip(earnings_sum, spendings_sum_overall_inc)]

        # ----- User defined
        utils.log("Generating user defined bar plot...", "system")
        user_spendings_sum, _, user_earnings_sum = SimpleMath.get_monthly_shifted(shift=10, category= GeneralPlot.USER_DEFINED_CATEGORIES)

        Graphics.plot_general(user_spendings_sum,
                              spendings_sum_overall_inc,
                              user_earnings_sum,
                              lp_Overall_income=False,
                              lp_user_defined=True,
                              title_ext='User_defined',
                              user_spendings_sum = user_spendings_sum,
                              user_earnings_sum = user_earnings_sum)
        # ----- Cards
        utils.log("Generating card distribution plot...", "system")
        card_ids = DataBase().get_card_ids() + ['Bank']
        color_list = Local.Colors[:len(card_ids)]
        card_color_dict = dict(zip(card_ids, color_list))
        #for cash transactions color
        card_color_dict['Cash'] = "#ECCD1F"

        Graphics.card_distribution(card_color_dict, card_validation_df)

        # Capture card distribution data for interactive chart
        if not card_validation_df.empty:
            data['card_dist'] = {
                str(row['CardID']): {
                    'amount':  round(float(abs(row['Final_Value'])), 2),
                    'status':  bool(row['Status']),
                    'color':   card_color_dict.get(str(row['CardID']), '#b0bec5'),
                }
                for _, row in card_validation_df.iterrows()
            }
        else:
            data['card_dist'] = {}

        # ----- Payment PIE Graphs
        utils.log("Generating Payments data...", "system")
        payment_filtered_df = transactions_df[transactions_df['Transaction_Type'] == Trans_Type.payment]
        payments_df = utils.extract_payments_data(payment_filtered_df)
        Graphics.generate_payment_pie_graphs(payments_df)


        # ---------------- General calculations ----------------
        # monthly_cash_balance = cash_information_data['Monthly Earned Cash'] + \
        #                         cash_information_data['Monthly Spent Cash']
        
        total_monthly_income = transactions_df[(transactions_df['Final_Value'] > 0)]['Final_Value'].sum()
        total_monthly_outcome = transactions_df[(transactions_df['Final_Value'] < 0)]['Final_Value'].sum()
        total_monthly_outcome_no_invest = transactions_df[(transactions_df['Final_Value'] < 0) & 
                                                          ((transactions_df["Category"] != INVESTMENT_CATEGORY))]['Final_Value'].sum()
        data['net income'] = (total_monthly_income + total_monthly_outcome) 

        data['overall net income'] = (total_monthly_income + \
                                      total_monthly_outcome_no_invest)
        data['overall_net_mean'] = (np.array(earnings_sum) + np.array(spendings_sum_overall_inc)).mean()
        
        spendings_df = transactions_df[transactions_df['Final_Value'] < 0]
        spendings_df['Final_Value'] = spendings_df['Final_Value'].apply(lambda x: abs(x))

        earnings_df = transactions_df[transactions_df['Final_Value'] > 0]   
        monthly_balance = DataBase().get_latest_Balance()

        # ---- Smart Alerts ----
        # Collect the last 6 months of processed transaction DataFrames to
        # give the alert detector enough history for comparison.
        # We reuse the same query+process pipeline as get_monthly_shifted().
        utils.log("Running smart alert detection...", "system")
        try:
            from Analysis.SmartAlerts import AlertDetector
            from Configurations.AlertsConfig import ALERTS_CONFIG

            history_dfs = []
            for i in range(1, 7):   # 1 month ago → 6 months ago
                hist_date = t - pd.DateOffset(months=i)
                hist_raw  = DataBase().query_monthly_transactions(
                    date=hist_date, tables=["BankTransactions", "CardTransactions"]
                )
                history_dfs.append(SimpleMath.process_prices(hist_raw, date=hist_date))

            alerts = AlertDetector(
                current_df  = transactions_df,
                history_dfs = history_dfs,
                config      = ALERTS_CONFIG,
            ).detect_all()

            utils.log(f"Smart alerts: {len(alerts)} alert(s) generated", "system")

        except Exception as exc:
            # Alert detection must never crash the main analysis flow
            utils.log(f"Smart alert detection failed (non-critical): {exc}", "warning")
            alerts = []

        # ---- Mortgage analysis ----
        utils.log("Generating mortgage analysis...", "system")
        from src_utils.mortgage import (
            full_schedule, months_elapsed_and_balance, milestone_schedule,
            actual_payments, actual_rental_income, current_month_data,
            alltime_category_data,
            TOTAL_MONTHLY_PAYMENT, RENTAL_INCOME_PM,
            APARTMENT_PRICE, MORTGAGE_AMOUNT, DOWN_PAYMENT, MORTGAGE_CATEGORY,
            FIRST_PAYMENT, INITIAL_APARTMENT_PAYMENT,
        )
        _mort_totals, _mort_per_track = full_schedule()
        _today_date  = t.date() if hasattr(t, "date") else datetime.now().date()
        _n_months, _cur_balance = months_elapsed_and_balance(_mort_totals, _today_date)
        _actual_pays   = actual_payments()         # mortgage payments per month (DB)
        _actual_rental = actual_rental_income()    # rental income per month (DB)
        _this_month    = current_month_data(t.year, t.month)  # this month's actuals
        _alltime       = alltime_category_data()   # all-time totals for the category
        # Build Chart.js-ready data (replaces slow matplotlib PNG generation)
        _step = 3   # sample every 3 months → ~120 points for 30-year schedule
        _chart_months = [str(d)[:7] for d in _mort_totals['month'].iloc[::_step]]
        _chart_bal_total = [round(float(v)) for v in _mort_totals['total_balance'].iloc[::_step]]
        _chart_interest  = [round(float(v), 2) for v in _mort_totals['total_interest'].iloc[::_step]]
        _chart_principal = [round(float(v), 2) for v in _mort_totals['total_principal'].iloc[::_step]]
        _chart_tracks = {}
        for _tn, _tg in _mort_per_track.groupby("track"):
            _tg_r = _tg.reset_index(drop=True)
            _chart_tracks[str(_tn)] = {
                "balance":    [round(float(v)) for v in _tg_r['balance'].iloc[::_step]],
                "track_type": str(_tg_r["track_type"].iloc[0]),
            }
        # Cashflow: build month list from first payment to today+6 months
        from dateutil.relativedelta import relativedelta as _rdelta
        _cf_d = FIRST_PAYMENT.replace(day=1)
        _cf_end = _today_date + _rdelta(months=6)
        _cf_months, _cf_payments, _cf_rentals = [], [], []
        _pay_map  = {} if _actual_pays.empty  else {str(d)[:7]: v for d, v in zip(_actual_pays['month'],  _actual_pays['total_paid'])}
        _rent_map = {} if _actual_rental.empty else {str(d)[:7]: v for d, v in zip(_actual_rental['month'], _actual_rental['total_income'])}
        while _cf_d <= _cf_end:
            _m = str(_cf_d)[:7]
            _cf_months.append(_m)
            _cf_payments.append(round(float(_pay_map.get(_m, TOTAL_MONTHLY_PAYMENT)), 2))
            _cf_rentals.append(round(float(_rent_map.get(_m, RENTAL_INCOME_PM)), 2))
            _cf_d = (_cf_d + _rdelta(months=1)).replace(day=1)

        _housing_txns = DataBase().get_all_category_transactions(MORTGAGE_CATEGORY)
        # 5% annual appreciation on apartment value (default; user can adjust in UI)
        _DEFAULT_RATE        = 5.0
        _years_elapsed       = _n_months / 12
        _appreciated_price   = round(APARTMENT_PRICE * ((1 + _DEFAULT_RATE/100) ** _years_elapsed))
        _equity_base         = round(APARTMENT_PRICE  - _cur_balance)
        _equity_appreciated  = round(_appreciated_price - _cur_balance)
        _monthly_appreciation = round(_appreciated_price * (((1 + _DEFAULT_RATE/100) ** (1/12)) - 1))
        _alltime_mortgage = float(_actual_pays["total_paid"].sum()) if not _actual_pays.empty else 0.0

        # ── Build הון עצמי timeline (yearly samples, history + projection) ────
        _EQUITY_ACCOUNT = "נכס שלום שבזי"
        _rate_monthly   = (1 + _DEFAULT_RATE / 100) ** (1 / 12) - 1
        _eq_history = []   # (date, equity) up to today — monthly points

        for _, _mrow in _mort_totals.iterrows():
            _m = _mrow["month"]
            _m_date = _m.date() if hasattr(_m, "date") else _m
            if _m_date > _today_date:
                break   # history only — no future points
            _months_from_start = max(0, round((_m_date - FIRST_PAYMENT).days / 30.4375))
            _apt_val  = APARTMENT_PRICE * (1 + _rate_monthly) ** _months_from_start
            _equity   = round(_apt_val - _mrow["total_balance"] + _alltime["alltime_income"])
            _eq_history.append((_m_date, _equity))

        # Always pin the current point to the exact דיור panel value
        _equity_now = _equity_appreciated + _alltime["alltime_income"]
        if _eq_history:
            _eq_history[-1] = (_today_date, _equity_now)   # override last point with exact value
        else:
            _eq_history = [(_today_date, _equity_now)]
        accounts_data[_EQUITY_ACCOUNT] = _eq_history

        # Recompute Total now that נכס שלום שבזי is included
        def _recompute_total(data: dict) -> list:
            def _to_date(d):
                return d.date() if hasattr(d, 'date') and callable(d.date) else d

            _dates = sorted(set(
                _to_date(d) for k, v in data.items() if k != 'Total' for d, _ in v
            ))
            _sums = []
            for _d in _dates:
                _t = sum(
                    max(
                        ((_to_date(dt), val) for dt, val in v if _to_date(dt) <= _d),
                        key=lambda x: x[0],
                        default=(None, 0)
                    )[1]
                    for k, v in data.items() if k != 'Total' and v
                )
                _sums.append((_d, _t))
            return _sums

        accounts_data['Total'] = _recompute_total(accounts_data)

        # Sale return: net_invested = everything spent; profit includes rent received
        _net_invested        = _alltime["alltime_out"]
        _sale_profit         = _equity_appreciated + _alltime["alltime_income"] - _net_invested
        _total_return_pct    = round(_sale_profit / _net_invested * 100, 1) if _net_invested > 0 else 0
        _annual_return_pct   = round(((1 + _total_return_pct/100) ** (12 / max(_n_months, 1)) - 1) * 100, 1)

        mortgage_data = {
            "apartment_price":        APARTMENT_PRICE,
            "apartment_appreciated":  _appreciated_price,
            "equity":                 _equity_base,
            "equity_appreciated":     _equity_appreciated,
            "monthly_appreciation":   _monthly_appreciation,
            "years_elapsed":          round(_years_elapsed, 1),
            "mortgage_amount":        MORTGAGE_AMOUNT,
            "down_payment":           DOWN_PAYMENT,
            "current_balance":        _cur_balance,
            # This-month actuals (fall back to projected if not yet in DB)
            "payment_found":          bool(_this_month["payment"]),
            "total_monthly_payment":  _this_month["payment"] if _this_month["payment"] else TOTAL_MONTHLY_PAYMENT,
            "rental_income":          _this_month["rental"]  if _this_month["rental"]  else RENTAL_INCOME_PM,
            "net_monthly_cost":       _this_month["net"] if _this_month["rent_found"]
                                      else round((_this_month["payment"] if _this_month["payment"] else TOTAL_MONTHLY_PAYMENT) - RENTAL_INCOME_PM, 2),
            "rent_found":             _this_month["rent_found"],
            "month_out":              _this_month["month_out"],
            "month_income":           _this_month["month_income"],
            "alltime_out":            _alltime["alltime_out"],
            "alltime_income":         _alltime["alltime_income"],
            "alltime_net":            _alltime["alltime_net"],
            "months_elapsed":         _n_months,
            "default_rate":           _DEFAULT_RATE,
            "net_invested":           round(_net_invested, 2),
            "total_return_pct":       _total_return_pct,
            "annual_return_pct":      _annual_return_pct,
            "initial_apartment_payment": INITIAL_APARTMENT_PAYMENT,
            "alltime_mortgage_payments": round(_alltime_mortgage, 2),
            "milestones":            milestone_schedule(_mort_totals),
            "mortgage_category":     MORTGAGE_CATEGORY,
            "housing_transactions":  _housing_txns,
            "first_payment_date":    FIRST_PAYMENT.strftime('%Y-%m-%d'),
            # Chart.js data (replaces matplotlib PNGs)
            "chart_balance":   {
                "months": _chart_months,
                "total":  _chart_bal_total,
                "tracks": _chart_tracks,
                "today":  str(_today_date)[:7],
            },
            "chart_breakdown": {
                "months":    _chart_months,
                "interest":  _chart_interest,
                "principal": _chart_principal,
            },
            "chart_cashflow":  {
                "months":   _cf_months,
                "payments": _cf_payments,
                "rentals":  _cf_rentals,
                "today":    str(_today_date)[:7],
                "projected_payment": round(float(TOTAL_MONTHLY_PAYMENT), 2),
                "projected_rental":  round(float(RENTAL_INCOME_PM), 2),
            },
        }

        # Accounts chart is now rendered as interactive Chart.js in the HTML — no PNG needed

        utils.log("Generating HTML report...", "system")
        utils.generate_html(t.month,
                            t.year,
                            spendings_df,
                            high_std_spendings,
                            earnings_df,
                            high_std_earnings,
                            monthly_balance,
                            card_color_dict,
                            data,
                            accounts_data,
                            cash_information_data,
                            alerts=alerts,
                            mortgage_data=mortgage_data,
                            accounts_meta=accounts_raw_meta)
        import os as _os
        if not _os.environ.get('BANKAPP_WEB'):
            webbrowser.open(r'source\html\output.html')

    def debug_value_mismatch(self) -> None:
        from datetime import datetime
        from Constants import BANK_CARD_NUMBER

        utils.log("Loading organizer table...", 'system')
        _, color_coded_df = utils.read_present_table()

        # Collect all (month_str, col) cells where validation ran and failed
        mismatches = [
            (idx, col)
            for col in color_coded_df.columns
            if col.split(' | ')[-1] != BANK_CARD_NUMBER
            for idx in color_coded_df.index
            if color_coded_df.at[idx, col] == False  # noqa: E712 — must use == for pandas
        ]

        if not mismatches:
            utils.log("No mismatches found.", 'system')
            return

        utils.log(f"Found {len(mismatches)} mismatch(es).\n", 'system')

        while True:
            display = [f"{col} — {month_str}" for month_str, col in mismatches]
            choice = utils.template_menu(display, "Select a mismatch to debug:", exit=True, col_space=50)
            if choice == 0:
                return
            month_str, col = mismatches[choice - 1]
            format_name, card_number = col.split(' | ')
            date = datetime.strptime(month_str, "%B, %Y")
            possible_names = Formats.FORMATS.get(format_name, {}).get("Transaction Names", {}).get(card_number, [])

            charge_month = utils.next_month(date)
            file_df = DataBase().get_file_table()
            file_row = file_df[
                (file_df['Format'] == format_name) &
                (file_df['Card_Number'] == card_number) &
                (pd.to_datetime(file_df['Date']).dt.month == charge_month.month) &
                (pd.to_datetime(file_df['Date']).dt.year == charge_month.year)
            ]
            file_name = file_row['File_Name'].values[0] if not file_row.empty else "Not found"

            utils.log(f"\n{'='*60}", 'system')
            utils.log(f"  {format_name} | {card_number} — {month_str}", 'system')
            utils.log(f"  File: {file_name}", 'system')
            utils.log(f"{'='*60}", 'system')

            # Card transactions for this month — two passes:
            # general_analysis=True  → matches validation exactly (correct sum)
            # general_analysis=False → keeps all rows so Relevance is meaningful for display
            processed_df_analysis = AppManagerUtils.retrieve_and_initialize_data(date, std_out=False, general_analysis=True)
            card_df_analysis = processed_df_analysis[
                (processed_df_analysis['TableName'] == 'CardTransactions') &
                (processed_df_analysis['CardID'] == card_number)
            ].copy()

            processed_df_debug = AppManagerUtils.retrieve_and_initialize_data(date, std_out=False, general_analysis=False)
            card_df = processed_df_debug[
                (processed_df_debug['TableName'] == 'CardTransactions') &
                (processed_df_debug['CardID'] == card_number)
            ].copy()

            if card_df_analysis.empty:
                utils.log("  No card transactions found.", 'system')
                continue

            display_cols = ['ID', 'TableName', 'Source_file', 'Name', 'Executed_Date', 'Charge_Value', 'Charge_Currency', 'Final_Value', 'Category', 'Relevance']
            card_df = card_df.reset_index(drop=True)
            utils.log("\n" + utils.df_to_markdown(card_df[display_cols]), 'system')
            expected_sum = abs(round(card_df_analysis['Final_Value'].sum(), 2))
            utils.log(f"  Expected charge sum: {expected_sum}", 'system')

            # Bank candidates from next month (charge_month already computed above)
            next_m = charge_month
            if not possible_names:
                utils.log("  No charge names configured for this card — cannot compare bank transactions.", 'system')
                continue

            bank_df = DataBase().get_Bank_Transactions(next_m.month, next_m.year)
            candidates = bank_df[bank_df['Name'].isin(possible_names)].copy()

            if candidates.empty:
                utils.log(f"  No bank transactions in {next_m.strftime('%B %Y')} matching names: {possible_names}", 'system')
                continue

            card_df_analysis = card_df_analysis.reset_index(drop=True)
            abs_values = card_df_analysis['Final_Value'].abs().round(2).tolist()

            utils.log(f"\n  Bank candidates in {next_m.strftime('%B %Y')}:", 'system')
            for _, row in candidates.iterrows():
                bank_out = round(row['Out'], 2)
                diff = round(bank_out - expected_sum, 2)
                utils.log(f"    {utils.heb_conversion(str(row['Name']))} | {row['Date']} | Out={bank_out:.2f} | Diff={diff:+.2f}", 'system')

                if diff == 0:
                    utils.log("    -> MATCH — no missing transactions.", 'system')
                    continue

                # Find a subset of transactions whose abs(Final_Value) sum equals abs(diff)
                target = round(abs(diff), 2)
                combo = self._find_subset_sum(abs_values, target)
                if combo is not None:
                    matched = card_df_analysis.iloc[list(combo)][['Name', 'Final_Value', 'Category']]
                    utils.log(f"    -> Combination accounting for the diff ({diff:+.2f}):", 'system')
                    utils.log("\n" + utils.df_to_markdown(matched), 'system')
                else:
                    utils.log(f"    -> No single combination of transactions accounts for the diff ({diff:+.2f}).", 'system')

            exact_matches = candidates[candidates['Out'].apply(lambda x: round(x, 2)) == expected_sum]
            if not exact_matches.empty:
                utils.log("  MATCH EXISTS — mismatch may have since resolved.", 'system')
            else:
                utils.log(f"  NO MATCH — mismatch confirmed. Expected {expected_sum}.", 'system')

    @staticmethod
    def _find_subset_sum(values: list, target: float) -> list | None:
        """Return indices of the smallest subset of values that sums to target (±0.01), or None."""
        from itertools import combinations
        for r in range(1, len(values) + 1):
            for combo in combinations(range(len(values)), r):
                if abs(round(sum(values[i] for i in combo), 2) - target) <= 0.01:
                    return list(combo)
        return None



