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

class Location(Enum):
    FILE_NAME_DATE = 1
    INNER_CELL = 2

class Sortion_Method(Enum):
    BY_NAME_SERIAL = 1
    BY_NAME_DATE = 2
    # ADD ANOTHER METHOD - BY INNER FILE DATE.


class Context_class(Enum):
    Card = 1
    Bank = 2


class Formats:

    FORMATS = {
               "Isra-Card":  {"Format Name": "Isra-Card",
                                    "Context": Context_class.Card,
                                    "Identification method": Identification_Method.CELL,
                                    "Identification data": ((4, 0), 'גולד - מסטרקארד'),
                                    "Sortion method": Sortion_Method.BY_NAME_DATE,
                                    "Sortion key": None,
                                    "Card number cell": (4, 0),
                                    "Card string format" : None,
                                    "Adittional data field": (4, 2),
                                    "TimeStamp": Location.FILE_NAME_DATE,
                                    "TimeStamp Format": r'(\d{1,2})_(\d{4})' ,
                                    "TimeStamp location": None,
                                    "Headers": ["תאריך רכישה",
                                                "שם בית עסק",
                                                "סכום עסקה",
                                                "מטבע מקור",
                                                "סכום חיוב",
                                                "מטבע לחיוב",
                                                "מספר שובר",
                                                "פירוט נוסף"],
                                    "Double tables": True,
                                    "Secondary Headers": ["תאריך רכישה",
                                                            "תאריך חיוב",
                                                            "שם בית עסק",
                                                            "סכום מקורי",
                                                            "מטבע מקור",
                                                            "סכום חיוב",
                                                            "מטבע לחיוב"],
                                    "Header row index": 6,
                                    "Header col index": 0,
                                    "Independent": True,
                                    "flip": False,
                                    "associated": [],
                                    "Transaction Names": {"4046" : ["4046 - ישראכרט", '4046 - ישראכרט בע"מ'],
                                                           "2922" : ['ישראכרט בע"מ']}
                            },

               "Isra-Card-2026":  {"Format Name": "Isra-Card-2026",
                                    "Context": Context_class.Card,
                                    "Identification method": Identification_Method.HEADERS,
                                    "Identification data": None,
                                    "Sortion method": Sortion_Method.BY_NAME_DATE,
                                    "Sortion key": None,
                                    "Card number cell": (5, 0),
                                    "Card string format" : r"\d{4}$",
                                    "Adittional data field": None,
                                    "TimeStamp": Location.FILE_NAME_DATE,
                                    "TimeStamp Format": r'\d{4}_(\d{2})_(\d{4})' ,
                                    "TimeStamp location": None,
                                    "Headers": ["תאריך רכישה",
                                                "שם בית עסק",
                                                "סכום עסקה",
                                                "מטבע עסקה",
                                                "סכום חיוב",
                                                "מטבע חיוב",
                                                "מס' שובר",
                                                "פירוט נוסף"],
                                    "Double tables": False,
                                    "Secondary Headers": [],
                                    "Header row index": 10,
                                    "Header col index": 0,
                                    "Independent": True,
                                    "flip": False,
                                    "associated": [],
                                    "Transaction Names": {"4046" : ["4046 - ישראכרט", '4046 - ישראכרט בע"מ'],
                                                           "2922" : ['ישראכרט בע"מ']}
                            },

               "American-Express": {"Format Name": "American-Express",
                                    "Context": Context_class.Card,
                                    "Identification method": Identification_Method.CELL,
                                    "Identification data": ((4, 0), "אמריקן אקספרס זהב - 1565"),
                                    "Sortion method": Sortion_Method.BY_NAME_DATE,
                                    "Sortion key": None,
                                    "Card number cell": (4, 0),
                                    "Card string format" : None,
                                    "Adittional data field": (4, 2),
                                    "TimeStamp": Location.FILE_NAME_DATE,
                                    "TimeStamp Format": r'_(\d+)_(\d{4})' ,
                                    "TimeStamp location": None,
                                    "Headers": ["תאריך רכישה",
                                                "שם בית עסק",
                                                "סכום עסקה",
                                                "מטבע מקור",
                                                "סכום חיוב",
                                                "מטבע לחיוב",
                                                "מספר שובר",
                                                "פירוט נוסף"],
                                    "Double tables": True,
                                    "Secondary Headers": ["תאריך רכישה",
                                                            "תאריך חיוב",
                                                            "שם בית עסק",
                                                            "סכום מקורי",
                                                            "מטבע מקור",
                                                            "סכום חיוב",
                                                            "מטבע לחיוב"],
                                    "Header row index": 6,
                                    "Header col index": 0,
                                    "Independent": True,
                                    "flip": False,
                                    "associated": [],
                                    "Transaction Names": {"1565" : ["פרימיום אקספרס"]}
                                },

                "Cal":          {"Format Name": "Cal",
                                "Context": Context_class.Card,
                                "Identification method": Identification_Method.HEADERS,
                                "Identification data": None,
                                "Sortion method": Sortion_Method.BY_NAME_DATE,
                                "Sortion key": None,
                                "Card number cell": (1, 0),
                                "Card string format" : r"\d{4}$",
                                "Adittional data field": (3, 0),
                                "TimeStamp": Location.FILE_NAME_DATE,
                                "TimeStamp Format": r"\d{2}\.(\d{2})\.(\d{2})" ,
                                "TimeStamp location": (3, 0),
                                "Headers": ["תאריך\nעסקה",
                                            "שם בית עסק",
                                            "סכום\nעסקה",
                                            "סכום\nחיוב",
                                            "סוג\nעסקה",
                                            "ענף",
                                            "הערות"],
                                "Double tables": False,
                                "Secondary Headers": [],
                                "Header row index": 4,
                                "Header col index": 0,
                                "Independent": True,
                                "flip": False,
                                "associated": [],
                                "Transaction Names": {"3843" : ['עפ"י הרשאה כאל'],
                                                       "4437" : ['עפ"י הרשאה כאל']}},

               "BeinLeumi-Bank-Date-Range": {"Format Name": "BeinLeumi-Bank-Date-Range",
                                  "Context": Context_class.Bank,
                                  "Identification method": Identification_Method.HEADERS,
                                  "Identification data": None,
                                  "Sortion method": Sortion_Method.BY_NAME_SERIAL,
                                  "Sortion key": None,
                                  "Adittional data field": None,
                                  "Headers": ['יתרה',
                                              'תאריך ערך',  #1
                                              'זכות',       #2
                                              'חובה',       #3
                                              'תאור',       #4
                                              'אסמכתא',     #5
                                              'סוג פעולה',  #6
                                              'תאריך'],     #7
                                  "Double tables": False,
                                  "Secondary Headers": [],
                                  "Header row index": 6,
                                  "Header col index": 1,
                                  "Independent": False,
                                  "flip": True,
                                  "associated": ["BeinLeumi-Bank"],
                                  "Transaction Names": {}},

               "BeinLeumi-Bank": {"Format Name": "BeinLeumi-Bank",
                                  "Context": Context_class.Bank,
                                  "Identification method": Identification_Method.HEADERS,
                                  "Identification data": None,
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
                                  "Double tables": False,
                                  "Secondary Headers": [],
                                  "Header row index": 2,
                                  "Header col index": 1,
                                  "Independent": False,
                                  "flip": False,
                                  "associated": ["BeinLeumi-Bank-Date-Range"],
                                  "Transaction Names": {}},

               "Leumi-Max":  {"Format Name": "Leumi-Max",
                              "Context": Context_class.Card,
                              "Identification method": Identification_Method.FILE_NAME,
                              "Identification data": "transaction-details_export",
                              "Sortion method": Sortion_Method.BY_NAME_SERIAL,
                              "Sortion key": None,
                              "Adittional data field": (3, 0),
                              "Card number cell": (2, 0),
                              "Card string format": None,
                              "TimeStamp": Location.INNER_CELL,
                              "TimeStamp Format": r'(\d{2})/(\d{4})' ,
                              "TimeStamp location": (3, 0),
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
                              "Double tables": False,
                              "Secondary Headers": [],
                              "Header row index": 4,
                              "Header col index": 0,
                              "Independent": True,
                              "flip": False,
                              "associated": [],
                              "Transaction Names": {}},

               }

    EXTENTIONS = [".xls", ".xlsx", ".csv"]
