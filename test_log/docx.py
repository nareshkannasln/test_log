# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""A small Word (.docx) writer, built on nothing but the standard library.

A .docx is a zip of XML parts, so writing one directly costs less than taking on a
dependency — and it keeps the app installable on a machine that is offline, which is
exactly where this app tends to be used.

Only what a test report needs is implemented: headings, paragraphs, captioned images,
hyperlinks and rules.
"""

import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from xml.sax.saxutils import escape

EMU_PER_INCH = 914_400
CONTENT_WIDTH_EMU = int(6.2 * EMU_PER_INCH)  # A4 with the margins set below

NS = (
	'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
	'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
	'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
	'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
	'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'
)

IMAGE_CONTENT_TYPES = {
	"png": "image/png",
	"jpg": "image/jpeg",
	"jpeg": "image/jpeg",
	"gif": "image/gif",
	"bmp": "image/bmp",
	"webp": "image/webp",
}

RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _clean(text) -> str:
	"""XML rejects most control characters outright, so drop them before escaping."""
	text = "" if text is None else str(text)
	text = "".join(char for char in text if char >= " " or char in "\t\n")
	return escape(text)


@dataclass
class _Image:
	name: str
	data: bytes
	extension: str
	rel_id: str


@dataclass
class Document:
	"""Builds one .docx in memory. Call the writers in order, then `render()`."""

	body: list = field(default_factory=list)
	images: list = field(default_factory=list)
	links: dict = field(default_factory=dict)
	_next_rel: int = 10
	_next_shape: int = 1

	# ------------------------------------------------------------------ content

	def heading(self, text, level=1):
		sizes = {0: 40, 1: 30, 2: 24}
		self.paragraph(
			text,
			bold=True,
			size=sizes.get(level, 24),
			space_before=280 if level else 0,
			space_after=120,
			color="1F2933" if level else None,
		)

	def paragraph(
		self, text="", *, bold=False, italic=False, size=22, color=None, space_before=0, space_after=120
	):
		properties = [f'<w:spacing w:before="{space_before}" w:after="{space_after}"/>']
		run_properties = [f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>']

		if bold:
			run_properties.append("<w:b/>")
		if italic:
			run_properties.append("<w:i/>")
		if color:
			run_properties.append(f'<w:color w:val="{color}"/>')

		runs = ""
		for index, line in enumerate(str(text).split("\n")):
			runs += "<w:r>"
			runs += f"<w:rPr>{''.join(run_properties)}</w:rPr>"
			if index:
				runs += "<w:br/>"
			runs += f'<w:t xml:space="preserve">{_clean(line)}</w:t></w:r>'

		self.body.append(f"<w:p><w:pPr>{''.join(properties)}</w:pPr>{runs}</w:p>")

	def label_value(self, label, value):
		if value in (None, ""):
			return

		self.body.append(
			"<w:p>"
			'<w:pPr><w:spacing w:before="0" w:after="60"/></w:pPr>'
			'<w:r><w:rPr><w:b/><w:sz w:val="20"/><w:color w:val="616E7C"/></w:rPr>'
			f'<w:t xml:space="preserve">{_clean(label)}: </w:t></w:r>'
			'<w:r><w:rPr><w:sz w:val="20"/></w:rPr>'
			f'<w:t xml:space="preserve">{_clean(value)}</w:t></w:r>'
			"</w:p>"
		)

	def rule(self):
		self.body.append(
			"<w:p><w:pPr>"
			'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="D9E2EC"/></w:pBdr>'
			'<w:spacing w:before="160" w:after="160"/>'
			"</w:pPr></w:p>"
		)

	def page_break(self):
		self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

	def link(self, label, url):
		rel_id = f"rId{self._next_rel}"
		self._next_rel += 1
		self.links[rel_id] = url

		self.body.append(
			"<w:p>"
			'<w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr>'
			f'<w:hyperlink r:id="{rel_id}">'
			'<w:r><w:rPr><w:color w:val="1264A3"/><w:u w:val="single"/><w:sz w:val="20"/></w:rPr>'
			f'<w:t xml:space="preserve">{_clean(label)}</w:t></w:r></w:hyperlink>'
			"</w:p>"
		)

	def image(self, data: bytes, extension: str, *, caption=None, max_width_emu=CONTENT_WIDTH_EMU):
		extension = (extension or "png").lower().lstrip(".")
		if extension not in IMAGE_CONTENT_TYPES:
			return False

		width, height = _pixel_size(data)
		if not width or not height:
			return False

		# 96 dpi is what a screen capture is measured in.
		cx = min(int(width / 96 * EMU_PER_INCH), max_width_emu)
		cy = int(cx * height / width)

		rel_id = f"rId{self._next_rel}"
		self._next_rel += 1
		shape_id = self._next_shape
		self._next_shape += 1

		name = f"image{len(self.images) + 1}.{extension}"
		self.images.append(_Image(name=name, data=data, extension=extension, rel_id=rel_id))

		self.body.append(
			'<w:p><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr><w:r><w:drawing>'
			'<wp:inline distT="0" distB="0" distL="0" distR="0">'
			f'<wp:extent cx="{cx}" cy="{cy}"/>'
			'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
			f'<wp:docPr id="{shape_id}" name="Picture {shape_id}"/>'
			'<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
			"<a:graphic><a:graphicData uri=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
			"<pic:pic><pic:nvPicPr>"
			f'<pic:cNvPr id="{shape_id}" name="{_clean(name)}"/><pic:cNvPicPr/>'
			"</pic:nvPicPr>"
			f'<pic:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
			'<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
			f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
			'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
			"</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
		)

		if caption:
			self.paragraph(caption, italic=True, size=18, color="616E7C", space_after=160)

		return True

	# ------------------------------------------------------------------ packaging

	def render(self) -> bytes:
		buffer = BytesIO()

		with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
			archive.writestr("[Content_Types].xml", self._content_types())
			archive.writestr("_rels/.rels", _ROOT_RELS)
			archive.writestr("word/document.xml", self._document())
			archive.writestr("word/_rels/document.xml.rels", self._document_rels())

			for image in self.images:
				archive.writestr(f"word/media/{image.name}", image.data)

		return buffer.getvalue()

	def _content_types(self) -> str:
		defaults = {image.extension for image in self.images}
		overrides = "".join(
			f'<Default Extension="{extension}" ContentType="{IMAGE_CONTENT_TYPES[extension]}"/>'
			for extension in sorted(defaults)
		)

		return (
			'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
			'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
			'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
			'<Default Extension="xml" ContentType="application/xml"/>'
			f"{overrides}"
			'<Override PartName="/word/document.xml" '
			'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
			"</Types>"
		)

	def _document(self) -> str:
		section = (
			"<w:sectPr>"
			'<w:pgSz w:w="11906" w:h="16838"/>'
			'<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
			'w:header="708" w:footer="708" w:gutter="0"/>'
			"</w:sectPr>"
		)

		return (
			'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
			f"<w:document {NS}><w:body>{''.join(self.body)}{section}</w:body></w:document>"
		)

	def _document_rels(self) -> str:
		parts = [
			f'<Relationship Id="{image.rel_id}" Type="{RELS}/image" Target="media/{image.name}"/>'
			for image in self.images
		]
		parts += [
			f'<Relationship Id="{rel_id}" Type="{RELS}/hyperlink" '
			f'Target="{escape(url, {chr(34): "&quot;"})}" TargetMode="External"/>'
			for rel_id, url in self.links.items()
		]

		return (
			'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
			'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
			f"{''.join(parts)}</Relationships>"
		)


_ROOT_RELS = (
	'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
	'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
	f'<Relationship Id="rId1" Type="{RELS}/officeDocument" Target="word/document.xml"/>'
	"</Relationships>"
)


def _pixel_size(data: bytes):
	"""Pixel dimensions of an image, so it can be scaled to the page width."""
	try:
		from PIL import Image

		with Image.open(BytesIO(data)) as image:
			return image.size
	except Exception:
		# Pillow missing or the image is unreadable — fall back to a sensible frame.
		return (1280, 720)
