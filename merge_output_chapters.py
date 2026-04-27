import argparse
import re
from pathlib import Path


def chapter_sort_key(path: Path):
    """Sort chapter files by numeric filename first (e.g. 2.md < 10.md)."""
    match = re.search(r"\d+", path.stem)
    if match:
        return (0, int(match.group()), path.stem.lower())
    return (1, 0, path.stem.lower())


def merge_markdown_chapters(input_dir: Path, output_file: Path, add_filename_header: bool = False) -> int:
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"输入目录不存在或不是目录: {input_dir}")

    chapter_files = sorted(input_dir.glob("*.md"), key=chapter_sort_key)
    if not chapter_files:
        raise FileNotFoundError(f"目录中未找到 md 章节文件: {input_dir}")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as out:
        for index, chapter_file in enumerate(chapter_files):
            content = chapter_file.read_text(encoding="utf-8")

            if add_filename_header:
                out.write(f"=== {chapter_file.name} ===\n")

            out.write(content.rstrip())

            if index < len(chapter_files) - 1:
                out.write("\n\n")

    return len(chapter_files)


def main():
    parser = argparse.ArgumentParser(
        description="将 output_chapters 下所有 .md 章节按顺序合并为 txt。"
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        default="output_chapters",
        help="章节目录，默认 output_chapters",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        default="merged_output.txt",
        help="输出 txt 文件，默认 merged_output.txt",
    )
    parser.add_argument(
        "--with-filename-header",
        action="store_true",
        help="在每章前写入文件名分隔头（如 === 1.md ===）",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    input_dir = Path(args.input_dir)
    output_file = Path(args.output_file)

    if not input_dir.is_absolute():
        input_dir = root / input_dir
    if not output_file.is_absolute():
        output_file = root / output_file

    merged_count = merge_markdown_chapters(
        input_dir=input_dir,
        output_file=output_file,
        add_filename_header=args.with_filename_header,
    )

    print(f"合并完成：{merged_count} 个章节 -> {output_file}")


if __name__ == "__main__":
    main()

