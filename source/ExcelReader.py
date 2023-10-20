import xlwings as xw


class ExcelManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ExcelManager, cls).__new__(cls)
            cls._instance.app = xw.App(visible=False)
            cls._instance.active_sheet = None

        return cls._instance

    def open_sheet(self, file_path):
        try:
            if self.active_sheet is None:
                workbook = self.app.books.open(file_path)
                sheet = workbook.sheets[0]  # Read the first sheet in the Excel file
                self.active_sheet = sheet
            return True
        except Exception as e:
            print(f"Error opening file or sheet: {str(e)}")
            return False


    def set_active_sheet(self, file_path):
        if self.active_sheet is not None:
            self.active_sheet.book.close()
            self.active_sheet = None  # Close the previous active sheet

        if not self.open_sheet(file_path):
            print(f"Error setting active sheet to '{file_path}': Sheet not found")

    def close_and_kill_excel(self):
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
        if not self.open_sheet(self.active_sheet):
            print(f"Error setting active sheet to '{file_path}': Sheet not found")
        if self.active_sheet is not None:
            return self.active_sheet[row_idx - 1: row_idx - 1 + row_count, col_idx: col_idx + col_count].value


if __name__ == "__main__":
    excel_manager = ExcelManager()

    file_path = r"C:\Users\ofeks\OneDrive\Work\Projects\Personal\BankProject\Inputs01\isra"
    file_1 = "Export_11_2023.xls"
    file_2 = "Export_10_2023.xls"
    excel_manager.set_active_sheet(f"{file_path}\{file_1}")

    print(excel_manager.read_sheet(1, 15, 1, 15))
    print(excel_manager.read_sheet(1, 3, 1, 3))
    excel_manager.set_active_sheet(f"{file_path}\{file_2}")
    print(excel_manager.read_sheet(1, 5, 1, 5))

    excel_manager.close_and_kill_excel()
