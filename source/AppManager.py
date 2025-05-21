from Parser import Parser
from Card import Card
from Bank import Bank
from Context import Context
from Constants import Local, CC_CHARGE_CATEGORY_NAME, INVESTMENT_CATEGORY, GOLDEN_COLOR_PALLETE, GeneralPlot
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
            print("""
                    Hello Ofek!
                    What would you like to do today?

                    1. Update/Parse files
                    2. Show statistics
                    3. Delete file information
                    4. Search transactions 
                    5. Update existing file
                    6. Execute SQL query on db
                    7. Open File Organizer
                    8. Export Excel
                    9. Insert other account status
                    10. Advanced Search                  
                    11. Exit
                """)
            answer = input()
            answer = -1 if not answer.isdigit() else int(answer)

            match answer:
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
                    df = utils.read_present_table()
                    utils.create_html_with_colored_dates(df)
                case 8:
                    self.exporter_function()
                case 9:
                    self.Insert_other_account_status()
                case 10:
                    self.advanced_search()
                case 11:
                    break
                case _:
                    print("Please insert a valid number.")

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

            choice = utils.template_menu(options, "\nSelect search filter to add:")

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
                                   'Edit transaction description'], 'Pick one of the following:')
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
            case _:
                utils.log('Something went wrong in "execute_sql"', 'error')

    def update_existing_file_v2(self):
        update_file_lst = listdir(Local.UPDATE_FOLDER)
        if len(update_file_lst) == 0:
            utils.log(f"{Local.UPDATE_FOLDER} is Empty. Returning to menu..", "system")
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
            utils.move_file_to_directory(file_path=f"{Local.UPDATE_FOLDER}/{new_file_name}",
                                         destination_directory=Local.INPUT_FOLDER)
            utils.log("Done." 'system')

            utils.log(f"Moving existing (old file) {existing_file_name}  file to 'removed' folder...", 'system')
            utils.move_file_to_directory(file_path=f"{Local.VERIFIED_FOLDER}/{existing_file_format}/{existing_file_name}",
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
                                utils.move_file_to_directory(file_path=f"{Local.INPUT_FOLDER}/{new_file_name}",
                                                             destination_directory=Local.UPDATE_FOLDER)
                                utils.log("Done." 'system')

                                utils.log("Moving file back to input folder...", 'system')
                                utils.move_file_to_directory(file_path=f"removed/{existing_file_name}",
                                                             destination_directory=Local.INPUT_FOLDER)
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
                utils.move_file_to_directory(file_path=f"{Local.INPUT_FOLDER}/{new_file_name}",
                                             destination_directory=Local.UPDATE_FOLDER)
                utils.log("Done." 'system')

                utils.log("Moving file back to input folder...", 'system')
                removed_root = existing_file_name.split("\\")[-1]
                add_root = existing_file_name.split("\\")[0]
                utils.move_file_to_directory(file_path=f"removed/{removed_root}",
                                             destination_directory=f"{add_root}/{Local.INPUT_FOLDER}")
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
                    DataBase().set_category(table=row['TableName'], id=row['ID'], category=res)
                    if len(description) > 1:
                        DataBase().set_transaction_description(description, row['TableName'], row['ID'])
                    utils.log("Tag saved.", "system")
                    DataBase().commit_changes()
                # ---------------- Fill in similar rows ----------------
                if tag_status_res != 'No Match':
                    similar_trans, desc_x = DataBase().get_by_name(row['TableName'], row['Original_Name'])
                    count = len(similar_trans)
                    if count > 0:
                        if tag_status_res is None:
                            res_x = utils.template_menu(['Yes', 'No'],
                                                        f"There are {count} untagged transaction with the same name. Do you want apply to all?")
                        else:
                            res_x = 0
                        if res_x == 0:    # Yes -> 0
                            res_df = pd.DataFrame(similar_trans, columns=desc_x)
                            for _, row_x in res_df.iterrows():
                                DataBase().set_category(table=row['TableName'], id=row_x['ID'], category=res)
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
        match utils.template_menu(["General Statistics", "Pick a category/Bussines name"], "Pick an option:"):
            case 0:
                self.general_analysis()
            case 1:
                self.category_analysis()
            case _:
                utils.log("Unreachable point reached...", "error")

    def category_analysis(self):

        case = 0

        match utils.template_menu(["Analyze a category", "Analayze a Business"], "Pick an option:"):
            case 0:
                options = utils.get_saved_categories()
                idx, sub_options = utils.typer_template_menu(options, "Pick a Category:")
            case 1:
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
                                         "Monthly Active Average": get_active_monthly_average(name_for_analysis, case),
                                         "Monthly Active Standard Deviation": get_active_monthly_sd(name_for_analysis, case),
                                         "Yearly Average": yearly_average(name_for_analysis, case),
                                         "Total Spendings": total_spendings(name_for_analysis, case),
                                         "Total Income": total_income(name_for_analysis, case),
                                         "Yearly use plot path": r"C:\Users\ofeks\OneDrive\BankProject\Outputs\General_info_Category_analysis.png",
                                         "Highest Transaction value" : "X",
                                         "Highest Transaction date": "X",
                                         "Association list": outliers_lst,
                                         "count pie plot path" : r"C:\Users\ofeks\OneDrive\BankProject\Outputs\Category_Distribution.png",
                                         "transactions": df_transactions})
        webbrowser.open(r'source\html\Category_output.html')


    def general_analysis(self):
        from datetime import datetime
        # -----
        print("Pick an option:\n1 -> Current Month\n2 -> Last Month\n3 -> Pick A date")
        x = int(input())
        match x:
            case 1:
                t = datetime.now()
            case 2:
                from dateutil.relativedelta import relativedelta
                t = datetime.now() - relativedelta(months=1)
            case _:
                m = int(input('month: '))
                y = int(input('year: '))
                t = datetime.now().replace(day = 1, month=m, year=y)

        data = {}

        def card_charge_validation(date: datetime) -> pd.DataFrame:
            """
            """
            # ---------------------------------------------------------
            #   The following line will help configure the אשראי　transactions
            # ---------------------------------------------------------
            df = DataBase().card_sum(date)
            # The following will result in a data base describing the total amount of spendings per card in the given month.
            debbug_df = df.copy()
            cards_df = df.groupby("CardID").sum().reset_index()
            cards_df['Status'] = 'Not Verified'
            bank_df = DataBase().get_Bank_Transactions(Local.CHARGE_DAY + 1,
                                                    utils.next_month(date).month,
                                                    utils.next_month(date).year)
            for _, row_cs in cards_df.iterrows():
                for _, row_bt in bank_df.iterrows():
                    x = round(row_bt['Out'], 2)
                    y = round(row_cs['Out/Transaction_value'], 2)
                    if x == y:
                        cards_df.loc[cards_df['CardID'] == row_cs['CardID'], 'Status'] = 'Verified'
                        if row_bt['Category'] == 'אשראי':
                            break

                        if utils.template_menu(['No', 'Yes'], f"App found this transaction to be a credit card:\n\
                                            {row_bt}\n Do you Agree?"):
                            DataBase().set_category('BankTransactions', row_bt['ID'], CC_CHARGE_CATEGORY_NAME)
                            DataBase().commit_changes()
                            break
                        else:
                            utils.log('ignored...', 'system')

            if not cards_df.empty:
                cards_df = cards_df[['CardID', 'Status', 'Out/Transaction_value']]
            
            for index, row in cards_df.iterrows():
                if row['Status'] == 'Not Verified':
                    # Perform your action here
                    utils.log(f"information for card at index: {index},\n {debbug_df[debbug_df['CardID'] == row['CardID']].to_markdown()}", 'debug')
            return cards_df

        def print_unverified_cards(date: datetime):
            """
            The function will iterate past data and print the card id and mnths which were not verified.
            """
            df = card_charge_validation(date)
            while not df.empty:
                for _, row in df.iterrows():
                    if row['Status'] == 'Not Verified':
                        utils.log(f"Card {row['CardID']} was not verified for {date.month}/{date.year}", 'warning')
                m, y = utils.subtract_month(date.month, date.year)
                date = datetime(int(y),int(m),1)
                df = card_charge_validation(date)
            
        print_unverified_cards(t)
        card_validation_df = card_charge_validation(t)
        
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
        accounts_data = get_accounts_data()
        Graphics.plot_linear_plots_graph(accounts_data)
        
        monthly_balance = DataBase().get_latest_Balance()

        spendings_df = SimpleMath.process_prices(
                            DataBase().get_monthly_spendings(year=t.year, month=t.month)
                            )

        spendings_df = utils.remove_leumi(spendings_df)

        earnings_df = SimpleMath.process_prices(
                            DataBase().get_monthly_earnings(year=t.year, month=t.month)
                            )
        earnings_df = utils.remove_leumi(earnings_df)

        # ---------------- Spendings Pie plot ----------------
        color_pallete = sns.light_palette("#f66b85", n_colors=10, reverse=True)
        spendings_With_no_investments_df = spendings_df[spendings_df["Category"] != INVESTMENT_CATEGORY]
        high_std_spendings = Graphics.plot_transactions_pie_chart(spendings_With_no_investments_df.groupby("Category").sum(), 
                                                                  "Spendings", 
                                                                  color_pallete)
        # -------------=--- Earnings Pie plot -----------------
        color_pallete = sns.light_palette("#4fba89", n_colors=10, reverse=True)
        high_std_earnings = Graphics.plot_transactions_pie_chart(earnings_df.groupby("Category").sum(),
                                                                 "Earnings",
                                                                 color_pallete)
        # ---------------- Investments Pie plot ----------------
        color_pallete = GOLDEN_COLOR_PALLETE
        investments_df = spendings_df[spendings_df["Category"] == INVESTMENT_CATEGORY]
        _ = Graphics.plot_transactions_pie_chart(investments_df,
                                                "Investments",
                                                color_pallete)

        # ----- General
        spendings_sum, spendings_sum_overall_inc, earnings_sum = SimpleMath.get_monthly_shifted(shift=10)

        Graphics.plot_general(spendings_sum, 
                              spendings_sum_overall_inc,
                              earnings_sum,
                              lp_Overall_income=True,
                              lp_user_defined=False)
        
        # ----- User defined
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

        card_ids = DataBase().get_card_ids() + ['Bank']
        color_list = Local.Colors[:len(card_ids)]
        card_color_dict = dict(zip(card_ids, color_list))

        Graphics.card_distribution(spendings_With_no_investments_df, card_color_dict, card_validation_df)

        data['net income'] = (earnings_df['Final_Value'].sum() - spendings_df['Final_Value'].abs().sum())
        data['overall net income'] = (earnings_df['Final_Value'].sum() - \
                                      spendings_With_no_investments_df['Final_Value'].abs().sum())
        data['overall_net_mean'] = (np.array(earnings_sum) + np.array(spendings_sum_overall_inc)).mean()
        
        utils.generate_html(t.month,
                            t.year,
                            spendings_df,
                            high_std_spendings,
                            earnings_df,
                            high_std_earnings,
                            monthly_balance,
                            card_color_dict,
                            data,
                            accounts_data)
        webbrowser.open(r'source\html\output.html')





