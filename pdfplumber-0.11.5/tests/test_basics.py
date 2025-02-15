#!/usr/bin/env python
import logging
import os
import unittest

import pytest

import pdfplumber

logging.disable(logging.ERROR)

HERE = os.path.abspath(os.path.dirname(__file__))


class Test(unittest.TestCase):
    @classmethod
    def setup_class(self):
        path = os.path.join(HERE, "pdfs/nics-background-checks-2015-11.pdf")
        self.pdf = pdfplumber.open(path)
        # via http://www.pdfill.com/example/pdf_drawing_new.pdf
        path_2 = os.path.join(HERE, "pdfs/pdffill-demo.pdf")
        self.pdf_2 = pdfplumber.open(path_2)

    @classmethod
    def teardown_class(self):
        self.pdf.close()
        self.pdf_2.close()

    def test_metadata(self):
        metadata = self.pdf.metadata
        assert isinstance(metadata["Producer"], str)

    def test_pagecount(self):
        assert len(self.pdf.pages) == 1

    def test_page_number(self):
        assert self.pdf.pages[0].page_number == 1
        assert str(self.pdf.pages[0]) == "<Page:1>"

    def test_objects(self):
        assert len(self.pdf.chars)
        assert len(self.pdf.rects)
        assert len(self.pdf.lines)
        assert len(self.pdf.rect_edges)
        assert len(self.pdf_2.curve_edges)
        # Ensure that caching is working:
        assert id(self.pdf._rect_edges) == id(self.pdf.rect_edges)
        assert id(self.pdf_2._curve_edges) == id(self.pdf_2.curve_edges)
        assert id(self.pdf.pages[0]._layout) == id(self.pdf.pages[0].layout)

    def test_annots(self):
        pdf = self.pdf_2
        assert len(pdf.annots)
        assert len(pdf.hyperlinks) == 17
        uri = "http://www.pdfill.com/pdf_drawing.html"
        assert pdf.hyperlinks[0]["uri"] == uri

        path = os.path.join(HERE, "pdfs/annotations.pdf")
        with pdfplumber.open(path) as pdf:
            assert len(pdf.annots)

    def test_annots_cropped(self):
        pdf = self.pdf_2
        page = pdf.pages[0]
        assert len(page.annots) == 13
        assert len(page.hyperlinks) == 1

        cropped = page.crop(page.bbox)
        assert len(cropped.annots) == 13
        assert len(cropped.hyperlinks) == 1

        h0_bbox = pdfplumber.utils.obj_to_bbox(page.hyperlinks[0])
        cropped = page.crop(h0_bbox)
        assert len(cropped.annots) == len(cropped.hyperlinks) == 1

    def test_annots_rotated(self):
        def get_annot(filename, n=0):
            path = os.path.join(HERE, "pdfs", filename)
            with pdfplumber.open(path) as pdf:
                return pdf.pages[0].annots[n]

        a = get_annot("annotations.pdf", 3)
        b = get_annot("annotations-rotated-180.pdf", 3)
        c = get_annot("annotations-rotated-90.pdf", 3)
        d = get_annot("annotations-rotated-270.pdf", 3)

        assert (
            int(a["width"]) == int(b["width"]) == int(c["height"]) == int(d["height"])
        )
        assert (
            int(a["height"]) == int(b["height"]) == int(c["width"]) == int(d["width"])
        )
        assert int(a["x0"]) == int(c["top"]) == int(d["y0"])
        assert int(a["x1"]) == int(c["bottom"]) == int(d["y1"])
        assert int(a["top"]) == int(b["y0"]) == int(d["x0"])
        assert int(a["bottom"]) == int(b["y1"]) == int(d["x1"])

    def test_crop_and_filter(self):
        def test(obj):
            return obj["object_type"] == "char"

        bbox = (0, 0, 200, 200)
        original = self.pdf.pages[0]
        cropped = original.crop(bbox)
        assert id(cropped.chars) == id(cropped._objects["char"])
        assert cropped.width == 200
        assert len(cropped.rects) > 0
        assert len(cropped.chars) < len(original.chars)

        within_bbox = original.within_bbox(bbox)
        assert len(within_bbox.chars) < len(cropped.chars)
        assert len(within_bbox.chars) > 0

        filtered = cropped.filter(test)
        assert id(filtered.chars) == id(filtered._objects["char"])
        assert len(filtered.rects) == 0

    def test_outside_bbox(self):
        original = self.pdf.pages[0]
        outside_bbox = original.outside_bbox(original.find_tables()[0].bbox)
        assert outside_bbox.extract_text() == "Page 1 of 205"
        assert outside_bbox.bbox == original.bbox

    def test_relative_crop(self):
        page = self.pdf.pages[0]
        cropped = page.crop((10, 10, 40, 40))
        recropped = cropped.crop((10, 15, 20, 25), relative=True)
        target_bbox = (20, 25, 30, 35)
        assert recropped.bbox == target_bbox

        recropped_wi = cropped.within_bbox((10, 15, 20, 25), relative=True)
        assert recropped_wi.bbox == target_bbox

        # via issue #245, should not throw error when using `relative=True`
        bottom = page.crop((0, 0.8 * float(page.height), page.width, page.height))
        bottom.crop((0, 0, 0.5 * float(bottom.width), bottom.height), relative=True)
        bottom.crop(
            (0.5 * float(bottom.width), 0, bottom.width, bottom.height), relative=True
        )

        # An extra test for issue #914, in which relative crops were
        # using the the wrong bboxes for cropping, leading to empty object-lists
        crop_right = page.crop((page.width / 2, 0, page.width, page.height))
        crop_right_again_rel = crop_right.crop(
            (0, 0, crop_right.width / 2, page.height), relative=True
        )
        assert len(crop_right_again_rel.chars)

    def test_invalid_crops(self):
        page = self.pdf.pages[0]
        with pytest.raises(ValueError):
            page.crop((0, 0, 0, 0))

        with pytest.raises(ValueError):
            page.crop((0, 0, 10000, 10))

        with pytest.raises(ValueError):
            page.crop((-10, 0, 10, 10))

        with pytest.raises(ValueError):
            page.crop((100, 0, 0, 100))

        with pytest.raises(ValueError):
            page.crop((0, 100, 100, 0))

        # via issue #245
        bottom = page.crop((0, 0.8 * float(page.height), page.width, page.height))
        with pytest.raises(ValueError):
            bottom.crop((0, 0, 0.5 * float(bottom.width), bottom.height))
        with pytest.raises(ValueError):
            bottom.crop((0.5 * float(bottom.width), 0, bottom.width, bottom.height))

        # via issue #421, testing strict=True/False
        with pytest.raises(ValueError):
            page.crop((0, 0, page.width + 10, page.height + 10))

        page.crop((0, 0, page.width + 10, page.height + 10), strict=False)

    def test_rotation(self):
        assert self.pdf.pages[0].width == 1008
        assert self.pdf.pages[0].height == 612
        path = os.path.join(HERE, "pdfs/nics-background-checks-2015-11-rotated.pdf")
        with pdfplumber.open(path) as rotated:
            assert rotated.pages[0].width == 612
            assert rotated.pages[0].height == 1008

            assert rotated.pages[0].cropbox != self.pdf.pages[0].cropbox
            assert rotated.pages[0].bbox != self.pdf.pages[0].bbox

    def test_password(self):
        path = os.path.join(HERE, "pdfs/password-example.pdf")
        with pdfplumber.open(path, password="test") as pdf:
            assert len(pdf.chars) > 0

    def test_unicode_normalization(self):
        path = os.path.join(HERE, "pdfs/issue-905.pdf")

        with pdfplumber.open(path) as pdf:
            page = pdf.pages[0]
            print(page.extract_text())
            assert ord(page.chars[0]["text"]) == 894

        with pdfplumber.open(path, unicode_norm="NFC") as pdf:
            page = pdf.pages[0]
            assert ord(page.chars[0]["text"]) == 59
            assert page.extract_text() == ";;"

    def test_colors(self):
        rect = self.pdf.pages[0].rects[0]
        assert rect["non_stroking_color"] == (0.8, 1, 1)

    def test_text_colors(self):
        char = self.pdf.pages[0].chars[3358]
        assert char["non_stroking_color"] == (1, 0, 0)

    def test_load_with_custom_laparams(self):
        # See https://github.com/jsvine/pdfplumber/issues/168
        path = os.path.join(HERE, "pdfs/cupertino_usd_4-6-16.pdf")
        laparams = dict(line_margin=0.2)
        with pdfplumber.open(path, laparams=laparams) as pdf:
            assert round(pdf.pages[0].chars[0]["top"], 3) == 66.384

    def test_loading_pathobj(self):
        from pathlib import Path

        path = os.path.join(HERE, "pdfs/nics-background-checks-2015-11.pdf")
        path_obj = Path(path)
        with pdfplumber.open(path_obj) as pdf:
            assert len(pdf.metadata)

    def test_loading_fileobj(self):
        path = os.path.join(HERE, "pdfs/nics-background-checks-2015-11.pdf")
        with open(path, "rb") as f:
            with pdfplumber.open(f) as pdf:
                assert len(pdf.metadata)
            assert not f.closed

    def test_bad_fileobj(self):
        path = os.path.join(HERE, "pdfs/empty.pdf")
        with pytest.raises(pdfplumber.pdf.PSException):
            pdfplumber.open(path)

        f = open(path)
        with pytest.raises(pdfplumber.pdf.PSException):
            pdfplumber.open(f)
        # File objects passed to pdfplumber should not be auto-closed
        assert not f.closed
        f.close()
