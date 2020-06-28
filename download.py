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


class DownloadError(Exception):
    pass


class Item:
    title: str
    path: Path
    url: str

    def __str__(self) -> str:
        return self.title

    def __repr__(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        return sub(r"\W", "", self.title)

    def download(self) -> None:
        if not self.url:
            return
        try:
            self.html = fetch(self.url)
        except DownloadError:
            self.html = None
            return
        self.path.mkdir(parents=True, exist_ok=True)
        with open(self.path / 'page.html', 'w') as output:
            output.write(self.html.prettify())
        sleep(10)

    def load(self) -> None:
        path = self.path / 'page.html'
        if not path.exists():
            self.download()
        else:
            self.html = BeautifulSoup(path.read_text(), 'html.parser')


class Book(Item):
    title = "The Book of Life"
    url = "https://theschooloflife.com/thebookoflife/"
    path = Path(__file__).parent / "source"
    parts: List["Part"] = []

    def load(self) -> None:
        super().load()
        for html in self.html(class_="nav-main__sub-rollover"):
            if html.has_attr("onmouseover"):
                self.parts.append(Part(html.text.strip()))


class Part(Item):
    sections: List["Section"] = []

    def __init__(self, title: str):
        self.title = title
        self.url = urljoin(Book.url, f"category/{title.lower()}/?index")
        self.path = Book.path / self.name

    def load(self) -> None:
        super().load()
        self.sections = [Section(section, self) for section in self.html.find_all("section")]

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
    headings: List[str] = [r"^\d+\.", r"^\(?[iIvVxX]+\)?\.?", r"^\W \w+"]

    def __init__(self, html: Tag, section: Section):
        self.title = html(class_="title")[0].text.strip()
        self.section = section
        self.url = html.a.attrs["href"]
        self.path = section.path / self.name

    def write(self) -> None:
        if not self.html:
            return
        images = 0
        caption = False
        text = f"{self.title}\n{'='*len(self.title)}\n\n"
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
                    except (DownloadError, KeyError):
                        continue
                text += f"\n.. figure:: {images}.jpg\n   :figwidth: 100 %\n\n"
                caption = True
            elif html.p or html.em or html.name in ["em", "p"]:
                html_text = html.text.strip()
                for heading in self.headings:
                    if match(heading, html_text) and len(html_text) < 50:
                        text += f'{html_text}\n{"-"*len(html_text)}\n\n'
                        break
                else:
                    if caption and len(html_text) < 100:
                        text += "   "
                    text += html_text + "\n\n"
                caption = False
        with open(self.path / "text.rst", "w") as output:
            output.write(text)
        del self.html


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
    try:
        if path:
            response = get(url, headers=headers, stream=True)
            response.raise_for_status()
            with open(path, "wb") as output:
                copyfileobj(response.raw, output)
            return None
        else:
            html = get(url, headers=headers)
            html.raise_for_status()
            if html.status_code == 503:
                raise HTTPError(url, 503, "Rate limited", None, None)
            return BeautifulSoup(html.text, "html.parser")
    except HTTPError as error:
        print(f"{url} responded with {error.code}: {error.reason}")
    except Exception as error:
        print(f"Failed to fetch {url}: {error}")
    raise DownloadError()


if __name__ == "__main__":
    book = Book()
    with alive_bar():
        book.load()

    with alive_bar(len(book.parts)) as bar:
        for part in book.parts:
            part.load()
            bar(part.title)

    chapters = [
        chapter
        for part in book.parts
        for section in part.sections
        for chapter in section.chapters
    ]
    with alive_bar(len(chapters)) as bar:
        for part in book.parts:
            for section in part.sections:
                for chapter in section.chapters:
                    if not (chapter.path / "text.rst").exists():
                        chapter.load()
                        chapter.write()
                    bar(chapter.title)
                section.write()
            part.write()
