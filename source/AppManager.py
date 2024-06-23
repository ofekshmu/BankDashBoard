from Parser import Parser
from Card import Card
from Bank import Bank
from Context import Context
from Constants import Local
from src_utils.utils import utils
from database import DataBase
from front.Graphics import Graphics
from src_utils.calculations import SimpleMath
from src_utils.ExcelReader import ExcelManager
import webbrowser
from Configurations.Formats import Formats, Context_class
import pandas as pd
import json

from os import listdir


class AppManager:

    def __init__(self):
        res = utils.validate_formats()
        if type(res) == str:
            utils.log(res, 'error')
        else:
            utils.log(f'Format validation result: {res}', 'system')
        
        self.parser = Parser()

    def menu(self):
        while True:
            print("""
                    Hello Ofek!
                    What would you like to do today?

                    1. Update/Parse files
                    2. Show statistics
                    3. Delete file information
                    4. Validate
                    5. Update existing file
                    6. Execute SQL query on db
                    7. Open File Organizer
                    8. Exit
                """)
            answer = input()
            answer = -1 if not answer.isdigit() else int(answer)

            match answer:
                case 1:
                    self.load_data()
                    self.tag_data()
                case 2:
                    self.analysis()
                case 3:
                    self.delete_file_info()
                case 4:
                    utils.log("Option no avaliable", 'system')
                case 5:
                    self.update_existing_file_v2()
                case 6:
                    self.execute_sql()
                case 7:
                    df = utils.read_present_table()
                    utils.create_html_with_colored_dates(df)
                case 8:
                    break
                case _:
                    print("Please insert a valid number.")

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
                                   'Change transaction category by ID'], 'Pick one of the follwing:')
        match res:
            case 0:
                original_command()
            case 1:
                DataBase().change_category_by_id()
                DataBase().commit_changes()
            case _:
                utils.log('Something went wrong in "execute_sql', 'error')

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
                        res = utils.template_menu(['Abort update', 'Skip entery, its not important...'],
                                                  f'Did not found a correspinding entery for\n{entry_ex}\nin the new file.\n\
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
            my_series['Charge_Value/Out'] = str(my_series['Charge_Value/Out']) + ' ₪'
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
                                    'Source file name']
            else:
                my_series.index = ['Table Name',
                                    'Transaction ID',
                                    'Executed Date',
                                    'Name',
                                    'Reference ID',
                                    'Outgoing',
                                    'Incoming',
                                    'More Info',
                                    'Source file name']

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
                    DataBase().set_category(table=row['TableName'], id=row['ID'], category=res)
                    if len(description) > 1:
                        DataBase().set_transaction_description(description, row['TableName'], row['ID'])
                    utils.log("Tag saved.", "system")
                    DataBase().commit_changes()
                # ---------------- Fill in similar rows ----------------
                similar_trans, desc_x = DataBase().get_by_name(row['TableName'], row['Original_Name'])
                count = len(similar_trans)
                if count > 0:
                    res_x = utils.template_menu(['Yes', 'No'],
                                                f"There are {count} untagged transaction with the same name. Do you want apply to all?")
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
                options = json.load(open(Local.CATE_JSON_PATH, encoding='utf-8'))
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
            total_sum = DataBase().total_sum_transactions(name_for_analysis, case)
            total_months = len(DataBase().bank_transactions_sum_list(name_for_analysis, case))
            monthly_average_value = round(total_sum / total_months, 2)
            return monthly_average_value

        def get_active_monthly_sd(name_for_analysis, case):
            """
            Returns category \ business standard deviation of all incomes and spendings
            """
            month_sum_df = DataBase().bank_transactions_sum_list(name_for_analysis, case)
            month_sum_first_column = month_sum_df.iloc[:,0]
            sd_numerator = (month_sum_first_column - month_sum_first_column.mean()) ** 2
            total_sum = sd_numerator.sum()
            return round((total_sum / len(month_sum_df)) ** 0.5, 2)
        
        # Run analysis     
        utils.create_html_name_analysis({"subtitle": "Specific Analysis",
                                         "Category/business name": name_for_analysis,
                                         "Monthly Average": get_monthly_average(name_for_analysis, case),
                                         "Monthly Active Average": get_active_monthly_average(name_for_analysis, case),
                                         "Monthly Active Standard Deviation": get_active_monthly_sd(name_for_analysis, case),
                                         "Yearly Average": 0,
                                         "Total Spendings": DataBase().total_spendings(name_for_analysis, case),
                                         "Total Income": 0,
                                         "Yearly use plot path": r"C:\Users\ofeks\OneDrive\BankProject\Outputs\Spendings_category.png",
                                         "Highest Transaction value" : "X",
                                         "Highest Transaction date": "X",
                                         "Association list": [("Name1",2), ("Name2",4), ("Name3",6)],
                                         "count pie plot path" : "Insert path here",
                                         "transactions": pd.DataFrame([1,2,4])})
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
                t = datetime.now().replace(month=m, year=y)

        # ---------------------------------------------------------
        #   The following line will help configure the אשראי　transactions
        # ---------------------------------------------------------
        df, desc = DataBase().card_sum(t)
        # ------------------------------ DEBUG ---------------------------------
        # test = SimpleMath.process_prices(df, desc)
        # print(pd.DataFrame(df, columns=desc).to_markdown())
        # utils.log(test.to_markdown(), 'debug')
        # utils.log(test[test['CardID'] == '4046']['Final_Value'].sum(), 'debug')
        # ----------------------------------------------------------------------
        cards_df = pd.DataFrame(df, columns=desc).groupby("CardID").sum().reset_index()
        cards_df['Status'] = 'Not Verified'
        bank_df = DataBase().get_Bank_Transactions(Local.CHARGE_DAY + 1, 
                                                   utils.next_month(t).month,
                                                   utils.next_month(t).year)
        for _, row_cs in cards_df.iterrows():
            for _, row_bt in bank_df.iterrows():
                x = round(row_bt['Out'], 2)
                y = round(row_cs['Out/Transaction_value'], 2)
                if x == y:
                    cards_df.loc[cards_df['CardID'] == row_cs['CardID'], 'Status'] = 'Verified'
                    if row_bt['Category'] == 'אשראי':
                        break

                    res = utils.template_menu(['Yes', 'No'], f"App found this transaction to be a credit card:\n\
                                              {row_bt}\n Do you Agree?")
                    if res == 0:
                        DataBase().set_category('BankTransactions', row_bt['ID'], 'אשראי')
                        DataBase().commit_changes()
                        break
                    else:
                        utils.log('ignored...', 'system')

        if not cards_df.empty:
            cards_df = cards_df[['CardID', 'Status']]

        # ---------------------------------------------------------

        monthly_balance = DataBase().get_latest_Balance()

        spendings, description = DataBase().get_monthly_spendings(year=t.year, month=t.month)
        spendings_df = SimpleMath.process_prices(spendings, description)
        spendings_df = utils.remove_leumi(spendings_df)

        earnings, description = DataBase().get_monthly_earnings(year=t.year, month=t.month)
        earnings_df = SimpleMath.process_prices(earnings, description)
        earnings_df = utils.remove_leumi(earnings_df)

        high_std_spendings = Graphics.plot_transactions_pie_chart(spendings_df, "Spendings", Local.gentle_orange)
        high_std_earnings = Graphics.plot_transactions_pie_chart(earnings_df, "Earnings", Local.gentle_blue)

        # ------ GAS
        cat_data, description_cat = DataBase().get_by_category("Gas")
        df = SimpleMath.process_prices(cat_data, description_cat)
        if not df.empty:
            _ = Graphics.plot_gas(df)
            cat_dict = SimpleMath.cat_info(df)
            Graphics.plot_monthly_gas(df)
        else:
            cat_dict = {}
        # ----- General
        spendings_sum, earnings_sum = SimpleMath.get_monthly_shifted(shift=5)
        Graphics.plot_general(spendings_sum, earnings_sum)
        # ----- Cards

        card_ids = DataBase().get_card_ids() + ['Bank']
        color_list = Local.Colors[:len(card_ids)]
        card_color_dict = dict(zip(card_ids, color_list))

        Graphics.card_distribution(spendings_df, card_color_dict)

        utils.generate_html(t.month,
                            spendings_df,
                            high_std_spendings,
                            earnings_df,
                            high_std_earnings,
                            monthly_balance,
                            card_color_dict,
                            cat_dict,
                            cards_df)
        webbrowser.open(r'source\html\output.html')



        

