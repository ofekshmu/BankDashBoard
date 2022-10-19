from enum import Enum


class fileType(Enum):
    visa = 1
    bank = 2
    unkown = 3


# TODO: figure how to abstract class in python
class File:
    def __init__(self, name: str):
        self.name = name
        self.date = 'Not read'
        self.data = None

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
