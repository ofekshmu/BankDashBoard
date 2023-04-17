from Parser import Parser
from BankTransactionsFile import BankTransactionsFile
from InnerCreditFile import InnerCreditFile
from OuterCreditFile import OuterCreditFile
from Context import Context
from Constants import InnerCredit, BankTransactions, OuterCredit, Local
from src_utils.utils import utils
from database import DataBase
from front.Graphics import Graphics
from src_utils.calculations import SimpleMath
import webbrowser
from tqdm import tqdm
from typing import Tuple


class AppManager:

    def __init__(self):
        self.parser = Parser()

    def menu(self):
        print("""
                Hello Ofek!
                What would you like to do today?

                1. Update/Parse files
                2. Show statistics
                3. Delete file information
                4. Validate
                5. Exit
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
                exit()
            case _:
                print("Please insert a valid number.")

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
                continue
            if not (int(answer) > 0 and int(answer) < len(lst_names)):
                continue
            answer = int(answer)
            break

        selected_file = lst_names[answer]
        DataBase().drop_file(selected_file)

    def tag_data(self):
        """
        The function will check for untagged data and offer to tag it.
        """
        lst = DataBase().get_untagged()
        if len(lst) == 0:
            utils.log("There is No data to tag, You are all good!", "system")
        else:
            utils.log(f"There are {len(lst)} untagged Transactions.\nChoose a category or create a new one.", "system")
            for idx, t in enumerate(lst, start=1):
                t_id = t[1]
                t_name = utils.heb_conversion(t[3])
                t_table = t[0]
                t_amount = t[4]
                extra_info = "" if t[5] is None else utils.heb_conversion(t[5])
                t_date = t[2]
                utils.log(f"no'{idx}/{len(lst)} {20*'-'}", "system")
                utils.log(f"id: {t_id}\nName: {t_name}\nInfo: {extra_info}\nAmount: {t_amount}\nDate: {t_date}\nTable: {t_table}", "system")

                res = utils.handle_categories()
                if res == "Skip":
                    utils.log("Skipped...", "system")
                else:
                    DataBase().set_category(table=t_table, id=t_id, category=res)
                    DataBase().commit_changes()
                    utils.log("Tag saved.", "system")

    def load_data(self):
        context = Context()
        Context.counter = 0
        while next(self.parser):
            name, type = self.parser.get_next()

            if DataBase().is_file_exists(name):
                utils.log(f'Skipping {utils.name_he(name)}...', 'system')
                continue

            if type == BankTransactionsFile:
                context.setFile(BankTransactionsFile(name,
                                                     BankTransactions.DATE,
                                                     BankTransactions.BANK_NUM_LOC,
                                                     BankTransactions.HEADERS,
                                                     BankTransactions.INITIAL_ROW))
            elif type == InnerCreditFile:
                context.setFile(InnerCreditFile(name,
                                                InnerCredit.DATE_LOC,
                                                InnerCredit.BANK_NUM_LOC,
                                                InnerCredit.HEADERS,
                                                InnerCredit.INITIAL_ROW,
                                                InnerCredit.TABLE_SKIP))
            elif type == OuterCreditFile:
                context.setFile(OuterCreditFile(name,
                                                OuterCredit.HEADERS,
                                                OuterCredit.CARD_CELL,
                                                OuterCredit.INITIAL_ROW))
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

        # -----

        monthly_balance = SimpleMath.generate_monthly_balance()
        s_amount, spendings = SimpleMath.get_monthly_spendings(year=t.year, month=t.month)
        e_amount, earnings = SimpleMath.get_monthly_earnings(year=t.year, month=t.month)
        end_monthly_balance = monthly_balance - s_amount
        Graphics.plot_earnings(earnings)
        Graphics.plot_spendings(spendings)
        data = SimpleMath.gas_info()
        gas_stats = Graphics.plot_gas(data)
        Graphics.plot_monthly_gas(data)
        
        df_general = SimpleMath.general_info(earnings=DataBase().get_all_transactions(shift=7),
                                             spendings=DataBase().get_all_transactions(shift=7, income=False))
        
        Graphics.plot_general(df_general)

        utils.generate_html(spendings,
                            earnings,
                            monthly_balance,
                            end_monthly_balance,
                            gas_stats)
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

