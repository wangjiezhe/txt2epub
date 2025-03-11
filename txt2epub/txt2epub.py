#!/usr/bin/python
# -*- coding: utf-8 -*-
import pathlib
import re
import uuid
from typing import Optional

import langdetect
from ebooklib import epub

from .utils import convert_image_to_jpeg


class Txt2Epub:
    @staticmethod
    def create_epub(
        input_file: pathlib.Path,
        output_file: Optional[pathlib.Path] = None,
        book_identifier: Optional[str] = None,
        book_title: Optional[str] = None,
        book_author: Optional[str] = None,
        book_language: Optional[str] = None,
        book_cover: Optional[pathlib.Path] = None,
        linebreaks: int = 3,
    ):
        # generate fields if not specified
        book_identifier = book_identifier or str(uuid.uuid4())
        if match := re.match(r"^(.*?)\((.*?)\)$", input_file.stem):
            book_title = book_title or match.group(1)
            book_author = book_author or match.group(2)
        else:
            book_title = book_title or input_file.stem
            book_author = book_author or "Unknown"

        # read text from file
        with input_file.open("r", encoding="utf-8") as txt_file:
            book_text = txt_file.read()

            # detect book language if not specified
            try:
                book_language = book_language or langdetect.detect(book_text)
            except langdetect.lang_detect_exception.LangDetectException:
                book_language = "en"

        # split text into chapters
        chapters = book_text.split("\n" * linebreaks)

        # convert cover image to JPEG
        book_cover_jpeg = None
        if book_cover is not None and book_cover != pathlib.Path():
            book_cover_jpeg = convert_image_to_jpeg(book_cover)

        # create new EPUB book
        book = epub.EpubBook()

        # set book metadata
        book.set_identifier(book_identifier)
        book.set_title(book_title)
        book.add_author(book_author)
        book.set_language(book_language)
        book.set_cover("cover.jpg", book_cover_jpeg)

        # add info page
        info = epub.EpubHtml(
            title="Info",
            file_name="info.xhtml",
            lang=book_language,
        )
        info.add_link(href="style.css", rel="stylesheet", type="text/css")
        info.content = "<h1>{}</h1><h2>{}</h2>".format(book_title, book_author)
        book.add_item(info)

        # add message page
        message = epub.EpubHtml(
            title="Message",
            file_name="message.xhtml",
            lang=book_language,
        )
        message.add_link(href="style.css", rel="stylesheet", type="text/css")
        message.content = "<div>{}</div>".format(
            "".join(
                "<p>{}</p>".format(line.lstrip())
                for line in chapters.pop(0).split("\n")
            )
        )
        book.add_item(message)

        # check if txt has section level with syntax
        # =============
        # Section Title
        # =============
        if re.match(r"^={3,}", chapters[0].lstrip("\n")):
            use_section = True
        else:
            use_section = False

        # create chapters
        spine: list[str | epub.EpubHtml] = [info, message, "nav"]
        toc = []
        current_section = []
        for chapter_id, chapter_content_full in enumerate(chapters):
            chapter_lines = chapter_content_full.lstrip("\n").split("\n")
            chapter_title = chapter_lines[0]
            chapter_content = chapter_lines[1:]

            if use_section:
                if re.match(r"^={3,}$", chapter_title):
                    if current_section != []:
                        toc.append(current_section)
                        current_section = []
                    while (section_title := chapter_content.pop(0)) == "":
                        continue
                    section = epub.EpubHtml(
                        title=section_title,
                        file_name="chap_{:02d}.xhtml".format(chapter_id + 1),
                        lang=book_language,
                    )
                    section.add_link(
                        href="style.css", rel="stylesheet", type="text/css"
                    )
                    section.content = "<h1>{}</h1>".format(section_title)
                    book.add_item(section)
                    spine.append(section)
                    current_section.append(section)
                    current_section.append([])
                    continue

            # write chapter title and contents
            chapter = epub.EpubHtml(
                title=chapter_title,
                file_name="chap_{:02d}.xhtml".format(chapter_id + 1),
                lang=book_language,
            )
            chapter.add_link(href="style.css", rel="stylesheet", type="text/css")
            chapter.content = "<h2>{}</h2><div>{}</div>".format(
                chapter_title,
                "".join("<p>{}</p>".format(line.lstrip()) for line in chapter_content),
            )

            # add chapter to the book and TOC
            book.add_item(chapter)
            spine.append(chapter)
            if use_section:
                current_section[1].append(chapter)
            else:
                toc.append(chapter)

        if use_section:
            toc.append(current_section)

        # update book spine and TOC
        book.spine = spine
        book.toc = toc

        # add navigation files
        book.add_item(epub.EpubNcx())
        nav = epub.EpubNav(title="目录")
        nav.add_link(href="toc.css", rel="stylesheet", type="text/css")
        book.add_item(nav)

        # add CSS style
        style_css = epub.EpubItem(
            uid="style_content",
            file_name="style.css",
            media_type="text/css",
            content="""h1 {
  line-height: 130%;
  text-align: center;
  font-weight: bold;
  font-size: xx-large;
  margin-top: 3.2em;
  margin-bottom: 3.3em;
}

h2 {
  line-height: 130%;
  text-align: center;
  font-weight: bold;
  font-size: x-large;
  margin-top: 1.2em;
  margin-bottom: 2.3em;
}

div {
  margin: 0;
  padding: 0;
  text-align: justify;
}

p {
  text-indent: 2em;
  display: block;
  line-height: 1.3em;
  margin-top: 0.4em;
  margin-bottom: 0.4em;
}
""",
        )
        book.add_item(style_css)

        toc_css_content = """h2 {
  font-size: 2em;
  font-weight: bold;
  margin-bottom: 1em;
  text-align: center;
}
"""
        if use_section:
            toc_css_content += """
ol {
  list-style-type: upper-roman;
}

ol ol {
    list-style-type: decimal;
}
"""
        toc_css = epub.EpubItem(
            uid="style_toc",
            file_name="toc.css",
            media_type="text/css",
            content=toc_css_content,
        )
        book.add_item(toc_css)

        # generate new file path if not specified
        if output_file is None:
            output_file = input_file.with_suffix(".epub")

        # create EPUB file
        epub.write_epub(output_file, book)
