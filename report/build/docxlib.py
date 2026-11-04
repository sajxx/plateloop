"""Small XML builders that reproduce the formatting used by the report template (mlopsfinal.docx)."""
import re
from xml.sax.saxutils import escape

FONT = '<w:rFonts w:hint="default" w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/>'
PFONT = '<w:rPr><w:rFonts w:hint="default" w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/></w:rPr>'

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')


def run(text, sz=24, b=False, i=False, font=FONT):
    props = font + ("<w:b/><w:bCs/>" if b else "") + ("<w:i/><w:iCs/>" if i else "") + f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def runs(markup, sz=24, base_b=False, base_i=False):
    """Inline markup: **bold**, *italic*."""
    out = []
    for tok in re.split(r"(\*\*.+?\*\*|\*.+?\*)", markup):
        if not tok:
            continue
        if tok.startswith("**"):
            out.append(run(tok[2:-2], sz, True, base_i))
        elif tok.startswith("*") and len(tok) > 2:
            out.append(run(tok[1:-1], sz, base_b, True))
        else:
            out.append(run(tok, sz, base_b, base_i))
    return "".join(out)


def body(text):
    return (f'<w:p><w:pPr><w:spacing w:before="0" w:after="120" w:line="360" w:lineRule="auto"/><w:jc w:val="both"/>{PFONT}</w:pPr>'
            f'{runs(text)}</w:p>')


def objective(text):
    return (f'<w:p><w:pPr><w:spacing w:before="0" w:after="120" w:line="360" w:lineRule="auto"/><w:jc w:val="both"/>{PFONT}</w:pPr>'
            f'{run("Objective:", 24, True)}{run(" " + text, 24)}</w:p>')


def abstract_para(text):
    return (f'<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:ind w:firstLine="850"/><w:jc w:val="both"/>{PFONT}</w:pPr>'
            f'{run(text, 24)}</w:p>')


def abstract_spacer():
    return f'<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>{PFONT}</w:pPr></w:p>'


def keywords(text):
    return (f'<w:p><w:pPr><w:spacing w:before="240" w:after="0"/>{PFONT}</w:pPr>{run("Keywords: ", 24, True)}{run(text, 24)}</w:p>')


def abstract_heading():
    return (f'<w:p><w:pPr><w:pStyle w:val="2"/><w:pageBreakBefore/><w:spacing w:before="600" w:after="360"/><w:jc w:val="center"/>{PFONT}</w:pPr>'
            f'{run("ABSTRACT", 32, True)}</w:p>')


def chapter(num, title):
    lab = (f'<w:p><w:pPr><w:pageBreakBefore/><w:spacing w:before="1200" w:after="120"/><w:jc w:val="center"/>{PFONT}</w:pPr>'
           f'{run("CHAPTER " + str(num), 32, True)}</w:p>')
    ttl = (f'<w:p><w:pPr><w:pStyle w:val="2"/><w:spacing w:after="360"/><w:jc w:val="center"/>{PFONT}</w:pPr>{run(title, 32, True)}</w:p>')
    return lab + ttl


def references_heading():
    return (f'<w:p><w:pPr><w:pStyle w:val="2"/><w:pageBreakBefore/><w:spacing w:before="600" w:after="360"/><w:jc w:val="center"/>{PFONT}</w:pPr>'
            f'{run("REFERENCES", 32, True)}</w:p>')


def h3(text):
    return f'<w:p><w:pPr><w:pStyle w:val="3"/><w:keepNext/><w:spacing w:before="280" w:after="120"/>{PFONT}</w:pPr>{run(text, 28, True)}</w:p>'


def h4(text):
    return f'<w:p><w:pPr><w:pStyle w:val="4"/><w:keepNext/><w:spacing w:before="200" w:after="100"/>{PFONT}</w:pPr>{run(text, 24, True)}</w:p>'


def list_item(text, num_id):
    return (f'<w:p><w:pPr><w:pStyle w:val="18"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>'
            f'<w:spacing w:after="80" w:line="340" w:lineRule="auto"/><w:jc w:val="both"/>{PFONT}</w:pPr>{runs(text)}</w:p>')


def caption(label, text, above=True):
    if above:
        return (f'<w:p><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="80"/><w:jc w:val="center"/>{PFONT}</w:pPr>'
                f'{run(label + ": ", 22, True)}{run(text, 22)}</w:p>')
    return (f'<w:p><w:pPr><w:spacing w:before="40" w:after="240"/><w:jc w:val="center"/>{PFONT}</w:pPr>'
            f'{run(label + ": ", 22, True)}{run(text, 22)}</w:p>')


_doc_id = [100]


def figure(rid, cx, cy, name):
    _doc_id[0] += 1
    i = _doc_id[0]
    return (f'<w:p><w:pPr><w:keepNext/><w:spacing w:before="120" w:after="60"/><w:jc w:val="center"/>{PFONT}</w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:hint="default" w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/></w:rPr>'
            f'<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{i}" name="{escape(name)}" descr="{escape(name)}" title="{escape(name)}"/>'
            f'<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
            f'<pic:nvPicPr><pic:cNvPr id="{i}" name="{escape(name)}" descr="{escape(name)}" title="{escape(name)}"/><pic:cNvPicPr><a:picLocks noChangeAspect="1" noChangeArrowheads="1"/></pic:cNvPicPr></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:srcRect/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')


def code_line(text):
    mono = '<w:rFonts w:hint="default" w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Courier New" w:cs="Times New Roman"/>'
    return (f'<w:p><w:pPr><w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:ind w:left="120" w:right="120"/>{PFONT}</w:pPr>'
            f'<w:r><w:rPr>{mono}<w:sz w:val="15"/><w:szCs w:val="15"/></w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def code_block(lines):
    return "".join(code_line(l) for l in lines) + spacer()


def formula(text):
    return (f'<w:p><w:pPr><w:spacing w:before="100" w:after="140"/><w:jc w:val="center"/>{PFONT}</w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:hint="default" w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Cambria Math" w:cs="Times New Roman"/><w:i/><w:iCs/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def spacer():
    return f'<w:p><w:pPr><w:spacing w:before="0" w:after="60"/>{PFONT}</w:pPr></w:p>'


def reference(text):
    return (f'<w:p><w:pPr><w:spacing w:after="100" w:line="300" w:lineRule="auto"/><w:ind w:left="567" w:hanging="567"/><w:jc w:val="left"/>{PFONT}</w:pPr>'
            f'{runs(text)}</w:p>')


def ref_group(text):
    return f'<w:p><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/>{PFONT}</w:pPr>{run(text, 24, True)}</w:p>'


BORDER = '<w:top w:val="single" w:color="7F7F7F" w:sz="4" w:space="0"/><w:left w:val="single" w:color="7F7F7F" w:sz="4" w:space="0"/><w:bottom w:val="single" w:color="7F7F7F" w:sz="4" w:space="0"/><w:right w:val="single" w:color="7F7F7F" w:sz="4" w:space="0"/>'
MAR = '<w:tcMar><w:top w:w="50" w:type="dxa"/><w:left w:w="80" w:type="dxa"/><w:bottom w:w="50" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tcMar>'


def _cell(text, w, header, align, sz, keep, bold_first=False):
    jc = "center" if header else align
    marks = runs(text, sz, base_b=(header or bold_first))
    shd = '<w:shd w:val="clear" w:color="auto" w:fill="auto"/>' if header else ""
    kn = "<w:keepNext/>" if keep else ""
    return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/><w:tcBorders>{BORDER}</w:tcBorders>'
            f'{shd}{MAR}<w:vAlign w:val="center"/></w:tcPr>'
            f'<w:p><w:pPr>{kn}<w:spacing w:line="240" w:lineRule="auto"/><w:jc w:val="{jc}"/>{PFONT}</w:pPr>{marks}</w:p></w:tc>')


def table(widths, header, rows, aligns=None, sz=17, keep=True, bold_first=False):
    assert sum(widths) == 9026, sum(widths)
    aligns = aligns or ["left"] * len(widths)
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="9"/><w:tblW w:w="9026" w:type="dxa"/><w:tblInd w:w="0" w:type="dxa"/><w:tblBorders>'
           '<w:top w:val="single" w:color="auto" w:sz="4" w:space="0"/><w:left w:val="single" w:color="auto" w:sz="4" w:space="0"/><w:bottom w:val="single" w:color="auto" w:sz="4" w:space="0"/>'
           '<w:right w:val="single" w:color="auto" w:sz="4" w:space="0"/><w:insideH w:val="single" w:color="auto" w:sz="4" w:space="0"/><w:insideV w:val="single" w:color="auto" w:sz="4" w:space="0"/></w:tblBorders>'
           '<w:tblLayout w:type="autofit"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="10" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="10" w:type="dxa"/></w:tblCellMar></w:tblPr>'
           f'<w:tblGrid>{grid}</w:tblGrid>']
    out.append('<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>' + "".join(_cell(h, w, True, "center", sz, keep) for h, w in zip(header, widths)) + '</w:tr>')
    for ri, r in enumerate(rows):
        k = keep and ri < len(rows) - 1
        out.append('<w:tr><w:trPr><w:cantSplit/></w:trPr>' + "".join(
            _cell(str(c), w, False, a, sz, k, bold_first and ci == 0) for ci, (c, w, a) in enumerate(zip(r, widths, aligns))) + '</w:tr>')
    out.append('</w:tbl>')
    return "".join(out) + spacer()
