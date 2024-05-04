from AppManager import AppManager
from src_utils.utils import utils
from datetime import datetime
import atexit
from src_utils.ExcelReader import ExcelManager


# Define a function to be called when the application exits
def cleanup_on_exit():
    """
    This function kills all excel applications before existing to prevent possible issues...
    """
    # Your cleanup code here
    utils.log("Cleaning up before exiting...", 'system')
    ExcelManager().close_and_kill_excel()

def main():
    atexit.register(cleanup_on_exit)
    # -----------------------------------------
    utils.log(msg=f"\n{40*'#'} " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + f" {40*'#'}")
    myApp = AppManager()
    myApp.menu()

if __name__ == "__main__":
    main()
