import pstats
from sourceV2.File import File


class Context:

    def __init__(self):
        pass

    def setFile(self, file: File):
        self.__file = file

    def render(self):
        if self.__file.read():
            raise ValueError()
        if self.__file.validate():
            raise ValueError()
        if self.__file.clean():
            raise ValueError()
        if self.__file.reduce():
            raise ValueError()
        if self.__file.insert:
            raise ValueError()
