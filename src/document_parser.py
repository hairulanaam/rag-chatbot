import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_parse import LlamaParse
from src.config import LLAMA_PARSE_API_KEY

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".jpg", ".jpeg", ".png",
    ".docx", ".doc",
    ".txt",
}

PARSING_INSTRUCTION = (
    "Extract all the text from this document accurately."
    "DO NOT use bold formatting asterisks (**) for section title."
    "Use markdown headers."
)

def get_parser(instruction: str = None) -> LlamaParse:
    return LlamaParse(
        api_key=LLAMA_PARSE_API_KEY,
        result_type="markdown",
        language="id",
        system_prompt=instruction or PARSING_INSTRUCTION,
    )


def parse_file(file_path: str, output_dir: str = "data") -> str:
    parser = get_parser()

    print(f"⏳ Parsing: {file_path}...")
    documents = parser.load_data(file_path)

    content = "\n\n".join(doc.text for doc in documents if doc.text)

    basename = os.path.splitext(os.path.basename(file_path))[0]
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{basename}.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Berhasil → {output_path}")
    return output_path


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Parse dokumen ke Markdown (LlamaParse)")
    arg_parser.add_argument("input", help="Path ke file dokumen")
    arg_parser.add_argument("--output", "-o", default="data", help="Folder output (default: data/)")

    args = arg_parser.parse_args()
    parse_file(args.input, args.output)
