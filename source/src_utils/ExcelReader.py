try:
    import xlwings as xw
    _XLWINGS_AVAILABLE = True
except ImportError:
    xw = None  # type: ignore
    _XLWINGS_AVAILABLE = False
import threading
from src_utils.queuebykey import SpecialQueue
from typing import Union

MAX_ACTIVE_SHEETS = 1

# Each thread gets its own ExcelManager instance so that COM objects
# (which are apartment-threaded on Windows) are never shared across threads.
_tls = threading.local()


class ExcelManager:
    # Legacy class-level attributes kept for any code that still references them
    # directly, but the real state lives in _tls.
    _instance = None
    dead = True

    def __new__(cls):
        inst = getattr(_tls, 'instance', None)
        dead = getattr(_tls, 'dead', True)
        if inst is None or dead:
            # Initialize COM for this thread before creating the Excel app.
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
            inst = super(ExcelManager, cls).__new__(cls)
            inst.app = xw.App(add_book=False, visible=False)
            inst.queue = SpecialQueue(MAX_ACTIVE_SHEETS)
            inst.active_sheet = None
            _tls.instance = inst
            _tls.dead = False
            # Keep class-level ref in sync for legacy direct accesses
            cls._instance = inst
            cls.dead = False
        return inst

    def __open_sheet(self, file_path):
        """
        A private function, ment for opening the first sheet in an excel file.
        Suppresses Excel's "file in use" dialog so it never blocks the user.
        """
        import os
        fname = os.path.basename(file_path)

        # Suppress all Excel alert dialogs before opening.
        try:
            self.app.display_alerts = False
        except Exception:
            pass

        workbook = None
        try:
            workbook = self.app.books.open(file_path)
        except Exception:
            # File already open in this or another Excel instance — reuse it.
            for book in self.app.books:
                try:
                    if os.path.basename(book.fullname).lower() == fname.lower():
                        workbook = book
                        break
                except Exception:
                    continue

        try:
            self.app.display_alerts = True
        except Exception:
            pass

        if workbook is None:
            raise ValueError(f"Cannot open file (in use or inaccessible): {file_path}")

        sheet = workbook.sheets[0]
        self.active_sheet = sheet
        return sheet

    #@add_root
    def set_active_sheet(self, file_path) -> 'ExcelManager':
        """
        The function changes the currently active sheet. An active sheet is a sheet which all actions are conducted
        on at a given time. While there is only 1 active sheet at a time. The app permits running MAX_ACTIVE_SHEETS in parralell.
        This was implemanted to reduce the closing and opening times between switched files. this number can be changed.
        Closing files is done in an LRU mannaer.
        """
        if self.queue.is_present(file_path):
            self.active_sheet = self.queue.access_by_key(file_path)
        else:
            if self.queue.is_full():
                _, removed_sheet = self.queue.pop()
                removed_sheet.book.close()
            self.queue.push(file_path, self.__open_sheet(file_path))

        return self

    def close_and_kill_excel(self):
        """
        Call this function at the end of the App in order to close all background running process.
        """
        if self.active_sheet is not None:
            try:
                self.active_sheet.book.close()
            except Exception:
                pass
        try:
            self.app.kill()
        except Exception:
            pass
        self.active_sheet = None
        # Clear the thread-local instance so the next call creates a fresh one.
        _tls.instance = None
        _tls.dead = True
        ExcelManager._instance = None
        ExcelManager.dead = True
        # Note: do NOT call CoUninitialize — COM should stay initialized for the
        # thread's lifetime so subsequent xw.App() calls succeed without errors.

    def read_sheet(self, row_idx: int, row_count: int, col_idx: int, col_count: int, type: str = "value") -> list:
        """
        The function read the a table like structure out of an excel file names @file_name
        The indexes are inclusive, meaning that data will be read from row_idx until row_idx + row_count
        including the values of the border indexes.
        """
        if type not in ["value", "format"]:
            raise ValueError("Type must be either 'value' or 'format'")
        if self.active_sheet is None:
            print(f"Error setting active sheet to '{self.active_sheet}': Sheet not found")
        if self.active_sheet is not None and type == "value":
            return self.active_sheet[row_idx - 1: row_idx - 1 + row_count, col_idx: col_idx + col_count].value
        else:
            range_obj = self.active_sheet[row_idx - 1: row_idx - 1 + row_count, col_idx: col_idx + col_count]
            formats = [[cell.number_format for cell in row] for row in range_obj.rows]
            return formats

    def read_value(self, location: tuple):
        if self.active_sheet is None:
            raise ValueError(f"Error setting active sheet to '{self.active_sheet}': Sheet not found")

        return self.active_sheet[location].value

    @staticmethod
    def extract_currency_from_number_format(number_format: str, default: str = "₪") -> str:
        """
        Extracts the currency symbol from an Excel number format string.
        For example: '[$€] #,##0.00' -> '€', '[$₪] #,##0.00' -> '₪'.
        Returns default if no currency symbol is found.
        """
        import re
        match = re.search(r'\[\$(.+?)\]', number_format)
        return match.group(1) if match else default

    def read_cell(self, row: int, col: int) -> Union[str, None]:
        '''
        Returns the value of the cell with indexes [row, col]
        Function returns either string answer or None if the cell is empty.
        '''
        if row > 0 and col >= 0:
            return self.active_sheet[f'{chr(65 + col)}{row}'].value
        else:
            # TODO should reedit header validation in src_utils in order to enable the import of utils here.
            print(f"Invalid indexes -> ({row}, {col})", "error")
            return ""

# if __name__ == "__main__":
#     excel_manager = ExcelManager()

#     file_path = r"C:\Users\ofeks\OneDrive\Work\Projects\Personal\BankProject\Inputs01\isra"
#     file_1 = "Export_11_2023.xls"
#     file_2 = "Export_10_2023.xls"
#     excel_manager.set_active_sheet(f"{file_path}\{file_1}")

#     print(excel_manager.read_sheet(1, 15, 1, 15))
#     print(excel_manager.read_sheet(1, 3, 1, 3))
#     excel_manager.set_active_sheet(f"{file_path}\{file_2}")
#     print(excel_manager.read_sheet(1, 5, 1, 5))

#     excel_manager.close_and_kill_excel()
