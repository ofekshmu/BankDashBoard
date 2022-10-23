from Constants import log
from sourceV2.File import File


class Context:

    file: File

    def setFile(self, file: File = None) -> None:
        if file is not None:
            self.file = file
        else:
            self.file = File('Default')

    def render(self) -> bool:
        log(f'Reading {self.file.name}...', category='system')
        if not self.file.load():
            log(f'Failed reading file: {self.file.name}', category='error')
            return False
        if self.__file.validate():
            raise ValueError()
        if self.__file.clean():
            raise ValueError()
        if self.__file.reduce():
            raise ValueError()
        if self.__file.insert:
            raise ValueError()

        return True