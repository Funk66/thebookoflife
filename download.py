from re import sub, match, search
from time import sleep
from hashlib import md5
from shutil import copyfileobj
from typing import List
from pathlib import Path
from requests import get
from urllib.request import urljoin
from urllib.error import HTTPError
from bs4 import BeautifulSoup
from bs4.element import Tag
from alive_progress import alive_bar
from typing import overload, Optional, Any


class DownloadError(Exception):
    pass


def noop(*args):
    pass


class Item:
    title: str
    path: Path
    url: str
    children: List[Any]

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
        with open(self.path / "page.html", "w") as output:
            output.write(self.html.prettify())
        sleep(10)

    def load(self) -> None:
        path = self.path / "page.html"
        if not path.exists():
            self.download()
        else:
            self.html = BeautifulSoup(path.read_text(), "html.parser")

    def write(self) -> None:
        text = ""
        if hasattr(self, "name"):
            text = f".. _{self.name}:\n\n"
        text += (
            f"{self.title}\n{'='*len(self.title)}\n\n"
            ".. toctree::\n"
            "   :maxdepth: 1\n\n"
        )
        for child in self.children:
            text += f"   {child.name}/index\n"
        with open(self.path / "index.rst", "w") as output:
            output.write(text)


class Book(Item):
    title = "The Book of Life"
    url = "https://theschooloflife.com/thebookoflife/"
    path = Path(__file__).parent / "source"
    children: List["Part"] = []

    def load(self) -> None:
        super().load()
        for html in self.html(class_="nav-main__sub-rollover"):
            if html.has_attr("onmouseover"):
                self.children.append(Part(html.text.strip()))


class Part(Item):
    def __init__(self, title: str):
        self.title = title
        self.url = urljoin(Book.url, f"category/{title.lower()}/?index")
        self.path = Book.path / self.name

    def load(self) -> None:
        super().load()
        self.children = [
            Section(section, self) for section in self.html.find_all("section")
        ]


class Section(Item):
    download = noop
    load = noop

    def __init__(self, html: Tag, parent: Part):
        self.title = html.div.text.strip()
        self.path = parent.path / self.name
        self.children: List["Chapter"] = []
        chapters: List[str] = []
        for li in html.find_all("li"):
            chapter = Chapter(li, self)
            if chapter.name not in chapters:
                self.children.append(chapter)
                chapters.append(chapter.name)


class Chapter(Item):
    def __init__(self, html: Tag, parent: Section):
        self.title = html(class_="title")[0].text.strip()
        self.url = html.a.attrs["href"]
        self.path = parent.path / self.name
        self.parent = parent

    def write(self) -> None:
        if not self.html:
            print(f"No content for {self.title}")
            self.parent.children.pop(self.parent.children.index(self))
            return

        items = []
        for item in self.html.find(class_="old-wrapper").children:
            if isinstance(item, str):
                continue
            if item(class_="addtoany_content"):
                break
            if not item.img and not search(r"[a-zA-Z]", item.text):
                continue
            items.append(item)

        content = []
        previous = None
        for i in range(0, len(items) - 1):
            current = items[i]
            item = Content(current, previous, items[i + 1])
            content.append(item)
            previous = item
        content.append(Content(items[-1], previous, None))
        text = f"{self.title}\n{'='*len(self.title)}\n\n"
        text += "\n".join([c.output() for c in content])
        with open(self.path / "index.rst", "w") as output:
            output.write(text)
        del self.html


class Content:
    headings: List[str] = [r"^\d+\.", r"^\(?[iIvVxX]+\)?\.?\s", r"^\W[ ]+\w+"]

    def __init__(self, content: Tag, previous: Optional[Tag], next: Optional[Tag]):
        self.content = content
        self.previous = previous
        self.next = next

    @property
    def text(self) -> str:
        if not hasattr(self, "_text"):
            self._text = self.content.text.strip()
        return self._text

    @property
    def img(self) -> str:
        if not hasattr(self, "_img"):
            img = self.content.img
            if img and img.attrs.get("src", "").startswith("http"):
                self._img = img.attrs["src"]
            else:
                self._img = ""
        return self._img

    @property
    def is_img(self) -> bool:
        return self.img != ""

    @property
    def is_caption(self) -> bool:
        return bool(
            self.previous
            and self.previous.is_img
            and not self.previous.text
            and len(self.text) < 100
            and not self.is_list
            and not self.is_heading
            and match(r"^[a-zA-Z]", self.text)
        )

    @property
    def is_list(self) -> bool:
        if not self.text.strip().startswith("- "):
            return False
        elif self.previous and self.previous.is_list:
            return True
        elif self.next and self.next.text.startswith("- "):
            return True
        else:
            return False

    @property
    def is_heading(self) -> bool:
        if len(self.text) > 70 or self.is_list:
            return False
        for heading in self.headings:
            if match(heading, self.text):
                return True
        return False

    def bold(self, tag: str) -> BeautifulSoup:
        text = sub(f"<{tag}>\\s?", " $START$", str(self.content))
        text = sub(f"\\s?</{tag}>", "$END$ ", text)
        return BeautifulSoup(text, "html.parser")

    def output(self) -> str:
        if self.is_img:
            filename = md5(self.img.encode("utf-8")).hexdigest() + ".jpg"
            path = Book.path / "images" / filename
            if not path.exists():
                try:
                    # fetch(self.img, path)
                    filename = "404.png"
                except DownloadError:
                    filename = "404.png"
            text = f".. figure:: ../../../images/{filename}\n   :figwidth: 100 %\n"
            if self.text:
                text += f"\n   {self.text}\n"
            return text
        elif self.is_caption:
            return f"   {self.text}\n"
        elif self.is_heading:
            heading = " ".join(self.text.split()[1:])
            return f"{heading}\n{'-'*len(heading)}\n"
        elif self.is_list:
            if self.next and self.next.is_list():
                return self.text
        elif self.content.name != "p" and not self.content.p:
            return ""

        self.content = BeautifulSoup(sub(r"\s+", " ", str(self.content)), "html.parser")
        for tag in ["em", "b", "strong"]:
            for bold in self.content.find_all(tag):
                if bold.text:
                    self.content = self.bold(tag)
            text = sub(r"\s?\$END\$", "**", self.content.text)
            text = sub(r"\$START\$\s?", "**", text)
            self._text = text.replace("****", "").strip()

        return self.text + "\n"


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

    with alive_bar(len(book.children)) as bar:
        for part in book.children:
            part.load()
            bar(part.title)

    chapters = [
        chapter
        for part in book.children
        for section in part.children
        for chapter in section.children
    ]
    with alive_bar(len(chapters)) as bar:
        for part in book.children:
            for section in part.children:
                for chapter in section.children:
                    if not (chapter.path / "index.rst").exists():
                        chapter.load()
                        chapter.write()
                    bar(chapter.title)
                section.write()
            part.write()
        book.write()
