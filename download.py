from re import sub, match
from time import sleep
from shutil import copyfileobj
from typing import List
from pathlib import Path
from requests import get
from urllib.request import urljoin
from urllib.error import HTTPError
from bs4 import BeautifulSoup
from bs4.element import Tag
from alive_progress import alive_bar
from typing import overload, Optional


class Item:
    title: str
    name: str

    def __str__(self) -> str:
        return self.title

    def __repr__(self) -> str:
        return self.name

    @staticmethod
    def sanitize(text: str) -> str:
        return sub(r"\W", "", text)


class Book(Item):
    title = "The Book of Life"
    url = "https://theschooloflife.com/thebookoflife/"
    path = Path(__file__).parent / "source"
    parts: List["Part"] = []

    @classmethod
    def download(cls) -> None:
        with alive_bar() as bar:
            for html in fetch(cls.url)(class_="nav-main__sub-rollover"):
                if html.has_attr("onmouseover"):
                    cls.parts.append(Part(html.text))
            for part in cls.parts:
                bar(part.title)
                part.download()
        chapters = [
            chapter
            for part in cls.parts
            for section in part.sections
            for chapter in section.chapters
        ]
        with alive_bar(len(chapters)) as bar:
            for part in cls.parts:
                for section in part.sections:
                    for chapter in section.chapters:
                        if not (chapter.path / "text.rst").exists():
                            chapter.download()
                            chapter.write()
                            sleep(10)
                        bar(chapter.title)
                    section.write()
                part.write()


class Part(Item):
    sections: List["Section"] = []

    def __init__(self, title: str):
        self.title = title
        self.name = self.sanitize(title)
        self.url = urljoin(Book.url, f"category/{title.lower()}/?index")
        self.path = Book.path / self.name

    def download(self) -> None:
        html = fetch(self.url)
        self.sections = [Section(section, self) for section in html.find_all("section")]
        for section in self.sections:
            continue
            section.download()

    def write(self) -> None:
        index = (
            f".. _{self.name}\n\n"
            f"{self.title}\n{'='*len(self.title)}\n\n"
            ".. toctree::\n"
        )
        for section in self.sections:
            index += f"   {section.name}/index\n"
        with open(self.path / "index.rst", "w") as output:
            output.write(index)


class Section(Item):
    chapters: List["Chapter"] = []

    def __init__(self, html: Tag, part: Part):
        self.title = html.div.text
        self.part = part
        self.name = self.sanitize(self.title)
        self.path = part.path / self.name
        self.chapters = [Chapter(chapter, self) for chapter in html.find_all("li")]

    def write(self) -> None:
        index = f".. _{self.name}\n\n"
        index += f"{self.title}\n{'='*len(self.title)}\n\n.. toctree::\n"
        for chapter in self.chapters:
            index += f"   {chapter.name}/text\n"
        with open(self.path / "index.rst", "w") as output:
            output.write(index)


class Chapter(Item):
    headings: List[str] = [r"^\n+\.", r"^\(?[iIvVxX]+\)?\.?"]

    def __init__(self, html: Tag, section: Section):
        self.title = html(class_="title")[0].text
        self.name = self.sanitize(self.title)
        self.section = section
        self.url = html.a.attrs["href"]
        self.path = section.path / self.name

    def download(self) -> None:
        try:
            self.html = fetch(self.url)
        except HTTPError as error:
            message = f"{self.url}: {error.code} - {error.reason}"
            raise HTTPError(self.url, error.code, message, None, None)

    def write(self) -> None:
        images = 0
        caption = False
        text = f"{self.title}\n{'='*len(self.title)}\n\n"
        self.path.mkdir(parents=True, exist_ok=True)
        for html in self.html.find(class_="old-wrapper").children:
            if not isinstance(html, Tag):
                continue
            elif {"responsive-container", "addtoany_content"} & set(
                html.attrs.get("class", [])
            ):
                break
            elif html.img:
                images += 1
                path = self.path / f"{images}.jpg"
                if not path.exists():
                    try:
                        fetch(html.img.attrs["src"], path)
                    except Exception:
                        print(f"Failed to fetch image {html.img.attrs.get('src')}")
                        continue
                text += f"\n.. figure:: {images}.jpg\n   :figwidth: 100 %\n\n"
                caption = True
            elif html.p or html.em or html.name in ["em", "p"]:
                for heading in self.headings:
                    if match(heading, html.text):
                        text += html.text + "\n" + "-" * len(html.text)
                        caption = False
                        continue
                if caption and len(html.text) < 100:
                    text += "   "
                text += html.text.strip() + "\n\n"
                caption = False
        with open(self.path / "text.rst", "w") as output:
            output.write(text)


@overload
def fetch(url: str) -> BeautifulSoup:
    ...


@overload
def fetch(url: str, path: Path = None) -> None:
    ...


def fetch(url: str, path: Path = None) -> Optional[BeautifulSoup]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/35.0.1916.47 Safari/537.36"
    }
    if path:
        response = get(url, headers=headers, stream=True)
        with open(path, "wb") as output:
            copyfileobj(response.raw, output)
        return None
    else:
        html = get(url, headers=headers)
        if html.status_code == 503:
            raise HTTPError(url, 503, "Rate limited", None, None)
        return BeautifulSoup(html.text, "html.parser")


if __name__ == "__main__":
    Book.download()
