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

def split_novel_to_chapters(input_filepath, output_dir):
    """
    Splits a novel text file into individual chapter Markdown files.

    Args:
        input_filepath (str): The path to the input novel .txt file.
        output_dir (str): The directory to save the chapter .md files.
    """
    # Define the regular expression to match chapter titles
    # Matches lines starting with "第" followed by Chinese numerals or digits, ending with "章",
    # allowing for optional whitespace around the title.
    chapter_pattern = re.compile(r"^\s*第[一二三四五六七八九十百千万\d]+章.*$")

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
                match = chapter_pattern.match(line)
                if match:
                    # If we have content from a previous chapter, write it to a file
                    if current_chapter_title and current_chapter_content:
                        # Sanitize the chapter title before using it as a filename
                        safe_title = sanitize_filename(current_chapter_title)
                        filename = os.path.join(output_dir, f"{safe_title}.md")
                        try:
                            with open(filename, 'w', encoding='utf-8') as outfile:
                                outfile.write("".join(current_chapter_content))
                            print(f"  - Saved: {filename}")
                            chapter_count += 1
                        except OSError as e:
                            print(f"  - Error saving file {filename}: {e}")
                            print(f"  - Original title: {current_chapter_title}")

                    # Start a new chapter
                    current_chapter_title = match.group(0).strip() # Get the matched title and remove leading/trailing whitespace
                    current_chapter_content = [line] # Start new content with the title line
                    print(f"Found chapter: {current_chapter_title}")

                elif current_chapter_title:
                    # If we are inside a chapter, append the line
                    current_chapter_content.append(line)

            # Write the last chapter after the loop finishes
            if current_chapter_title and current_chapter_content:
                # Sanitize the last chapter title as well
                safe_title = sanitize_filename(current_chapter_title)
                filename = os.path.join(output_dir, f"{safe_title}.md")
                try:
                    with open(filename, 'w', encoding='utf-8') as outfile:
                        outfile.write("".join(current_chapter_content))
                    print(f"  - Saved: {filename}")
                    chapter_count += 1
                except OSError as e:
                    print(f"  - Error saving file {filename}: {e}")
                    print(f"  - Original title: {current_chapter_title}")

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
