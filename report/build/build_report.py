"""Rebuild the project report from the template: keep the front matter, replace the chapters, refresh the contents page.

Run from the repository root:  .venv/bin/python report/build/build_report.py
Inputs : report/build/template/mlopsfinal_template.docx (pristine template), report/figures/*.png, report/experiments/*.json
Output : docs/<title>.docx
"""
import copy, json, os, re, shutil, subprocess, sys, zipfile
from lxml import etree
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import docxlib as X
import content as C

TEMPLATE = f"{HERE}/template/mlopsfinal_template.docx"
OUT = f"{ROOT}/docs/{C.TITLE}.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W}
FIG = f"{ROOT}/report/figures"
OLD_TITLE_COVER = "SMARTDEPLOY: CLOUD-BASED USED CAR PRICE PREDICTION USING MLOPS"
OLD_TITLE_CERT = "SmartDeploy: Cloud-Based Used Car Price Prediction Using MLOps"


class Builder:
    def __init__(self):
        self.parts, self.images, self.nums, self.fig_n = [], [], [], 0
        self.cur_list = None

    # raw
    def add(self, xml): self.parts.append(xml)
    abstract_heading = staticmethod(X.abstract_heading); abstract_para = staticmethod(X.abstract_para)
    abstract_spacer = staticmethod(X.abstract_spacer); keywords = staticmethod(X.keywords)

    def chapter(self, n, t): self.add(X.chapter(n, t))
    def p(self, t): self.add(X.body(t))
    def objective(self, t): self.add(X.objective(t))
    def h3(self, t): self.add(X.h3(t))
    def h4(self, t): self.add(X.h4(t))
    def bullet(self, t): self.add(X.list_item(t, 1))
    def caption(self, label, text, above=True): self.add(X.caption(label, text, above))
    def table(self, widths, header, rows, **kw): self.add(X.table(widths, header, rows, **kw))
    def formula(self, t): self.add(X.formula(t))
    def code(self, lines): self.add(X.code_block(lines))

    def numbered(self, t):
        if self.cur_list is None:
            self.cur_list = 3 + len(self.nums); self.nums.append(self.cur_list)
        self.add(X.list_item(t, self.cur_list))

    def figure(self, fname, label, text):
        self.cur_list = None
        self.fig_n += 1
        rid = f"rIdFig{self.fig_n}"
        im = Image.open(f"{FIG}/{fname}"); w, h = im.size
        cx = 5700000; cy = int(cx * h / w)
        self.images.append((rid, fname, f"image_fig{self.fig_n}.png"))
        self.add(X.figure(rid, cx, cy, text))
        self.add(X.caption(label, text, above=False))


def load_inputs():
    E = {"e1": json.load(open(f"{ROOT}/report/experiments/e1_results.json")),
         "e2": json.load(open(f"{ROOT}/report/experiments/e2_results.json")),
         "e3": json.load(open(f"{ROOT}/report/experiments/e3_results.json"))}
    return E, json.load(open(f"{ROOT}/report/experiments/dataset_stats.json"))


def body_xml(E, stats):
    b = Builder()
    C.abstract(b); C.ch1(b); C.ch2(b); C.ch3(b); C.ch4(b, stats); C.ch5(b, E); C.ch6(b)
    b.add(X.references_heading())
    for grp, items in REFS:
        b.add(X.ref_group(grp))
        for i, t in enumerate(items, 1):
            b.add(X.reference(f"{i}.  {t}"))
    return b


REFS = [
    ("Journals", [
        "Cui, C. et al. (2021). PP-LCNet: A lightweight CPU convolutional neural network. *arXiv preprint* arXiv:2109.15099.",
        "Gama, J., Žliobaitė, I., Bifet, A., Pechenizkiy, M. and Bouchachia, A. (2014). A survey on concept drift adaptation. *ACM Computing Surveys*, 46(4): Article 44.",
        "Kreuzberger, D., Kühl, N. and Hirschl, S. (2023). Machine learning operations (MLOps): Overview, definition, and architecture. *IEEE Access*, 11: 31866–31879.",
        "Lu, J., Liu, A., Dong, F., Gu, F., Gama, J. and Zhang, G. (2020). Learning under concept drift: A review. *IEEE Transactions on Knowledge and Data Engineering*, arXiv:2004.05785.",
        "Yu, G. et al. (2021). PP-PicoDet: A better real-time object detector on mobile devices. *arXiv preprint* arXiv:2111.00902.",
    ]),
    ("Conference proceedings", [
        "Amershi, S. et al. (2019). Software engineering for machine learning: A case study. In *Proceedings of the IEEE/ACM International Conference on Software Engineering: Software Engineering in Practice (ICSE-SEIP)*, pp. 291–300.",
        "Laroca, R., Severo, E., Zanlorensi, L. A., Oliveira, L. S., Gonçalves, G. R., Schwartz, W. R. and Menotti, D. (2018). A robust real-time automatic license plate recognition based on the YOLO detector. In *Proceedings of the International Joint Conference on Neural Networks (IJCNN)*, pp. 1–10.",
        "Lin, T.-Y. et al. (2014). Microsoft COCO: Common objects in context. In *Proceedings of the European Conference on Computer Vision (ECCV)*, pp. 740–755.",
        "Redmon, J., Divvala, S., Girshick, R. and Farhadi, A. (2016). You only look once: Unified, real-time object detection. In *Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR)*, pp. 779–788.",
        "Ren, S., He, K., Girshick, R. and Sun, J. (2015). Faster R-CNN: Towards real-time object detection with region proposal networks. In *Advances in Neural Information Processing Systems 28*, pp. 91–99.",
        "Sculley, D. et al. (2015). Hidden technical debt in machine learning systems. In *Advances in Neural Information Processing Systems 28*, pp. 2503–2511.",
        "Silva, S. M. and Jung, C. R. (2018). License plate detection and recognition in unconstrained scenarios. In *Proceedings of the European Conference on Computer Vision (ECCV)*, pp. 580–596.",
        "Xie, Q., Luong, M.-T., Hovy, E. and Le, Q. V. (2020). Self-training with noisy student improves ImageNet classification. In *Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)*, pp. 10687–10698.",
    ]),
    ("Technical documentation and web resources", [
        "Amazon Web Services (2026a). AWS Free Tier FAQs. https://aws.amazon.com/free/free-tier-faqs/ (accessed 26 October 2026).",
        "Amazon Web Services (2026b). Supported AWS services for Sign up for AWS (new). https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.md (accessed 26 October 2026).",
        "Amazon Web Services (2026c). AWS Regions for your projects. https://docs.aws.amazon.com/accounts/latest/reference/project-regions.html (accessed 26 October 2026).",
        "Stolz, R., Zhao, J. and Yu, P. (2026d). Object detection with Amazon Nova 2 Lite. AWS Machine Learning Blog, 2 June 2026. https://aws.amazon.com/blogs/machine-learning/object-detection-with-amazon-nova-2-lite/",
        "Amazon Web Services (2026e). Nova 2 Lite. Amazon Bedrock User Guide. https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html (accessed 26 October 2026).",
        "Amazon Web Services (2026f). Amazon SageMaker AI pricing. https://aws.amazon.com/sagemaker/ai/pricing/ (accessed 26 October 2026).",
        "Amazon Web Services (2026g). Blue/green deployments. Amazon SageMaker AI Developer Guide. https://docs.aws.amazon.com/sagemaker/latest/dg/deployment-guardrails-blue-green.html (accessed 26 October 2026).",
        "Amazon Web Services (2026h). Training data labeling using humans with Amazon SageMaker Ground Truth. https://docs.aws.amazon.com/sagemaker/latest/dg/sms.html (accessed 26 October 2026).",
        "Amazon Web Services (2026i). Prebuilt SageMaker image support policy. https://docs.aws.amazon.com/sagemaker/latest/dg/pre-built-containers-support-policy.html (accessed 26 October 2026).",
        "Amazon Web Services (2026j). Data quality. Amazon SageMaker Model Monitor. https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor-data-quality.html (accessed 26 October 2026).",
        "PaddlePaddle Authors (2026). PaddleDetection: Object detection and instance segmentation toolkit based on PaddlePaddle. https://github.com/PaddlePaddle/PaddleDetection",
    ]),
]


def set_text(p, old, new):
    for t in p.iter(f"{{{W}}}t"):
        if t.text and old in t.text:
            t.text = t.text.replace(old, new); return True
    return False


def build(toc_pages=None):
    work = f"{HERE}/work"
    shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    with zipfile.ZipFile(TEMPLATE) as z:
        z.extractall(work)
        order = z.namelist()
    E, stats = load_inputs()
    b = body_xml(E, stats)

    doc_path = f"{work}/word/document.xml"
    tree = etree.parse(doc_path); root = tree.getroot(); body = root.find("w:body", NSMAP)
    kids = list(body)
    keep, tail = kids[:30], kids[-1]            # cover, certificate, contents table, section break | final sectPr
    for k in kids[30:-1]:
        body.remove(k)
    # cover and certificate titles
    for k in keep:
        set_text(k, OLD_TITLE_COVER, C.TITLE.upper()); set_text(k, OLD_TITLE_CERT, C.TITLE)
    # contents table page numbers
    if toc_pages:
        tbl = [k for k in keep if k.tag == f"{{{W}}}tbl"][0]
        heads = []; page_ps = []
        for tr in tbl.findall("w:tr", NSMAP)[1:]:
            tcs = tr.findall("w:tc", NSMAP)
            heads += ["".join(p.itertext()).strip() for p in tcs[1].findall("w:p", NSMAP)]
            page_ps += tcs[2].findall("w:p", NSMAP)
        for h, p in zip(heads, page_ps):
            ts = list(p.iter(f"{{{W}}}t"))
            if ts: ts[0].text = str(toc_pages[h]);  [setattr(t, "text", "") for t in ts[1:]]
    # new body
    frag = etree.fromstring(f'<w:body {X.NS}>' + "".join(b.parts) + '</w:body>')
    for el in frag:
        tail.addprevious(el)
    for shd in list(root.iter(f"{{{W}}}shd")):   # drop yellow placeholder highlights
        if shd.get(f"{{{W}}}fill") == "FFFF00":
            shd.getparent().remove(shd)
    tree.write(doc_path, xml_declaration=True, encoding="UTF-8", standalone=True)

    # numbering: one restarted list per numbered list
    npath = f"{work}/word/numbering.xml"; s = open(npath, encoding="utf-8").read()
    extra = "".join(f'<w:num w:numId="{n}"><w:abstractNumId w:val="1"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>' for n in b.nums)
    open(npath, "w", encoding="utf-8").write(s.replace("</w:numbering>", extra + "</w:numbering>"))

    # images: drop the old figures (image2..image11), add the new ones
    rpath = f"{work}/word/_rels/document.xml.rels"; r = open(rpath, encoding="utf-8").read()
    for i in range(2, 12):
        r = re.sub(rf'<Relationship Id="rId\d+" Type="[^"]*image" Target="media/image{i}\.png"/>', "", r)
        os.remove(f"{work}/word/media/image{i}.png")
    new_rels = ""
    for rid, fname, target in b.images:
        shutil.copyfile(f"{FIG}/{fname}", f"{work}/word/media/{target}")
        new_rels += f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{target}"/>'
    open(rpath, "w", encoding="utf-8").write(r.replace("</Relationships>", new_rels + "</Relationships>"))

    # document properties
    cp = f"{work}/docProps/core.xml"; s = open(cp, encoding="utf-8").read()
    open(cp, "w", encoding="utf-8").write(s.replace(OLD_TITLE_CERT, C.TITLE))

    # zip, content types first
    if os.path.exists(OUT): os.remove(OUT)
    names = ["[Content_Types].xml"] + [n for n in order if n != "[Content_Types].xml" and not n.endswith("/") and os.path.exists(f"{work}/{n}")]
    for dp, _, fs in os.walk(work):
        for f in fs:
            n = os.path.relpath(os.path.join(dp, f), work)
            if n not in names: names.append(n)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names: z.write(f"{work}/{n}", n)
    return OUT


def render(docx):
    out = f"{HERE}/render"; shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", out, docx], check=True, capture_output=True)
    return f"{out}/{os.path.basename(docx)[:-5]}.pdf"


def toc_headings():
    with zipfile.ZipFile(TEMPLATE) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    tbl = root.find("w:body", NSMAP).find("w:tbl", NSMAP)
    hs = []
    for tr in tbl.findall("w:tr", NSMAP)[1:]:
        tcs = tr.findall("w:tc", NSMAP)
        hs += ["".join(p.itertext()).strip() for p in tcs[1].findall("w:p", NSMAP)]
    return hs


def page_map(pdf):
    import pymupdf
    d = pymupdf.open(pdf)
    lines = [[l.strip() for l in d[i].get_text().splitlines()] for i in range(d.page_count)]
    pages, start = {}, 3                               # body starts on the 4th physical page, numbered 1
    for h in toc_headings():
        found = None
        for i in range(start, d.page_count):
            if h in lines[i]:
                found = i; break
        if found is None:
            raise SystemExit(f"heading not found in render: {h}")
        pages[h] = found - 2; start = found
    return pages, d.page_count


if __name__ == "__main__":
    out = build()
    pdf = render(out); pages, n = page_map(pdf)
    out = build(pages)
    pdf = render(out); pages2, n2 = page_map(pdf)
    print("pages", n, "->", n2, "| toc stable:", pages == pages2)
    if pages != pages2:
        out = build(pages2); pdf = render(out)
    json.dump(pages2, open(f"{HERE}/toc_pages.json", "w"), indent=1)
    print(out)
