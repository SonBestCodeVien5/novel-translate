# EPUB export

Export is available for an approved real-provider job. The local CLI is:

```sh
.venv/bin/python scripts/export_epub.py --data-dir data --job-id JOB_ID --output /safe/path/translated.epub
```

The command refuses to overwrite an existing output. The browser export is
available from the real-job review page and returns `application/epub+zip`.

TXT sources become a new EPUB 3 package with a navigation document, chapter
documents, a fresh edition identifier, Vietnamese language metadata, and a
modified timestamp. For imported EPUB sources, the exporter keeps the package,
spine order, file paths, metadata, images, and inline markup. It replaces text
only when each source and translated paragraph has exactly one mapped text
node and paragraph counts match. A missing navigation document is added for
EPUB 3; EPUB 2 keeps its version and NCX/spine.

Export stops for paragraphs split across multiple text nodes, mismatched
paragraph counts, missing local links/resources/anchors, script or active
content, signatures, encryption, or changed raw/mapping files. Review those
chapters and export as TXT when their formatting does not fit this profile.
The source EPUB remains unchanged. Output follows the local parser limits: 64
MiB compressed, 8 MiB per entry, 128 MiB expanded, and 10,000 entries. These
size limits are app policy. The package metadata, navigation and OCF container
structure follow the [W3C EPUB 3.3 Recommendation](https://www.w3.org/TR/epub-33/).
