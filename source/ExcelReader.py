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
            return self.active_sheet
        except Exception as e:
            print(f"Error opening file or sheet: {str(e)}")
            return None

    def read_values(self, start_cell, end_cell):
        if self.active_sheet is not None:
            try:
                data_range = self.active_sheet.range(start_cell, end_cell)
                return data_range.value
            except Exception as e:
                print(f"Error reading data from sheet '{self.active_sheet}': {str(e)}")
            finally:
                self.close_and_kill_excel()

        return None

    def set_active_sheet(self, file_path):
        if self.active_sheet is not None:
            self.active_sheet = None  # Close the previous active sheet

        if not self.open_sheet(file_path):
            print(f"Error setting active sheet to '{file_path}': Sheet not found")

    def close_and_kill_excel(self):
        if self.active_sheet is not None:
            self.active_sheet.book.close()
            self.app.quit()
            self.active_sheet = None


if __name__ == "__main__":
    excel_manager = ExcelManager()

    file_path = r"C:\Users\ofeks\OneDrive\Work\Projects\Personal\BankProject\Inputs01\isra"
    file_1 = "Export_11_2023.xls"
    excel_manager.set_active_sheet(f"{file_path}\{file_1}")
    data = excel_manager.read_values("A1", "B3")
    if data:
        for row in data:
            print(row)
