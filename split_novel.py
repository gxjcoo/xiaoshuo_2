import re
import os

def sanitize_filename(filename):
    """Removes characters that are invalid in Windows filenames."""
    # Define invalid characters for Windows filenames
    # Includes < > : " / \ | ? *
    invalid_chars = r'[<>:"/\\|?*]'
    # Replace invalid characters with an empty string
    sanitized = re.sub(invalid_chars, '', filename)
    # Also remove leading/trailing whitespace and dots which can cause issues
    sanitized = sanitized.strip('. ')
    # Ensure the filename is not empty after sanitization
    if not sanitized:
        sanitized = "invalid_title"
    return sanitized

def save_chapter(output_dir, chapter_title, chapter_content, chapter_index):
    """Saves a chapter to a markdown file."""
    if not chapter_title or not chapter_content:
        return False

    filename = os.path.join(output_dir, f"{chapter_index}.md")
    try:
        with open(filename, 'w', encoding='utf-8') as outfile:
            outfile.write("".join(chapter_content))
        print(f"  - Saved: {filename}")
        return True
    except OSError as e:
        print(f"  - Error saving file {filename}: {e}")
        print(f"  - Original title: {chapter_title}")
        return False

def split_novel_to_chapters(input_filepath, output_dir):
    """
    Splits a novel text file into individual chapter Markdown files.

    Args:
        input_filepath (str): The path to the input novel .txt file.
        output_dir (str): The directory to save the chapter .md files.
    """
    # Matches chapter headings both at line start and inline in paragraph text.
    # Example inline case: "...惊恐。第5章 这游戏实在是太真实了"
    chapter_pattern = re.compile(
        r"第\s*[零〇一二三四五六七八九十百千万两\d]+\s*[章节回](?:\s+|[:：]\s*)[^\n\r]*"
    )

    # Create the output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    current_chapter_content = []
    current_chapter_title = None
    chapter_count = 0

    try:
        with open(input_filepath, 'r', encoding='utf-8') as infile:
            print(f"Reading file: {input_filepath}")
            for line in infile:
                pos = 0
                found_in_line = False

                for match in chapter_pattern.finditer(line):
                    found_in_line = True
                    prefix = line[pos:match.start()]
                    matched_title = match.group(0).strip()

                    # Keep text before an inline chapter marker in the previous chapter.
                    if prefix and current_chapter_title:
                        current_chapter_content.append(prefix)

                    # Save previous chapter before switching to a new one.
                    next_index = chapter_count + 1
                    if save_chapter(output_dir, current_chapter_title, current_chapter_content, next_index):
                        chapter_count += 1

                    current_chapter_title = matched_title
                    current_chapter_content = [matched_title + "\n"]
                    print(f"Found chapter: {current_chapter_title}")
                    pos = match.end()

                if found_in_line:
                    # Preserve trailing text after the last heading on this line.
                    suffix = line[pos:]
                    if suffix and current_chapter_title:
                        current_chapter_content.append(suffix)
                elif current_chapter_title:
                    # If we are inside a chapter, append the line
                    current_chapter_content.append(line)

            # Write the last chapter after the loop finishes
            next_index = chapter_count + 1
            if save_chapter(output_dir, current_chapter_title, current_chapter_content, next_index):
                chapter_count += 1

        print(f"\nFinished splitting. Total chapters found and attempted to save: {chapter_count}")
        if chapter_count == 0:
            print("Warning: No chapters matching the pattern were found. Please check the chapter format in the file.")

    except FileNotFoundError:
        print(f"Error: Input file not found at {input_filepath}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    input_file = "1.txt"  # Assumes the input file is in the same directory as the script
    output_directory = "all"
    split_novel_to_chapters(input_file, output_directory)
