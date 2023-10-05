from Parser import Parser
from Card import Card
from Bank import Bank
from Context import Context
from Constants import Local
from src_utils.utils import utils
from database import DataBase
from front.Graphics import Graphics
from src_utils.calculations import SimpleMath
import webbrowser
from Configurations.Formats import Formats, Context_class
from typing import Tuple
import pandas as pd
from os import listdir


class AppManager:

    def __init__(self):
        self.parser = Parser()
        utils.validate_formats()
        
    def menu(self):
        print("""
                Hello Ofek!
                What would you like to do today?

                1. Update/Parse files
                2. Show statistics
                3. Delete file information
                4. Validate
                5. Update existing file
                6. Execute SQL query on db
                7. Exit
            """)
        answer = int(input())
        match answer:
            case 1:
                self.load_data()
                self.tag_data()
            case 2:
                self.analysis()
            case 3:
                self.delete_file_info()
            case 4:
                self.validate()
            case 5:
                self.update_existing_file()
            case 6:
                self.execute_sql()
            case 7:
                exit()
            case _:
                print("Please insert a valid number.")

    def execute_sql(self):
        pw = input("Please confirm password for this action: ")
        if pw != "ofek":
            utils.log("Bad password", "system")
            return False
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

    def update_existing_file(self) -> bool:

        update_file_lst = listdir(Local.UPDATE_FOLDER)
        if len(update_file_lst) == 0:
            utils.log(f"{Local.UPDATE_FOLDER} is Empty. Returning to menu..", "system")
            return False

        files_df = DataBase().get_file_table()
        print(files_df.to_markdown())
        file_id = utils.template_menu(list(files_df["Name"]),
                                      "Please choose what file do you want to update and delete.")

        new_file_id = utils.template_menu(update_file_lst,
                                          f"Choose a file to update from.")

        ack = utils.template_menu(["Yes", "No"], "Are you sure?")
        if ack == 0:
            file_name = list(files_df["Name"])[file_id]
            utils.log(f"Removing {file_name}...", 'system')
            DataBase().drop_file(file_name)
            utils.log(f"File chose to update from: {update_file_lst[new_file_id]}", 'system')
            utils.move_file_to_directory(file_path=f"{Local.UPDATE_FOLDER}/{update_file_lst[new_file_id]}",
                                         destination_directory=Local.INPUT_FOLDER)
            utils.move_file_to_directory(file_path=f"{Local.INPUT_FOLDER}/{file_name}",
                                         destination_directory=f"removed")
            utils.log("Initiating Load Sequence...", 'system')
            utils.log("Please Rerun 'Load Data' for the changes to take affect.", 'warning')
            DataBase().commit_changes()

        return True

    def delete_file_info(self):
        lst_names = DataBase().get_file_names()
        utils.log("Select the file you want to delete:")
        st = ""
        for idx, name in enumerate(lst_names):
            st += f"{idx} -> {utils.heb_conversion(name)}\n"
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
        DataBase().drop_file(selected_file)
        DataBase().commit_changes()

    def tag_data(self):
        """
        The function will check for untagged data and offer to tag it.
        """
        lst, desc = DataBase().get_untagged()
        df = pd.DataFrame(lst, columns=desc)
        df['Original_Name'] = df['Name']
        # To enable readible printing of data
        df['Name'] = df['Name'].apply(lambda x: utils.heb_conversion(x))
        df['Extra_Info'] = df['Extra_Info'].apply(lambda x: utils.heb_conversion(x))
        df['Source_file'] = df['Source_file'].apply(lambda x: utils.heb_conversion(x))
        if df.empty:
            utils.log("There is No data to tag, You are all good!", "system")
        else:
            utils.log(f"There are {len(lst)} untagged Transactions.\nChoose a category or create a new one.", "system")
            for _, row in df.iterrows():
                # Show the current untagged transaction - This is not a debug line!
                print(row.drop('Original_Name').to_markdown())
                res, description = utils.handle_categories()
                if res == "Skip":
                    utils.log("Skipped...", "system")
                    continue
                else:
                    DataBase().set_category(table=row['TableName'], id=row['ID'], category=res)
                    if len(description) > 1:
                        DataBase().set_transaction_description(description, row['TableName'], row['ID'])
                    utils.log("Tag saved.", "system")

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
                        utils.log("Updated the following:\n")
                        res_df['Name'] = res_df['Name'].apply(lambda x: utils.heb_conversion(x))
                        res_df['Extra_Info'] = res_df['Extra_Info'].apply(lambda x: utils.heb_conversion(x))
                        res_df['Source_file'] = res_df['Source_file'].apply(lambda x: utils.heb_conversion(x))
                        print(res_df.to_markdown())
                # -------------------------------------------------------
                DataBase().commit_changes()

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
        cards_df = SimpleMath.process_prices(df, desc).groupby("CardID").sum().reset_index()
        cards_df['Status'] = 'Not Verified'
        bank_df = DataBase().get_Bank_Transactions(Local.CHARGE_DAY + 1, t.month, t.year)
        for _, row_cs in cards_df.iterrows():
            for _, row_bt in bank_df.iterrows():
                x = round(row_bt['Out'], 2)
                y = round(row_cs['Final_Value'], 2)
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
        # utils.log(bank_df.to_markdown())
        utils.log(cards_df[['CardID', 'Final_Value', 'Status']].to_markdown())
        # ---------------------------------------------------------

        utils.log("NOT IMPLEMENTED - bank transaction below ", "warning")
        monthly_balance = DataBase().get_latest_Balance()

        spendings, description = DataBase().get_monthly_spendings(year=t.year, month=t.month)
        spendings_df = SimpleMath.process_prices(spendings, description)
        spendings_df = utils.remove_leumi(spendings_df)
        earnings, description = DataBase().get_monthly_earnings(year=t.year, month=t.month)
        earnings_df = SimpleMath.process_prices(earnings, description)
        earnings_df = utils.remove_leumi(earnings_df)
        end_monthly_balance = -1
        Graphics.plot_spendings(spendings_df)
        Graphics.plot_earnings(earnings_df)

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
        utils.log("General data is incorrect - its not taking into account both payment transactions and the remove of the leumi card.", 'warning')
        spendings_sum, earnings_sum = SimpleMath.get_monthly_shifted(shift=5)
        Graphics.plot_general(spendings_sum, earnings_sum)
        # ----- Cards
        Graphics.card_distribution(spendings_df)

        colors = [
            "#F5E1FF",  # Lavender
            "#F0FFF0",  # Honeydew
            "#FAF0E6",  # Linen
            "#FFF5E1",  # SeaShell
            "#E0FFFF",  # Light Cyan
            "#FFE4E1",  # Misty Rose
            "#F5F5DC",  # Beige
            "#F0E68C",  # Khaki
            "#E6E6FA",  # Lavender Mist
            "#FFE4B5"   # Moccasin
        ]

        colors = colors[:cards_df.shape[0]]
        cards_df['Color'] = colors
        utils.generate_html(t.month,
                            spendings_df,
                            earnings_df,
                            monthly_balance,
                            end_monthly_balance,
                            cards_df,
                            cat_dict)
        webbrowser.open('source\html\output.html')

    def validate(self):
        """
        The Function will validate the Balance created by the 'load_data' function by comparing the
        Total amount of credit at the month end with the sum of total transactions parsed for the same period.
        """
        from dateutil.relativedelta import relativedelta
        from datetime import datetime
        import pandas as pd

        def filter_unique_dates(visa_transactions: list[Tuple[datetime, float]]) -> pd.DataFrame:
            """
            The function will receive all visa charges in the db and return
            the total number of months to valdiate.
            """
            df = pd.DataFrame(visa_transactions, columns=['Date', 'Name', 'Amount', 'Balance'])
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df = df[df['Date'].dt.day == Local.CHARGE_DAY]
            df = df.groupby('Date').sum()
            df = df.drop('Balance', axis=1)
            return df

        visa_transactions = DataBase().get_visa_transactions()
        df = filter_unique_dates(visa_transactions)
        print(df)
        for row in df.iterrows():
            ds = (row[0] - relativedelta(months=1))
            amount = -row[1][0]
            s_amount, _ = SimpleMath.get_monthly_spendings(year=ds.year, month=ds.month)
            if abs(amount - s_amount) > 10:
                utils.log(f"\tValidation Failed for Charge conducted on {row[0]}.\n\t\tTotal Charge was {amount}, Transaction sum is {s_amount}", "warning")
                utils.warning_halt()
            else:
                utils.log(f"Validation for month {ds.month}/{ds.year} was Successful.\nThere is a {amount - s_amount} difference", 'system')

