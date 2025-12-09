from Parser import Parser
from Card import Card
from Bank import Bank
from Context import Context
from Constants import Local, Paths
from Constants import CC_CHARGE_CATEGORY_NAME, INVESTMENT_CATEGORY, GOLDEN_COLOR_PALLETE, GeneralPlot, Settings, Trans_Type
from src_utils.utils import utils
from database import DataBase
from front.Graphics import Graphics
from src_utils.calculations import SimpleMath
from src_utils.ExcelReader import ExcelManager
import webbrowser
from Configurations.Formats import Formats, Context_class
import pandas as pd
from os import listdir
import numpy as np
import seaborn as sns
from Exporter import Exporter

class AppManager:

    def __init__(self):
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
                                             'Advanced Search'],
                                             msg='Hello Ofek! What would you like to do today?',
                                             exit=True,
                                             col_space=33):
            
                case 0:
                    return
                case 1:
                    self.load_data()
                    utils.tagger_refresh()
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
                    utils.create_html_with_colored_dates(df, color_coded_df)
                case 8:
                    self.add_cash_transaction()
                case 9:
                    self.exporter_function()
                case 10:
                    self.Insert_other_account_status()
                case 11:
                    self.advanced_search()
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
                    # Get account name
                    # Get account names from database
                    account_names = DataBase().get_all_account_names()
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
                                   'Delete a cash transaction entery by ID'], 'Pick one of the following:', col_space=60)
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

    def category_analysis(self):

        case = 0

        match utils.template_menu(["Analyze a category", "Analayze a Business"], "Pick an option:", exit=True):
            case 0:
                return
            case 1:
                options = utils.get_saved_categories()
                idx, sub_options = utils.typer_template_menu(options, "Pick a Category:")
            case 2:
                case = 1
                options = DataBase().get_all_business_names()
                idx, sub_options = utils.typer_template_menu(options, "Pick a Bussines:")
            case _:
                utils.log("Unreachable point reached...", "error") 

        name_for_analysis = sub_options[idx]

        def get_monthly_average(name_for_analysis, case):
            """
            Returns category \ business monthly average of all incomes and sepndings 
            """
            total_sum = DataBase().total_sum_transactions(name_for_analysis, case)
            total_months = DataBase().months_total_calculator()
            monthly_average_value = round(total_sum / total_months, 2)
            return monthly_average_value
        
        def get_rolling_monthly_average(name_for_analysis, case, rolling_window=5):
            """
            Returns category/business monthly average over the last 5 months
            (excluding current month)
            """
            from dateutil.relativedelta import relativedelta
            
            if case:
                df = DataBase().get_transactions(category=None, business=name_for_analysis)
            else:
                df = DataBase().get_transactions(category=name_for_analysis, business=None)

            df = SimpleMath.process_prices(df)
            
            from datetime import datetime
            # Convert dates and filter last 5 months
            current_date = datetime.now().replace(day=1) # First day of current month
            x_months_ago = current_date - relativedelta(months=rolling_window)
            
            df['Date/Executed_Date'] = pd.to_datetime(df['Date/Executed_Date'])
            mask = (df['Date/Executed_Date'] >= x_months_ago) & (df['Date/Executed_Date'] < current_date)
            df = df[mask]
            
            # Group by month and calculate average
            df['month_year'] = df['Date/Executed_Date'].dt.strftime('%Y-%m')
            monthly_sums = df.groupby('month_year')['Final_Value'].sum()
            
            return round(monthly_sums.sum() / rolling_window, 2)

        def get_active_monthly_average(name_for_analysis, case):
            """
            Returns category \ business monthly average of active months, i.e - months that include
            any transaction of the chosen category \ business
            """
            #total_sum = DataBase().total_sum_transactions(name_for_analysis, case)
            if case:
                df = DataBase().get_transactions(category=None, business=name_for_analysis)
            else:
                df = DataBase().get_transactions(category=name_for_analysis, business=None)

            df = SimpleMath.process_prices(df)
            df['Date/Executed_Date'] = pd.to_datetime(df['Date/Executed_Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y-%m'))
            df = df.groupby('Date/Executed_Date').sum()
            total_active_month = len(df)
            total_sum = df['Final_Value'].sum()
            monthly_average_value = round(total_sum / total_active_month, 2)
            return monthly_average_value

        def get_active_monthly_sd(name_for_analysis, case):
            """
            Returns category \ business standard deviation of all incomes and spendings
            """
            if case:
                df = DataBase().get_transactions(category=None, business=name_for_analysis)
            else:
                df = DataBase().get_transactions(category=name_for_analysis, business=None)

            df = SimpleMath.process_prices(df)
            df['Date/Executed_Date'] = pd.to_datetime(df['Date/Executed_Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y-%m'))
            df = df.groupby('Date/Executed_Date').sum()
            total_active_month = len(df)
            total_sum = df['Final_Value'].sum()
            active_monthly_average = get_active_monthly_average(name_for_analysis, case)
            monthly_average_value = round(((total_sum -  active_monthly_average) / total_active_month) ** 0.5, 2)
            return monthly_average_value
        
        def yearly_average(name_for_analysis, case):
            """
            Returns category \ business yearly average of all incomes and spenedings 
            """
            if case:
                df = DataBase().get_transactions(category=None, business=name_for_analysis)
            else:
                df = DataBase().get_transactions(category=name_for_analysis, business=None)

            df = SimpleMath.process_prices(df)
            df['Date/Executed_Date'] = pd.to_datetime(df['Date/Executed_Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y'))
            df = df.groupby('Date/Executed_Date').sum()
            df_len = len(df)
            total_active_month = DataBase().months_total_calculator()
            total_sum = df['Final_Value'].sum()
            monthly_average_value = round(total_sum * 12 / total_active_month, 2)
            return monthly_average_value
        
        def total_spendings(name_for_analysis, case):
            """
            Returns category \ business total spendings
            """
            if DataBase().total_spendings(name_for_analysis, case) == None:
                return 0
            return DataBase().total_spendings(name_for_analysis, case)

        def total_income(name_for_analysis, case):
            """
            Returns category \ business total income
            """
            if DataBase().total_income(name_for_analysis, case) == None:
                return 0
            return DataBase().total_income(name_for_analysis, case)

        if case:
            spendings_sum, spendings_sum_overall_inc, earnings_sum = SimpleMath.get_monthly_shifted(shift=6, category=None, business=name_for_analysis)
        else:
            spendings_sum, spendings_sum_overall_inc, earnings_sum = SimpleMath.get_monthly_shifted(shift=6, category=name_for_analysis, business=None)

        Graphics.plot_general(spendings_sum, spendings_sum_overall_inc, earnings_sum, title_ext='Category_analysis', topic = name_for_analysis, fig_size=(8, 5))
        
        def remove_by(df: pd.DataFrame, category=None, business_name=None) -> pd.DataFrame:
            if category is not None:
                df = df[df['Category'] == category]

            if business_name is not None:
                df = df[df['Name'] == business_name]

            return df

        def get_associated(name_for_analysis, case) -> list[str]:
            """
            TODO
            """
            if case:
                df = DataBase().get_transactions(category=None, business=name_for_analysis)
                df = SimpleMath.process_prices(df)
                df = df[['Name','Final_Value','Category']].groupby('Category').sum()
            else:
                df = DataBase().get_transactions(category=name_for_analysis, business=None)
                df = SimpleMath.process_prices(df)
                df = df[['Name','Final_Value','Category']].groupby('Name').sum()
            
            return Graphics.plot_pie_distribution(df)



        df_transactions = SimpleMath.process_prices(DataBase().get_transactions())
        if case:
            df_transactions = remove_by(df_transactions,business_name=name_for_analysis)
        else:
            df_transactions = remove_by(df_transactions,category=name_for_analysis)

        outliers_lst = get_associated(name_for_analysis, case)

        # Run analysis     
        utils.create_html_name_analysis({"subtitle": "Specific Analysis",
                                         "Category/business name": name_for_analysis,
                                         "Monthly Average": get_monthly_average(name_for_analysis, case),
                                         "Recent Monthly Average": get_rolling_monthly_average(name_for_analysis, case),
                                         "Monthly Active Average": get_active_monthly_average(name_for_analysis, case),
                                         "Monthly Active Standard Deviation": get_active_monthly_sd(name_for_analysis, case),
                                         "Yearly Average": yearly_average(name_for_analysis, case),
                                         "Total Spendings": total_spendings(name_for_analysis, case),
                                         "Total Income": total_income(name_for_analysis, case),
                                         "Yearly use plot path": r"C:\Users\ofeks\OneDrive\Ofek\BankProject\Outputs\General_info_Category_analysis.png",
                                         "Highest Transaction value" : "X",
                                         "Highest Transaction date": "X",
                                         "Association list": outliers_lst,
                                         "count pie plot path" : r"C:\Users\ofeks\OneDrive\Ofek\BankProject\Outputs\Category_Distribution.png",
                                         "transactions": df_transactions})
        webbrowser.open(r'source\html\Category_output.html')


    def general_analysis(self):
        from datetime import datetime
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
        def get_accounts_data() -> dict:
            """Get historical balance data for all accounts including main bank account"""
            accounts_data = {}
            
            # Get main bank account data
            bank_df = DataBase().get_monthly_bank_balances()
            accounts_data['Main Bank'] = list(zip(bank_df['Date'], bank_df['Balance']))

            # Get other accounts data 
            other_accounts_df = DataBase().get_account_entries_with_dates()
            for account in other_accounts_df['AccountName'].unique():
                account_df = other_accounts_df[other_accounts_df['AccountName'] == account]
                accounts_data[account] = list(zip(account_df['Date'], account_df['Value']))

            # Calculate total sum across all accounts
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

            return accounts_data

        # Get accounts data and create linear plot
        utils.log("Generating linear plots for all accounts...", "system")
        accounts_data = get_accounts_data()
        Graphics.plot_linear_plots_graph(accounts_data)
        
        utils.log("Processing card data...", "system")        
        monthly_card_transactions_df = DataBase().query_monthly_transactions(date=t, tables=["CardTransactions"])
        proceessed_card_transactions_df = SimpleMath.process_prices(monthly_card_transactions_df, date=t, debug=Settings.DEBUG)

        utils.log("Processing bank data...", "system")
        monthly_bank_transactions_df = DataBase().query_monthly_transactions(date=t, tables=["BankTransactions"])
        proceessed_bank_transactions_df = SimpleMath.process_prices(monthly_bank_transactions_df, date=t)
        
        # -------------------------- Collision of both df --------------------------
        if monthly_card_transactions_df.empty:
            utils.log("No card transactions found for the selected month.", "warning")
        else:
            proceessed_card_transactions_df=proceessed_card_transactions_df[['ID',
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
        if monthly_bank_transactions_df.empty:
            utils.log("No bank transactions found for the selected month.", "warning")
        else:
            proceessed_bank_transactions_df=proceessed_bank_transactions_df[['ID',
                                                                             'TableName', 
                                                                             'Name',
                                                                             'Date', 
                                                                             'Final_Value',
                                                                             'Category',
                                                                             'Extra_Info',
                                                                             'Description',
                                                                             'Transaction_Type']]
            
        proceessed_bank_transactions_df = proceessed_bank_transactions_df.rename(columns={'Date': 'Executed_Date'})
        
        transactions_df = pd.concat([proceessed_bank_transactions_df, proceessed_card_transactions_df], ignore_index=True)

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

        accounts_data['Cash'] = [(datetime.now(), 
                                                 cash_information_data["Accumulative Cash Balance"])]

        
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
        
        def handle_investments_pie_plot():           
            color_pallete = GOLDEN_COLOR_PALLETE
            temp_df = transactions_df[(transactions_df["Category"] == INVESTMENT_CATEGORY)]
            Graphics.plot_transactions_pie_chart(temp_df,
                                                "Investments",
                                                color_pallete)
            
        utils.log("Generating investments pie charts...", "system")
        handle_investments_pie_plot()

        # ----- General
        utils.log("Generating general bar plot...", "system")
        spendings_sum, spendings_sum_overall_inc, earnings_sum = SimpleMath.get_monthly_shifted(shift=10)

        Graphics.plot_general(spendings_sum, 
                              spendings_sum_overall_inc,
                              earnings_sum,
                              lp_Overall_income=True,
                              lp_user_defined=False)
        
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

        # ----- Payment PIE Graphs
        from Constants import Trans_Type
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
                            cash_information_data)
        webbrowser.open(r'source\html\output.html')





