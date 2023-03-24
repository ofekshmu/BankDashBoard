from Parser import Parser
from BankTransactionsFile import BankTransactionsFile
from InnerCreditFile import InnerCreditFile
from OuterCreditFile import OuterCreditFile
from Context import Context
from Constants import InnerCredit, BankTransactions, OuterCredit
from src_utils.utils import utils
from database import DataBase
from front.Graphics import Graphics
import copy


class AppManager:

    def __init__(self):
        self.parser = Parser()

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

    def plot_data(self):
        from datetime import datetime
        now = datetime.now()
        Graphics.basic_plots(year=now.year,
                             month=now.month)
