import contextlib
import re
import warnings

import lxml
from lxml import etree
from lxml.html.clean import Cleaner
import parsel
import numpy as np


_clean_html = Cleaner(
    scripts=True,
    javascript=False,  # onclick attributes are fine
    comments=True,
    style=True,
    links=True,
    meta=True,
    page_structure=False,  # <title> may be nice to have
    processing_instructions=True,
    embedded=True,
    frames=True,
    forms=False,  # keep forms
    annoying_tags=False,
    remove_unknown_tags=False,
    safe_attrs_only=False,
).clean_html


def _cleaned_html_tree(html):
    parser = lxml.html.HTMLParser(encoding='utf8')
    tree = lxml.html.fromstring(html.encode('utf8'), parser=parser)
    return _clean_html(tree)


def selector_to_text(sel):
    return sel.xpath('normalize-space()').extract_first('')


def cleaned_selector(html):
    try:
        tree = _cleaned_html_tree(html)
        sel = parsel.Selector(root=tree, type='html')
    except (etree.XMLSyntaxError, etree.ParseError, etree.ParserError,
            UnicodeEncodeError):
        # likely plain text
        sel = parsel.Selector(html)
    return sel


def html2text(html):
    """
    Convert html to text.

    >>> html = '<html><style>.div {}</style><body><p>Hello,   world!</body></html>'
    >>> html2text(html)
    'Hello, world!'

    It works with XHTML declared ecodings:
    >>> html = '<?xml version="1.0" encoding="utf-8" ?><html><style>.div {}</style><body>Hello,   world!</p></body></html>'
    >>> html2text(html)
    'Hello, world!'

    >>> html2text("")
    ''
    """
    return selector_to_text(cleaned_selector(html))


BLOCK_TAGS = {
    'address', 'article', 'aside', 'audio', 'blockquote', 'canvas', 'dd',
    'div', 'dl', 'fieldset', 'figcaption', 'figure', 'footer', 'form',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7', 'h8',
    'header', 'hgroup', 'hr', 'noscript', 'ol', 'output', 'p', 'pre',
    'section', 'table', 'tfoot', 'ul', 'video',
    # not really block, but makes sense to include
    'li',
}


def get_text_blocks(tree):
    text_blocks = []
    current = []
    tag = ''
    for node in tree.iter():
        if node.tag in BLOCK_TAGS:
            if current:
                text_blocks.append((tag, ' '.join(current)))
                current = []
            tag = node.tag
        for text in [node.text, node.tail]:
            if text:
                text = text.strip()
                if text:
                    current.append(text)
    if current:
        text_blocks.append((tag, ' '.join(current)))
    return text_blocks


@contextlib.contextmanager
def ignore_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        yield


def html_to_item(html):
    sel = cleaned_selector(html)
    text = selector_to_text(sel)
    text_item = {
        'text': text,
        'title': ' '.join(sel.xpath('/html/head/title//text()').extract()),
    }
    body = sel.xpath('/html/body')
    if body:
        text_item['blocks'] = get_text_blocks(body[0].root)
    return text_item


def item_to_text(item):
    text = [item['text']]
    if item['title']:
        text.extend('__title__{}'.format(w) for w in tokenize(item['title']))
    for tag, block_text in item.get('blocks', []):
        text.extend('__{}__{}'.format(tag, w) for w in tokenize(block_text))
    return ' '.join(text)


token_pattern = r'(?u)\b[_\w][_\w]+\b'


def tokenize(text):
    return re.findall(token_pattern, text, re.U)


def item_numeric_features(item):
    if item.get('blocks'):
        block_lengths = sorted(
            len(tokenize(block)) for _, block in item['blocks'])
    else:
        block_lengths = None
    return [
        len(tokenize(item['text'])),
        len(item['blocks']) if 'blocks' in item else 0,
        np.max(block_lengths) if block_lengths else 0,
        np.median(block_lengths) if block_lengths else 0,
        block_lengths[int(0.8 * len(block_lengths))] if block_lengths else 0,
    ]
