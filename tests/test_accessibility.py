from html.parser import HTMLParser

from jinja2 import Environment, FileSystemLoader, select_autoescape


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def render(name, **context):
    env = Environment(loader=FileSystemLoader('app/templates'), autoescape=select_autoescape(('html',)))
    return env.get_template(name).render(csrf='fixture', **context)


def test_skip_link_titles_and_chunk_save_names():
    book = {'id': 'book', 'title': 'A <script>book</script>', 'real_jobs': [], 'jobs': [], 'chapters': [
        {'ordinal': 0, 'title': 'One', 'chunks': [
            {'id': 'chunk-a', 'revision': 0, 'base_result_hash': None, 'stale': False,
             'source_text': 'A', 'translated_text': None, 'edited_text': None},
            {'id': 'chunk-b', 'revision': 0, 'base_result_hash': None, 'stale': False,
             'source_text': 'B', 'translated_text': None, 'edited_text': None},
        ]}],
    }
    html = render('book.html', book=book, selected_chapter=0, previous_chapter=None, next_chapter=None)
    page = Page(html)
    assert '<title>A &lt;script&gt;book&lt;/script&gt; · Novel Translate</title>' in html
    skip = next(attrs for tag, attrs in page.elements if tag == 'a' and attrs.get('class') == 'skip-link')
    main = next(attrs for tag, attrs in page.elements if tag == 'main')
    assert skip['href'] == '#' + main['id'] and main['tabindex'] == '-1'
    names = [attrs['aria-label'] for tag, attrs in page.elements
             if tag == 'button' and attrs.get('aria-label', '').startswith('Lưu bản sửa chương')]
    assert names == ['Lưu bản sửa chương 1, chunk 1', 'Lưu bản sửa chương 1, chunk 2']
