from enum import Enum


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

    def read(self):
        """

        """
        pass
