#!/usr/bin/env python
import logging
import os
import re
import unittest
from itertools import groupby
from operator import itemgetter

import pandas as pd
import pytest
from pdfminer.pdfparser import PDFObjRef
from pdfminer.psparser import PSLiteral

import pdfplumber
from pdfplumber import utils

logging.disable(logging.ERROR)

HERE = os.path.abspath(os.path.dirname(__file__))


class Test(unittest.TestCase):
    @classmethod
    def setup_class(self):
        self.pdf = pdfplumber.open(os.path.join(HERE, "pdfs/pdffill-demo.pdf"))
        self.pdf_scotus = pdfplumber.open(
            os.path.join(HERE, "pdfs/scotus-transcript-p1.pdf")
        )

    @classmethod
    def teardown_class(self):
        self.pdf.close()

    def test_cluster_list(self):
        a = [1, 2, 3, 4]
        assert utils.cluster_list(a) == [[x] for x in a]
        assert utils.cluster_list(a, tolerance=1) == [a]

        a = [1, 2, 5, 6]
        assert utils.cluster_list(a, tolerance=1) == [[1, 2], [5, 6]]

    def test_cluster_objects(self):
        a = ["a", "ab", "abc", "b"]
        assert utils.cluster_objects(a, len, 0) == [["a", "b"], ["ab"], ["abc"]]

        b = [{"x": 1, 7: "a"}, {"x": 1, 7: "b"}, {"x": 2, 7: "b"}, {"x": 2, 7: "b"}]
        assert utils.cluster_objects(b, "x", 0) == [[b[0], b[1]], [b[2], b[3]]]
        assert utils.cluster_objects(b, 7, 0) == [[b[0]], [b[1], b[2], b[3]]]

    def test_resolve(self):
        annot = self.pdf.annots[0]
        annot_ad0 = utils.resolve(annot["data"]["A"]["D"][0])
        assert annot_ad0["MediaBox"] == [0, 0, 612, 792]
        assert utils.resolve(1) == 1

    def test_resolve_all(self):
        info = self.pdf.doc.xrefs[0].trailer["Info"]
        assert type(info) is PDFObjRef
        a = [{"info": info}]
        a_res = utils.resolve_all(a)
        assert a_res[0]["info"]["Producer"] == self.pdf.doc.info[0]["Producer"]

    def test_decode_psl_list(self):
        a = [PSLiteral("test"), "test_2"]
        assert utils.decode_psl_list(a) == ["test", "test_2"]

    def test_x_tolerance_ratio(self):
        pdf = pdfplumber.open(os.path.join(HERE, "pdfs/issue-987-test.pdf"))
        page = pdf.pages[0]

        assert page.extract_text() == "Big Te xt\nSmall Text"
        assert page.extract_text(x_tolerance=4) == "Big Te xt\nSmallText"
        assert page.extract_text(x_tolerance_ratio=0.15) == "Big Text\nSmall Text"

        words = page.extract_words(x_tolerance_ratio=0.15)
        assert "|".join(w["text"] for w in words) == "Big|Text|Small|Text"

    def test_extract_words(self):
        path = os.path.join(HERE, "pdfs/issue-192-example.pdf")
        with pdfplumber.open(path) as pdf:
            p = pdf.pages[0]
            words = p.extract_words(vertical_ttb=False)
            words_attr = p.extract_words(vertical_ttb=False, extra_attrs=["size"])
            words_w_spaces = p.extract_words(vertical_ttb=False, keep_blank_chars=True)
            words_rtl = p.extract_words(horizontal_ltr=False)

        assert words[0]["text"] == "Agaaaaa:"
        assert words[0]["direction"] == "ltr"

        assert "size" not in words[0]
        assert round(words_attr[0]["size"], 2) == 9.96

        assert words_w_spaces[0]["text"] == "Agaaaaa: AAAA"

        vertical = [w for w in words if w["upright"] == 0]
        assert vertical[0]["text"] == "Aaaaaabag8"
        assert vertical[0]["direction"] == "btt"

        assert words_rtl[1]["text"] == "baaabaaA/AAA"
        assert words_rtl[1]["direction"] == "rtl"

    def test_extract_words_return_chars(self):
        path = os.path.join(HERE, "pdfs/extra-attrs-example.pdf")
        with pdfplumber.open(path) as pdf:
            page = pdf.pages[0]

            words = page.extract_words()
            assert "chars" not in words[0]

            words = page.extract_words(return_chars=True)
            assert "chars" in words[0]
            assert "".join(c["text"] for c in words[0]["chars"]) == words[0]["text"]

    def test_text_rotation(self):
        rotations = {
            "0": ("ltr", "ttb"),
            "-0": ("rtl", "ttb"),
            "180": ("rtl", "btt"),
            "-180": ("ltr", "btt"),
            "90": ("ttb", "rtl"),
            "-90": ("btt", "rtl"),
            "270": ("btt", "ltr"),
            "-270": ("ttb", "ltr"),
        }

        path = os.path.join(HERE, "pdfs/issue-848.pdf")
        with pdfplumber.open(path) as pdf:
            expected = utils.text.extract_text(pdf.pages[0].chars)
            for i, (rotation, (char_dir, line_dir)) in enumerate(rotations.items()):
                if i == 0:
                    continue
                print(f"--- {rotation} ---")
                p = pdf.pages[i].filter(lambda obj: obj.get("text") != " ")
                output = utils.text.extract_text(
                    x_tolerance=2,
                    y_tolerance=2,
                    chars=p.chars,
                    char_dir=char_dir,
                    line_dir=line_dir,
                    char_dir_rotated=char_dir,
                    line_dir_rotated=line_dir,
                    char_dir_render="ltr",
                    line_dir_render="ttb",
                )
                assert output == expected

    def test_text_rotation_layout(self):
        rotations = {
            "0": ("ltr", "ttb"),
            "-0": ("rtl", "ttb"),
            "180": ("rtl", "btt"),
            "-180": ("ltr", "btt"),
            "90": ("ttb", "rtl"),
            "-90": ("btt", "rtl"),
            "270": ("btt", "ltr"),
            "-270": ("ttb", "ltr"),
        }

        def meets_expectations(text):
            # Both texts should be found, and the first should appear before the second
            a = re.search("opens with a news report", text)
            b = re.search("having been transferred", text)
            return a and b and (a.start() < b.start())

        path = os.path.join(HERE, "pdfs/issue-848.pdf")
        with pdfplumber.open(path) as pdf:
            for i, (rotation, (char_dir, line_dir)) in enumerate(rotations.items()):
                print(f"--- {rotation} ---")
                p = pdf.pages[i].filter(lambda obj: obj.get("text") != " ")
                output = p.extract_text(
                    layout=True,
                    x_tolerance=2,
                    y_tolerance=2,
                    char_dir=char_dir,
                    line_dir=line_dir,
                    char_dir_rotated=char_dir,
                    line_dir_rotated=line_dir,
                    char_dir_render="ltr",
                    line_dir_render="ttb",
                    y_density=14,
                )
                assert meets_expectations(output)

    def test_text_render_directions(self):
        path = os.path.join(HERE, "pdfs/line-char-render-example.pdf")
        targets = {
            ("ttb", "ltr"): "first line\nsecond line\nthird line",
            ("ttb", "rtl"): "enil tsrif\nenil dnoces\nenil driht",
            ("btt", "ltr"): "third line\nsecond line\nfirst line",
            ("btt", "rtl"): "enil driht\nenil dnoces\nenil tsrif",
            ("ltr", "ttb"): "fst\nieh\nrci\nsor\ntnd\n d \nl l\nili\nnin\nene\n e ",
            ("ltr", "btt"): " s \nfet\nich\nroi\nsnr\ntdd\n   \nlll\niii\nnnn\neee",
            ("rtl", "ttb"): "tsf\nhei\nicr\nros\ndnt\n d \nl l\nili\nnin\nene\n e ",
            ("rtl", "btt"): " s \ntef\nhci\nior\nrns\nddt\n   \nlll\niii\nnnn\neee",
        }
        with pdfplumber.open(path) as pdf:
            page = pdf.pages[0]
            for (line_dir, char_dir), target in targets.items():
                text = page.extract_text(
                    line_dir_render=line_dir, char_dir_render=char_dir
                )
                assert text == target

    def test_invalid_directions(self):
        path = os.path.join(HERE, "pdfs/line-char-render-example.pdf")
        pdf = pdfplumber.open(path)
        page = pdf.pages[0]
        with pytest.raises(ValueError):
            page.extract_text(line_dir="xxx", char_dir="ltr")
        with pytest.raises(ValueError):
            page.extract_text(line_dir="ttb", char_dir="a")
        with pytest.raises(ValueError):
            page.extract_text(line_dir="rtl", char_dir="ltr")
        with pytest.raises(ValueError):
            page.extract_text(line_dir="ttb", char_dir="btt")
        with pytest.raises(ValueError):
            page.extract_text(line_dir_rotated="ttb", char_dir="btt")
        with pytest.raises(ValueError):
            page.extract_text(line_dir_render="ttb", char_dir_render="btt")
        pdf.close()

    def test_extra_attrs(self):
        path = os.path.join(HERE, "pdfs/extra-attrs-example.pdf")
        with pdfplumber.open(path) as pdf:
            page = pdf.pages[0]
            assert page.extract_text() == "BlackRedArial"
            assert (
                page.extract_text(extra_attrs=["non_stroking_color"])
                == "Black RedArial"
            )
            assert page.extract_text(extra_attrs=["fontname"]) == "BlackRed Arial"
            assert (
                page.extract_text(extra_attrs=["non_stroking_color", "fontname"])
                == "Black Red Arial"
            )
            # Should not error
            assert page.extract_text(
                layout=True,
                use_text_flow=True,
                extra_attrs=["non_stroking_color", "fontname"],
            )

    def test_extract_words_punctuation(self):
        path = os.path.join(HERE, "pdfs/test-punkt.pdf")
        with pdfplumber.open(path) as pdf:

            wordsA = pdf.pages[0].extract_words(split_at_punctuation=True)
            wordsB = pdf.pages[0].extract_words(split_at_punctuation=False)
            wordsC = pdf.pages[0].extract_words(
                split_at_punctuation=r"!\"&'()*+,.:;<=>?@[]^`{|}~"
            )

            assert wordsA[0]["text"] == "https"
            assert (
                wordsB[0]["text"]
                == "https://dell-research-harvard.github.io/HJDataset/"
            )
            assert wordsC[2]["text"] == "//dell-research-harvard"

            wordsA = pdf.pages[1].extract_words(split_at_punctuation=True)
            wordsB = pdf.pages[1].extract_words(split_at_punctuation=False)
            wordsC = pdf.pages[1].extract_words(
                split_at_punctuation=r"!\"&'()*+,.:;<=>?@[]^`{|}~"
            )

            assert len(wordsA) == 4
            assert len(wordsB) == 2
            assert len(wordsC) == 2

            wordsA = pdf.pages[2].extract_words(split_at_punctuation=True)
            wordsB = pdf.pages[2].extract_words(split_at_punctuation=False)
            wordsC = pdf.pages[2].extract_words(
                split_at_punctuation=r"!\"&'()*+,.:;<=>?@[]^`{|}~"
            )

            assert wordsA[1]["text"] == "["
            assert wordsB[1]["text"] == "[2,"
            assert wordsC[1]["text"] == "["

            wordsA = pdf.pages[3].extract_words(split_at_punctuation=True)
            wordsB = pdf.pages[3].extract_words(split_at_punctuation=False)
            wordsC = pdf.pages[3].extract_words(
                split_at_punctuation=r"!\"&'()*+,.:;<=>?@[]^`{|}~"
            )

            assert wordsA[2]["text"] == "al"
            assert wordsB[2]["text"] == "al."
            assert wordsC[2]["text"] == "al"

    def test_extract_text_punctuation(self):
        path = os.path.join(HERE, "pdfs/test-punkt.pdf")
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text(
                layout=True,
                split_at_punctuation=True,
            )
            assert "https " in text

    def test_text_flow(self):
        path = os.path.join(HERE, "pdfs/federal-register-2020-17221.pdf")

        def words_to_text(words):
            grouped = groupby(words, key=itemgetter("top"))
            lines = [" ".join(word["text"] for word in grp) for top, grp in grouped]
            return "\n".join(lines)

        with pdfplumber.open(path) as pdf:
            p0 = pdf.pages[0]
            using_flow = p0.extract_words(use_text_flow=True)
            not_using_flow = p0.extract_words()

        target_text = (
            "The FAA proposes to\n"
            "supersede Airworthiness Directive (AD)\n"
            "2018–23–51, which applies to all The\n"
            "Boeing Company Model 737–8 and 737–\n"
            "9 (737 MAX) airplanes. Since AD 2018–\n"
        )

        assert target_text in words_to_text(using_flow)
        assert target_text not in words_to_text(not_using_flow)

    def test_text_flow_overlapping(self):
        path = os.path.join(HERE, "pdfs/issue-912.pdf")

        with pdfplumber.open(path) as pdf:
            p0 = pdf.pages[0]
            using_flow = p0.extract_text(use_text_flow=True, layout=True, x_tolerance=1)
            not_using_flow = p0.extract_text(layout=True, x_tolerance=1)

        assert re.search("2015 RICE PAYMENT 26406576 0 1207631 Cr", using_flow)
        assert re.search("124644,06155766", using_flow) is None

        assert re.search("124644,06155766", not_using_flow)
        assert (
            re.search("2015 RICE PAYMENT 26406576 0 1207631 Cr", not_using_flow) is None
        )

    def test_extract_text(self):
        text = self.pdf.pages[0].extract_text()
        goal_lines = [
            "First Page Previous Page Next Page Last Page",
            "Print",
            "PDFill: PDF Drawing",
            "You can open a PDF or create a blank PDF by PDFill.",
            "Online Help",
            "Here are the PDF drawings created by PDFill",
            "Please save into a new PDF to see the effect!",
            "Goto Page 2: Line Tool",
            "Goto Page 3: Arrow Tool",
            "Goto Page 4: Tool for Rectangle, Square and Rounded Corner",
            "Goto Page 5: Tool for Circle, Ellipse, Arc, Pie",
            "Goto Page 6: Tool for Basic Shapes",
            "Goto Page 7: Tool for Curves",
            "Here are the tools to change line width, style, arrow style and colors",
        ]
        goal = "\n".join(goal_lines)

        assert text == goal

        text_simple = self.pdf.pages[0].extract_text_simple()
        assert text_simple == goal

        assert self.pdf.pages[0].crop((0, 0, 1, 1)).extract_text() == ""

    def test_extract_text_blank(self):
        assert utils.extract_text([]) == ""

    def test_extract_text_layout(self):
        target = (
            open(os.path.join(HERE, "comparisons/scotus-transcript-p1.txt"))
            .read()
            .strip("\n")
        )
        page = self.pdf_scotus.pages[0]
        text = page.extract_text(layout=True)
        utils_text = utils.extract_text(
            page.chars,
            layout=True,
            layout_width=page.width,
            layout_height=page.height,
            layout_bbox=page.bbox,
        )
        assert text == utils_text
        assert text == target

    def test_extract_text_layout_cropped(self):
        target = (
            open(os.path.join(HERE, "comparisons/scotus-transcript-p1-cropped.txt"))
            .read()
            .strip("\n")
        )
        p = self.pdf_scotus.pages[0]
        cropped = p.crop((90, 70, p.width, 300))
        text = cropped.extract_text(layout=True)
        assert text == target

    def test_extract_text_layout_widths(self):
        p = self.pdf_scotus.pages[0]
        text = p.extract_text(layout=True, layout_width_chars=75)
        assert all(len(line) == 75 for line in text.splitlines())
        with pytest.raises(ValueError):
            p.extract_text(layout=True, layout_width=300, layout_width_chars=50)
        with pytest.raises(ValueError):
            p.extract_text(layout=True, layout_height=300, layout_height_chars=50)

    def test_extract_text_nochars(self):
        charless = self.pdf.pages[0].filter(lambda df: df["object_type"] != "char")
        assert charless.extract_text() == ""
        assert charless.extract_text(layout=True) == ""

    def test_search_regex_compiled(self):
        page = self.pdf_scotus.pages[0]
        pat = re.compile(r"supreme\s+(\w+)", re.I)
        results = page.search(pat)
        assert results[0]["text"] == "SUPREME COURT"
        assert results[0]["groups"] == ("COURT",)
        assert results[1]["text"] == "Supreme Court"
        assert results[1]["groups"] == ("Court",)

        with pytest.raises(ValueError):
            page.search(re.compile(r"x"), regex=False)

        with pytest.raises(ValueError):
            page.search(re.compile(r"x"), case=False)

    def test_search_regex_uncompiled(self):
        page = self.pdf_scotus.pages[0]
        pat = r"supreme\s+(\w+)"
        results = page.search(pat, case=False)
        assert results[0]["text"] == "SUPREME COURT"
        assert results[0]["groups"] == ("COURT",)
        assert results[1]["text"] == "Supreme Court"
        assert results[1]["groups"] == ("Court",)

    def test_search_string(self):
        page = self.pdf_scotus.pages[0]
        results = page.search("SUPREME COURT", regex=False)
        assert results[0]["text"] == "SUPREME COURT"
        assert results[0]["groups"] == tuple()

        results = page.search("supreme court", regex=False)
        assert len(results) == 0

        results = page.search("supreme court", regex=False, case=False)
        assert len(results) == 2

        results = page.search("supreme court", regex=True, case=False)
        assert len(results) == 2

        results = page.search(r"supreme\s+(\w+)", regex=False)
        assert len(results) == 0

        results = page.search(r"10 Tuesday", layout=False)
        assert len(results) == 1

        results = page.search(r"10 Tuesday", layout=True)
        assert len(results) == 0

    def test_extract_text_lines(self):
        page = self.pdf_scotus.pages[0]
        results = page.extract_text_lines()
        assert len(results) == 28
        assert "chars" in results[0]
        assert results[0]["text"] == "Official - Subject to Final Review"

        alt = page.extract_text_lines(layout=True, strip=False, return_chars=False)
        assert "chars" not in alt[0]
        assert (
            alt[0]["text"]
            == "                                   Official - Subject to Final Review               "  # noqa: E501
        )

        assert results[10]["text"] == "10 Tuesday, January 13, 2009"
        assert (
            alt[10]["text"]
            == "            10                          Tuesday, January 13, 2009                   "  # noqa: E501
        )
        assert (
            page.extract_text_lines(layout=True)[10]["text"]
            == "10                          Tuesday, January 13, 2009"
        )  # noqa: E501

    def test_handle_empty_and_whitespace_search_results(self):
        # via https://github.com/jsvine/pdfplumber/discussions/853
        # The searches below should not raise errors but instead
        # should return empty result-sets.
        page = self.pdf_scotus.pages[0]
        for regex in [True, False]:
            results = page.search("\n", regex=regex)
            assert len(results) == 0

        assert len(page.search("(sdfsd)?")) == 0
        assert len(page.search("")) == 0

    def test_intersects_bbox(self):
        objs = [
            # Is same as bbox
            {
                "x0": 0,
                "top": 0,
                "x1": 20,
                "bottom": 20,
            },
            # Inside bbox
            {
                "x0": 10,
                "top": 10,
                "x1": 15,
                "bottom": 15,
            },
            # Overlaps bbox
            {
                "x0": 10,
                "top": 10,
                "x1": 30,
                "bottom": 30,
            },
            # Touching on one side
            {
                "x0": 20,
                "top": 0,
                "x1": 40,
                "bottom": 20,
            },
            # Touching on one corner
            {
                "x0": 20,
                "top": 20,
                "x1": 40,
                "bottom": 40,
            },
            # Fully outside
            {
                "x0": 21,
                "top": 21,
                "x1": 40,
                "bottom": 40,
            },
        ]
        bbox = utils.obj_to_bbox(objs[0])

        assert utils.intersects_bbox(objs, bbox) == objs[:4]
        assert utils.intersects_bbox(iter(objs), bbox) == objs[:4]

    def test_merge_bboxes(self):
        bboxes = [
            (0, 10, 20, 20),
            (10, 5, 10, 30),
        ]
        merged = utils.merge_bboxes(bboxes)
        assert merged == (0, 5, 20, 30)
        merged = utils.merge_bboxes(iter(bboxes))
        assert merged == (0, 5, 20, 30)

    def test_resize_object(self):
        obj = {
            "x0": 5,
            "x1": 10,
            "top": 20,
            "bottom": 30,
            "width": 5,
            "height": 10,
            "doctop": 120,
            "y0": 40,
            "y1": 50,
        }
        assert utils.resize_object(obj, "x0", 0) == {
            "x0": 0,
            "x1": 10,
            "top": 20,
            "doctop": 120,
            "bottom": 30,
            "width": 10,
            "height": 10,
            "y0": 40,
            "y1": 50,
        }
        assert utils.resize_object(obj, "x1", 50) == {
            "x0": 5,
            "x1": 50,
            "top": 20,
            "doctop": 120,
            "bottom": 30,
            "width": 45,
            "height": 10,
            "y0": 40,
            "y1": 50,
        }
        assert utils.resize_object(obj, "top", 0) == {
            "x0": 5,
            "x1": 10,
            "top": 0,
            "doctop": 100,
            "bottom": 30,
            "height": 30,
            "width": 5,
            "y0": 40,
            "y1": 70,
        }
        assert utils.resize_object(obj, "bottom", 40) == {
            "x0": 5,
            "x1": 10,
            "top": 20,
            "doctop": 120,
            "bottom": 40,
            "height": 20,
            "width": 5,
            "y0": 30,
            "y1": 50,
        }

    def test_move_object(self):
        a = {
            "x0": 5,
            "x1": 10,
            "top": 20,
            "bottom": 30,
            "width": 5,
            "height": 10,
            "doctop": 120,
            "y0": 40,
            "y1": 50,
        }

        b = dict(a)
        b["x0"] = 15
        b["x1"] = 20

        a_new = utils.move_object(a, "h", 10)
        assert a_new == b

    def test_snap_objects(self):
        a = {
            "x0": 5,
            "x1": 10,
            "top": 20,
            "bottom": 30,
            "width": 5,
            "height": 10,
            "doctop": 120,
            "y0": 40,
            "y1": 50,
        }

        b = dict(a)
        b["x0"] = 6
        b["x1"] = 11

        c = dict(a)
        c["x0"] = 7
        c["x1"] = 12

        a_new, b_new, c_new = utils.snap_objects([a, b, c], "x0", 1)
        assert a_new == b_new == c_new
        a_new, b_new, c_new = utils.snap_objects(iter([a, b, c]), "x0", 1)
        assert a_new == b_new == c_new

    def test_filter_edges(self):
        with pytest.raises(ValueError):
            utils.filter_edges([], "x")

    def test_to_list(self):
        objs = [
            {
                "x0": 0,
                "top": 0,
                "x1": 20,
                "bottom": 20,
            },
            {
                "x0": 10,
                "top": 10,
                "x1": 15,
                "bottom": 15,
            },
        ]
        assert utils.to_list(objs) == objs
        assert utils.to_list(iter(objs)) == objs
        assert utils.to_list(tuple(objs)) == objs
        assert utils.to_list((o for o in objs)) == objs
        assert utils.to_list(pd.DataFrame(objs)) == objs
