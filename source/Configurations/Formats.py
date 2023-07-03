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

    FORMATS = {"Leumi-Bank": {"Format Name": "Leumi-Bank",
                              "Context": Context_class.Card,
                              "Identification method": Identification_Method.NONE,
                              "Identification data": None,
                              "Sortion method": None,
                              "Sortion key": None,
                              "Headers": [],
                              "Header row index": None},
     
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
                              "Header row index": 6}
               }

    EXTENTIONS = [".xls", ".xlsx", ".csv"]
