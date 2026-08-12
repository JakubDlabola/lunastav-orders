"""Increase signature row heights in the DOCX template from 1200 → 1900 twips."""
import os
from docx import Document
from docx.oxml.ns import qn
from lxml import etree

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'Smlouva-LUNASTAV-vzor.docx')
OLD_HEIGHT = '2600'
NEW_HEIGHT = '2200'

doc = Document(TEMPLATE_PATH)

changed = 0
for ti, table in enumerate(doc.tables):
    for ri, row in enumerate(table.rows):
        tr = row._tr
        trPr = tr.find(qn('w:trPr'))
        if trPr is None:
            continue
        trHeight = trPr.find(qn('w:trHeight'))
        if trHeight is not None and trHeight.get(qn('w:val')) == OLD_HEIGHT:
            trHeight.set(qn('w:val'), NEW_HEIGHT)
            print(f"Table {ti} Row {ri}: {OLD_HEIGHT} -> {NEW_HEIGHT}")
            changed += 1

doc.save(TEMPLATE_PATH)
print(f"Done. {changed} rows updated to {NEW_HEIGHT} twips.")
