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


class Sortion(Enum):
    BY_NAME_SERIAL = 1
    BY_NAME_DATE = 2


class Context(Enum):
    Card = 1
    Bank = 2


class Formats:

    FORMATS = [{"Format Name": "Leumi-Bank",
                "Context": Context.Card,
                "Identification method": None,
                "Identification data": None,
                "Sortion method": None,
                "Sortion key": None,
                "Headers": [],
                "Header row index": None}
               ]

    EXTENTIONS = [".xls", ".xlsx", ".csv"]
