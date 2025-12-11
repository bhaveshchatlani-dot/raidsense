import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Load variables from the .env file (including OPENAI_API_KEY)
load_dotenv()

# Create an OpenAI client (it will automatically use OPENAI_API_KEY)
client = OpenAI()


def load_notes(file_path: str) -> str:
    """Read the meeting notes from a text file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Notes file not found: {file_path}")
    return path.read_text(encoding="utf-8")


def analyse_notes_with_openai(notes: str) -> str:
    """
    Send the notes to OpenAI and ask it to extract RAID.
    Returns markdown text.
    """

    # Build the prompt without triple quotes to avoid syntax issues
    prompt = (
        "You are RAIDSense, a RAID (Risks, Assumptions, Issues, Dependencies) analysis "
        "assistant for project and meeting notes.\n\n"
        "Read the meeting notes below and extract all relevant RAID items.\n\n"
        "Please follow these rules:\n"
        "- Be concise but specific.\n"
        "- Do NOT invent details that are not implied in the notes.\n"
        "- Group items logically (similar ones can be merged).\n"
        "- If a section has no items, write 'None identified' for that section.\n\n"
        "Format your answer EXACTLY like this in markdown:\n\n"
        "Risks:\n"
        "- ...\n\n"
        "Assumptions:\n"
        "- ...\n\n"
        "Issues:\n"
        "- ...\n\n"
        "Dependencies:\n"
        "- ...\n\n"
        f"Here are the meeting notes:\n\n{notes}\n"
    )

    response = client.responses.create(
        model="gpt-4o-mini",  # cheaper, good-quality model
        input=prompt,
    )

    # Gives all text output as one string
    return response.output_text


def main():
    # Use filename passed on the command line, or default to sample_notes.txt
    if len(sys.argv) > 1:
        notes_file = sys.argv[1]
    else:
        notes_file = "sample_notes.txt"

    try:
        notes = load_notes(notes_file)
    except FileNotFoundError as e:
        print(e)
        print("Make sure the notes file exists in the same folder as app.py.")
        return

    print("Loaded meeting notes from", notes_file)
    print("Sending to OpenAI for RAID analysis...\n")

    raid_markdown = analyse_notes_with_openai(notes)

    # Print to terminal
    print("===== RAIDSense Output =====\n")
    print(raid_markdown)
    print("\n============================\n")

    # Also save the RAID output to a markdown report file
    notes_path = Path(notes_file)
    report_name = notes_path.stem + "_RAID.md"  # e.g. sample_notes_RAID.md
    report_path = notes_path.with_name(report_name)

    report_path.write_text(raid_markdown, encoding="utf-8")
    print(f"RAID report saved to: {report_path.name}")


if __name__ == "__main__":
    main()