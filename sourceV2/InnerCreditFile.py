from sourceV2.File import File
from Constants import InnerCredit


class InnerCreditFile(File):
    def __init__(self, name: str):
        super().__init__(name)
        self.constants = InnerCredit

        NAME = "לאומי-פירוט העסקאות בכרטיסי האשראי"
        DATE = 'B5'
    HEADERS = ["מספר הכרטיס",
               "תאריך העסקה",
               "שם בית העסק",
               "סכום העסקה",
               "מטבע העסקה",
               "סכום החיוב",
               "מטבע חיוב העסקה",
               "סוג העסקה",
               "פרטים",
               "תאריך החיוב"]

    INITIAL_ROW = 10  # This is the row with the table titles
    TABLE_SKIP = 3  # Number of rows between trasnactions

    def validate(self):
        """

        """
        pass

    def clean(self):
        """

        """
        pass

    def reduce(self):
        """

        """
        pass

    def insert(self):
        """

        """
        pass
