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
                              "Adittional data field": (3, 0),
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
                              "Header row index": 4,
                              "Header col index": 0,
                              "Independent": False},

               "Isra-Card":  {"Format Name": "Isra-Card",
                              "Context": Context_class.Card,
                              "Identification method": Identification_Method.HEADERS,
                              "Identification data": None,
                              "Sortion method": Sortion_Method.BY_NAME_DATE,
                              "Sortion key": None,
                              "Adittional data field": (4, 2),
                              "Headers": ["תאריך רכישה",
                                          "שם בית עסק",
                                          "סכום עסקה",
                                          "מטבע מקור",
                                          "סכום חיוב",
                                          "מטבע לחיוב",
                                          "מספר שובר",
                                          "פירוט נוסף"],
                              "Double tables": True,
                              "Secondary Headers": [],
                              "Header row index": 6,
                              "Header col index": 0,
                              "Independent": True},

               "American-Express": {"Format Name": "American-Express",
                                    "Context": Context_class.Card,
                                    "Identification method": Identification_Method.HEADERS,
                                    "Identification data": None,
                                    "Sortion method": Sortion_Method.BY_NAME_DATE,
                                    "Sortion key": None,
                                    "Adittional data field": (1, 1),
                                    "Headers": ['תאריך רכישה',
                                                'תאריך חיוב',
                                                'שם בית עסק',
                                                'סכום מקורי',
                                                'מטבע מקור',
                                                'סכום חיוב',
                                                'מטבע לחיוב'],
                                    "Header row index": 6,
                                    "Header col index": 0,
                                    "Independent": True},

               "Leumi-Bank": {"Format Name": "Leumi-Bank",
                              "Context": Context_class.Bank,
                              "Identification method": Identification_Method.FILE_NAME,
                              "Identification data": "תנועות בחשבון",
                              "Sortion method": Sortion_Method.BY_NAME_DATE,
                              "Sortion key": None,
                              "Adittional data field": (7, 4),
                              "Headers": ['תאריך',
                                          'תאריך ערך',
                                          'תיאור',
                                          'אסמכתא',
                                          'בחובה',
                                          'בזכות',
                                          'היתרה בש"ח',
                                          'תאור מורחב',
                                          '  הערה'],    # Do not delete special character here!
                              "Header row index": 12,
                              "Header col index": 0,
                              "Independent": False},

               "BeinLeumi-Bank": {"Format Name": "BeinLeumi-Bank",
                                  "Context": Context_class.Bank,
                                  "Identification method": Identification_Method.FILE_NAME,
                                  "Identification data": "FibiSave",
                                  "Sortion method": Sortion_Method.BY_NAME_SERIAL,
                                  "Sortion key": None,
                                  "Adittional data field": None,
                                  "Headers": ['תאריך',
                                              'סוג פעולה',
                                              'תיאור',
                                              'אסמכתא',
                                              'זכות',
                                              'חובה',
                                              'תאריך ערך',
                                              'יתרה'],
                                  "Header row index": 1,
                                  "Header col index": 1,
                                  "Independent": False},

               "Leumi-Card6744": {"Format Name": "Leumi-Card6744",
                                  "Context": Context_class.Card,
                                  "Identification method": Identification_Method.CELL,
                                  "Identification data": ((4, 0), "פרוט עסקאות לכרטיס לאומי ויזה 6744"),
                                  "Sortion method": Sortion_Method.BY_NAME_DATE,
                                  "Sortion key": None,
                                  "Adittional data field": None,
                                  "Headers": ['תאריך העסקה',
                                              'שם בית העסק',
                                              'סכום העסקה',
                                              'סוג העסקה',
                                              'פרטים',
                                              'סכום חיוב'],
                                  "Header row index": 11,   # row starts from 1
                                  "Header col index": 0,
                                  "Independent": False}    # col starts from 0
               }

    EXTENTIONS = [".xls", ".xlsx", ".csv"]
