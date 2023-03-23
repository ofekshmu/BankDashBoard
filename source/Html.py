import webbrowser


class HtmlGenerator:

    def __init__(self, path: str = ""):
        self.path = ""
        self.template = ""
        self. css = """
<style>
    body {
        font-family: Arial, sans-serif;
    }

    .container {
        display: flex;
        justify-content: center;
        align-items: center;
    }

    .container img {
        margin: 10px;
        max-width: 50%;
        height: auto;
    }

    h1 {
        text-align: center;
    }
</style>
"""
    # def set_title(name: str):
    #     self
    # def add_style(self):

    # def open_file(self):
    #     webbrowser.open(self.path)
