"""Extract a legal PDF to UTF-8 text while preserving page boundaries."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader


def extract_pdf(source: Path, destination: Path) -> None:
    reader = PdfReader(source)
    sections: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        sections.append(f"<!-- PAGE {page_number} -->\n\n{text}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"Extracted {len(reader.pages)} pages to {destination}")


def extract_scanned_pdf(source: Path, destination: Path, image_dir: Path) -> None:
    """Extract embedded page images and OCR them with the project's EasyOCR model."""
    import easyocr

    reader = PdfReader(source)
    image_dir.mkdir(parents=True, exist_ok=True)
    ocr = easyocr.Reader(
        ["vi", "en"],
        gpu=False,
        model_storage_directory=str(
            Path(__file__).resolve().parents[1] / "data" / "models" / "easyocr"
        ),
    )
    sections: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        extracted = (page.extract_text() or "").strip()
        if not extracted and page.images:
            image = page.images[0]
            image_path = image_dir / f"page_{page_number:02d}.png"
            # Saving through Pillow decodes the PDF's CCITT-compressed TIFF image.
            image.image.convert("RGB").save(image_path, format="PNG")
            lines = ocr.readtext(str(image_path), detail=0, paragraph=False)
            extracted = "\n".join(str(line) for line in lines)
        sections.append(f"<!-- PAGE {page_number} -->\n\n{extracted}")
        print(f"OCR page {page_number}/{len(reader.pages)}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"Extracted {len(reader.pages)} pages to {destination}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--image-dir", type=Path, default=Path("data/ocr_pages"))
    args = parser.parse_args()
    if args.ocr:
        extract_scanned_pdf(args.source, args.destination, args.image_dir)
    else:
        extract_pdf(args.source, args.destination)


if __name__ == "__main__":
    main()
