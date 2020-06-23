from pathlib import Path
from urllib.request import Request, urlopen, urlretrieve
from bs4 import BeautifulSoup
from bs4.element import Tag


def get(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/35.0.1916.47 Safari/537.36"
            )
        },
    )
    html = urlopen(request)
    return BeautifulSoup(html, "html.parser")


INDEX = """.. _{section_link}:

{stars}
{section_title}
{stars}

.. toctree::

{articles}
"""
IMAGE = """
.. figure:: {path}
   :figwidth: 100 %

   {caption}
"""
base_url = "https://theschooloflife.com/thebookoflife"
page = get(base_url)
categories = [
    cat.text
    for cat in page(class_="nav-main__sub-rollover")
    if cat.has_attr("onmouseover")
]
for category in categories:
    category_path = category.lower().replace(" ", "_")
    print(f"{categories.index(category)+1}/{len(categories)} {category}")
    page = get(f"{base_url}/category/{category}/?index")
    for section in (sections := page("section")) :
        section_title = section.div.text
        section_link = section_title.lower().replace(" ", "_")
        print(f" {sections.index(section)+1}/{len(sections)} {section_title}")
        image = 0
        filenames = []
        for article in (articles := section("li")) :
            title = article.find(class_="title").text
            filename = sub("\W", "", title.replace(" ", "_").lower())
            filenames += [filename]
            print(f"  {articles.index(article)+1}/{len(articles)} {title}")
            page = get(article.a.attrs["href"])
            text = [f"{title}\n{'-'*len(title)}"]
            path = Path(f"source/{category_path}/{section_link}/")
            path.mkdir(parents=True, exist_ok=True)
            for paragraph in page.find(class_="old-wrapper").children:
                if not isinstance(paragraph, Tag):
                    continue
                elif paragraph.figure:
                    image += 1
                    imagepath = path / f"{image}.jpg"
                    urlretrieve(paragraph.img.attrs["src"], imagepath)
                    caption = True
                    continue
                elif paragraph.em and caption and len(paragraph.text) < 100:
                    text += [
                        IMAGE.format(
                            path=f"{image}.jpg", caption=paragraph.text.strip()
                        )
                    ]
                elif paragraph.p or paragraph.name == "p":
                    if caption:
                        text += [
                            IMAGE.format(
                                path=f"{image}.jpg", caption=paragraph.text.strip()
                            )
                        ]
                    text += [paragraph.text.strip(), "\n\n"]
                caption = False
            with open(path / f"{filename}.rst", "w") as output:
                output.write("".join(text))
            break
        with open(path / "index.rst", "w") as output:
            output.write(
                INDEX.format(
                    section_link=section_link,
                    section_title=section_title,
                    stars="*" * len(section_title),
                    articles="\n".join([f"   {fn}" for fn in filenames]),
                )
            )
        break
    break
title = "The Book of Life"
with open(path.parent / "index.rst", "w") as output:
    output.write(
        INDEX.format(
            section_link="",
            section_title=title,
            stars="*" * len(title),
            articles="\n".join([f"   {cat}" for cat in categories]),
        )
    )
