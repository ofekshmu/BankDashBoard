import xlwings as xw
from queuebykey import SpecialQueue

MAX_ACTIVE_SHEETS = 5


class ExcelManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            max_active_sheets = 5
            cls._instance = super(ExcelManager, cls).__new__(cls)
            cls._instance.app = xw.App(visible=False)
            cls._instance.queue = SpecialQueue(MAX_ACTIVE_SHEETS)
            cls._instance.active_sheet = None

        return cls._instance

    def __open_sheet(self, file_path):
        """
        A private function, ment for opening the first sheet in an excel file.
        """
        try:
            workbook = self.app.books.open(file_path)
            sheet = workbook.sheets[0]  # Read the first sheet in the Excel file
            self.active_sheet = sheet
            return sheet
        except Exception as e:
            raise ValueError(f"Error opening file or sheet: {str(e)}")

    def set_active_sheet(self, file_path):
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

    def close_and_kill_excel(self):
        """
        Call this function at the end of the App in order to close all background running process.
        """
        if self.active_sheet is not None:
            self.active_sheet.book.close()
            self.app.quit()
            self.active_sheet = None

    def read_sheet(self, row_idx: int, row_count: int, col_idx: int, col_count: int) -> list:
        """
        The function read the a table like structure out of an excel file names @file_name
        The indexes are inclusive, meaning that data will be read from row_idx until row_idx + row_count
        including the values of the border indexes.
        """
        if self.active_sheet is None:
            print(f"Error setting active sheet to '{file_path}': Sheet not found")
        if self.active_sheet is not None:
            return self.active_sheet[row_idx - 1: row_idx - 1 + row_count, col_idx: col_idx + col_count].value


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
