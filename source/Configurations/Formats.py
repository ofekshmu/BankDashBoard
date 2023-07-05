########################################################################
#                             Format File
#
#  Mind that on WINDOWS OS, all slashes are as follows: /
#
########################################################################
from enum import Enum


class Identification_Method(Enum):
    FILE_NAME = 1
    CELL = 2
    HEADERS = 3
    NONE = 4


class Sortion_Method(Enum):
    BY_NAME_SERIAL = 1
    BY_NAME_DATE = 2
    # ADD ANOTHER METHOD - BY INNER FILE DATE.


class Context_class(Enum):
    Card = 1
    Bank = 2


class Formats:

    FORMATS = {"Leumi-Max":  {"Format Name": "Leumi-Max",
                              "Context": Context_class.Card,
                              "Identification method": Identification_Method.FILE_NAME,
                              "Identification data": "transaction-details_export",
                              "Sortion method": Sortion_Method.BY_NAME_SERIAL,
                              "Sortion key": None,
                              "Headers": ["תאריך עסקה",
                                          "שם בית העסק",
                                          "קטגוריה",
                                          "4 ספרות אחרונות של כרטיס האשראי",
                                          "סוג עסקה",
                                          "סכום חיוב",
                                          "מטבע חיוב",
                                          "סכום עסקה מקורי",
                                          "מטבע עסקה מקורי",
                                          "תאריך חיוב",
                                          "הערות",
                                          "תיוגים",
                                          "מועדון הנחות",
                                          "מפתח דיסקונט",
                                          "אופן ביצוע ההעסקה",
                                          'שער המרה ממטבע מקור/התחשבנות לש"ח'],
                              "Header row index": 4},
     
               "Isra-Card":  {"Format Name": "Isra-Card",
                              "Context": Context_class.Card,
                              "Identification method": Identification_Method.FILE_NAME,
                              "Identification data": "Export_",
                              "Sortion method": Sortion_Method.BY_NAME_DATE,
                              "Sortion key": None,
                              "Headers": ["תאריך רכישה",
                                          "שם בית עסק",
                                          "סכום עסקה",
                                          "מטבע מקור",
                                          "סכום חיוב",
                                          "מטבע לחיוב",
                                          "מספר שובר",
                                          "פירוט נוסף"],
                              "Header row index": 6},

               "Leumi-Bank": {"Format Name": "Leumi-Bank",
                              "Context": Context_class.Bank,
                              "Identification method": Identification_Method.FILE_NAME,
                              "Identification data": "תנועות בחשבון",
                              "Sortion method": Sortion_Method.BY_NAME_DATE,
                              "Sortion key": None,
                              "Headers": ['תאריך',
                                          'תאריך ערך',
                                          'תיאור',
                                          'אסמכתא',
                                          'בחובה',
                                          'בזכות',
                                          'היתרה בש"ח',
                                          'תאור מורחב',
                                          '  הערה'],
                              "Header row index": 12},

               "Leumi-Card": {"Format Name": "Leumi-Card",
                              "Context": Context_class.Card,
                              "Identification method": Identification_Method.FILE_NAME,
                              "Identification data": "לאומי-פירוט העסקאות בכרטיסי האשראי",
                              "Sortion method": Sortion_Method.BY_NAME_DATE,
                              "Sortion key": None,
                              "Headers": ['מספר הכרטיס',
                                          'תאריך העסקה',
                                          'שם בית העסק',
                                          'סכום העסקה',
                                          'מטבע העסקה',
                                          'סכום החיוב',
                                          'מטבע חיוב העסקה',
                                          'סוג העסקה',
                                          'פרטים',
                                          'תאריך החיוב'],
                              "Header row index": 11}
               }

    EXTENTIONS = [".xls", ".xlsx", ".csv"]
