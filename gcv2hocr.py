#!/usr/bin/env python2

import sys
import json
import argparse
from string import Template
from xml.sax.saxutils import escape

class GCVAnnotation:

    templates = {
        'ocr_page': Template("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="$lang" lang="$lang">
  <head>
    <title>$title</title>
    <meta http-equiv="Content-Type" content="text/html;charset=utf-8" />
    <meta name='ocr-system' content='gcv2hocr.py' />
    <meta name='ocr-langs' content='$lang' />
    <meta name='ocr-number-of-pages' content='1' />
    <meta name='ocr-capabilities' content='ocr_page ocr_carea ocr_par ocr_line ocrx_word ocrp_lang'/>
  </head>
  <body>
    <div class='ocr_page' lang='$lang' title='bbox 0 0 $page_width $page_height'>
        <div class='ocr_carea' lang='$lang' title='bbox $x0 $y0 $x1 $y1'>$content
        </div>
    </div>
  </body>
</html>
    """),
        'ocr_par': Template("""
            <p class='ocr_par' id='$htmlid' title='bbox $x0 $y0 $x1 $y1'>$content
            </p>"""),
        'ocr_line': Template("""
                <span class='ocr_line' id='$htmlid' title='bbox $x0 $y0 $x1 $y1; baseline $baseline'>$content
                </span>"""),
        'ocrx_word': Template("""
                    <span class='ocrx_word' id='$htmlid' title='bbox $x0 $y0 $x1 $y1'>$content</span>""")
    }

    def __init__(self,
                 htmlid=None,
                 ocr_class=None,
                 lang='unknown',
                 baseline="0 -5",
                 page_height=None,
                 page_width=None,
                 content=[],
                 box=None,
                 title=''):
        self.title = title
        self.htmlid = htmlid
        self.baseline = baseline
        self.page_height = page_height
        self.page_width = page_width
        self.lang = lang
        self.ocr_class = ocr_class
        self.content = content
        self.x0 = box[0]['x']
        self.y0 = box[0]['y']
        self.x1 = box[2]['x']
        self.y1 = box[2]['y']

    def maximize_bbox(self):
        self.x0 = min([w.x0 for w in self.content])
        self.y0 = min([w.y0 for w in self.content])
        self.x1 = max([w.x1 for w in self.content])
        self.y1 = max([w.y1 for w in self.content])

    def __repr__(self):
        return "<%s [%s %s %s %s]>%s</%s>" % (self.ocr_class, self.x0, self.y0,
                                              self.x1, self.y1, self.content,
                                              self.ocr_class)
    def render(self):
        if type(self.content) == type([]):
            content = "".join(map(lambda x: x.render(), self.content))
        else:
            content = self.content
        return self.__class__.templates[self.ocr_class].substitute(self.__dict__, content=content)

def makePar(page, box):
    return GCVAnnotation(
                    ocr_class='ocr_par',
                    htmlid="par_%d" % (len(page.content)),
                    content=[],
                    box=box)

def makeLine(page, par, box):
    return GCVAnnotation(
                    ocr_class='ocr_line',
                    htmlid="line_%d_%d" % (len(page.content), len(par.content)),
                    content=[],
                    box=box)

def fromResponse(resp, baseline_tolerance=2, **kwargs):
    last_baseline = -100
    page = None
    curline = None

    if resp[0]['fullTextAnnotation'] is None:
        return GCVAnnotation(
                    ocr_class='ocr_page',
                    htmlid='page_0',
                    box=[{"x": 0, "y": 0}, None, {"x": 0, "y": 0}, None]
        )
    if resp[0]['fullTextAnnotation']['pages'] is None:
        return GCVAnnotation(
                    ocr_class='ocr_page',
                    htmlid='page_0',
                    box=[{"x": 0, "y": 0}, None, {"x": 0, "y": 0}, None]
        )
    for page_id, pageObj in enumerate(resp[0]['fullTextAnnotation']['pages']):
        page = GCVAnnotation(
                    ocr_class='ocr_page',
                    htmlid='page_0',
                    box=[{"x": 0, "y": 0}, None, {"x": pageObj['width'], "y": pageObj['height']}, None]
        )
        
        for block in pageObj['blocks']:
            for paragraph in block['paragraphs']:
                parbox = paragraph['boundingBox']['vertices']
                curlinebox = parbox
                curpar = makePar(page, parbox)
                curline = makeLine(page, curpar, curlinebox)
                newline = 0
                for wordObj in paragraph['words']:
                    wordText = ""
                    for symbol in wordObj['symbols']:
                        wordText += symbol['text']
                        # print(wordText)
                        # detectedBreak = symbol['property']['detectedBreak']
                        if symbol['property'] is not None:
                            detectedBreak = symbol['property']['detectedBreak']
                            if detectedBreak is not None:
                                if detectedBreak['type'] == 'SPACE':
                                    wordText += " "
                                elif detectedBreak['type'] == 'LINE_BREAK':
                                    wordText += " "
                                    # print('Line break found')
                                    # print(wordText)
                                    newline = 1

                    box = wordObj['boundingBox']['vertices']

                    # Can also be a new line of the new top and bottom height are outside the range of the top
                    # and bottom of the first word on the line.
                    if curline.content:
                        curline.maximize_bbox()

                    if curline.content and not (box[2]['y'] <= curline.y1 and box[2]['y'] >= curline.y0):

                        if curline.content:
                            curline.maximize_bbox()
                            curpar.content.append(curline)
                        curline = makeLine(page, curpar, box)
                        newline = 0
                    word = GCVAnnotation(ocr_class='ocrx_word', content=escape(wordText), box=box)
                    word.htmlid="word_%d_%d_%d" % (len(page.content), len(curpar.content), len(curline.content))
                    curline.content.append(word)
                    if newline:
                        curline.maximize_bbox()
                        curpar.content.append(curline)
                        curline = makeLine(page, curpar, box)
                        newline = 0
                if len(curline.content):
                    curpar.content.append(curline)
                page.content.append(curpar)
#        for line in page.content:
            #line.maximize_bbox()

        page.maximize_bbox()
        if not page.page_width:
            if pageObj['width']:
                page.page_width = pageObj['width']
            else:
                page.page_width = page.x1
        if not page.page_height:
            if pageObj['height']:
                page.page_height = pageObj['height']
            else:
                page.page_height = page.y1
        return page

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('gcv_file', help='GCV JSON file, "-" for STDIN')
    parser.add_argument(
        "--baseline",
        "-B",
        help="Baseline offset",
        metavar="pn pn-1 ...",
        default="0 0")
    parser.add_argument(
        "--baseline-tolerance",
        "-T",
        help="Y Tolerance to recognize same line. Default: 2",
        metavar="INT",
        type=int,
        default=2)
    parser.add_argument(
        "--title",
        "-t",
        help="Document title")
    parser.add_argument(
        "--lang",
        "-L",
        default='unknown',
        help="Language")
    parser.add_argument(
        "--page-width",
        "-W",
        help="Image width. Automatically detected unless specified")
    parser.add_argument(
        "--page-height",
        "-H",
        help="Image height. Automatically detected unless specified")
    args = parser.parse_args()

    instream = sys.stdin if args.gcv_file is '-' else open(args.gcv_file, 'r')
    resp = json.load(instream)
    if hasattr(resp, 'responses'): resp = ['responses'][0]

    del(args.gcv_file)
    page = fromResponse(resp, **args.__dict__)
    if str == bytes:
        print(page.render().encode('utf-8'))
    else:
        print(page.render())
