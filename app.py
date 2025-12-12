import sys
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Load variables from the .env file (including OPENAI_API_KEY)
load_dotenv()

# Create an OpenAI client (it will automatically use OPENAI_API_KEY)
client = OpenAI()

# ---- JSON Schema for RAIDSense output ----
RAID_SCHEMA = {
    "type": "object",
    "properties": {
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "mitigation": {"type": "string"},
                },
                "required": ["title", "detail", "mitigation"],
                "additionalProperties": False,
            },
        },
        "assumptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "validation_step": {"type": "string"},
                },
                "required": ["title", "detail", "validation_step"],
                "additionalProperties": False,
            },
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "next_step": {"type": "string"},
                },
                "required": ["title", "detail", "next_step"],
                "additionalProperties": False,
            },
        },
        "dependencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "owner": {"type": "string"},
                    "due_date": {"type": "string"},
                },
                "required": ["title", "detail", "owner", "due_date"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["risks", "assumptions", "issues", "dependencies"],
    "additionalProperties": False,
}


def load_notes(file_path: str) -> str:
    """Read the meeting notes from a text file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Notes file not found: {file_path}")
    return path.read_text(encoding="utf-8")


def analyse_notes_with_openai(notes: str) -> dict:
    """
    Send the notes to OpenAI and ask it to extract RAID.
    Returns a Python dict that matches RAID_SCHEMA.
    """

    system_msg = (
        "You are RAIDSense, a RAID (Risks, Assumptions, Issues, Dependencies) analysis assistant "
        "for project and meeting notes."
    )

    user_msg = (
        "Extract RAID items from the notes.\n"
        "Rules:\n"
        "- Be concise but specific.\n"
        "- Do NOT invent details that are not implied in the notes.\n"
        "- Merge duplicates / very similar items.\n"
        "- If a section has no items, return an empty array for it.\n\n"
        "- For any field you can't infer, return an empty string \"\" (not null, not omitted).\n"
        "Meeting notes:\n"
        f"{notes}"
    )

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "raid_output",
                "schema": RAID_SCHEMA,
                "strict": True,
            }
        },
        store=False,  # optional: avoid storing responses server-side
    )

    # response.output_text should be valid JSON matching RAID_SCHEMA
    return json.loads(response.output_text)


def render_markdown(raid: dict) -> str:
    """Convert the RAID dict into a nice Markdown report."""
    def section(title: str, items: list, extra_fields: list[str]) -> str:
        lines = [f"## {title}"]
        if not items:
            lines.append("None identified")
            return "\n".join(lines)

        for item in items:
            t = item.get("title", "").strip()
            d = item.get("detail", "").strip()

            bullet = f"- **{t}** — {d}" if t else f"- {d}"
            lines.append(bullet)

            for field in extra_fields:
                val = item.get(field, "").strip()
                if val:
                    pretty = field.replace("_", " ").title()
                    lines.append(f"  - *{pretty}:* {val}")

        return "\n".join(lines)

    parts = [
        "# RAIDSense Report",
        section("Risks", raid.get("risks", []), ["mitigation"]),
        section("Assumptions", raid.get("assumptions", []), ["validation_step"]),
        section("Issues", raid.get("issues", []), ["next_step"]),
        section("Dependencies", raid.get("dependencies", []), ["owner", "due_date"]),
        "",
    ]
    return "\n\n".join(parts)

def list_txt_files(folder: Path) -> list[Path]:
    return sorted([p for p in folder.glob("*.txt") if p.is_file()])


def choose_file_interactively(files: list[Path]) -> Path:
    if not files:
        raise FileNotFoundError("No .txt files found in this folder.")

    print("\nChoose a notes file:\n")
    for i, f in enumerate(files, start=1):
        print(f"{i}) {f.name}")

    choice = input("\nEnter a number (or press Enter for 1): ").strip()

    if choice == "":
        return files[0]

    if not choice.isdigit():
        raise ValueError("Please enter a valid number.")

    idx = int(choice)
    if idx < 1 or idx > len(files):
        raise ValueError("Number out of range.")

    return files[idx - 1]

def main():
    # Use filename passed on the command line, or default to sample_notes.txt
    if len(sys.argv) > 1:
        notes_file = sys.argv[1]
    else:
    # Interactive picker if no file was provided
        files = list_txt_files(Path.cwd())
        notes_path = choose_file_interactively(files)
        notes_file = notes_path.name

    try:
        notes = load_notes(notes_file)
    except FileNotFoundError as e:
        print(e)
        print("Make sure the notes file exists in the same folder as app.py.")
        return

    print("Loaded meeting notes from", notes_file)
    print("Sending to OpenAI for RAID analysis (structured JSON)...\n")

    try:
        raid_data = analyse_notes_with_openai(notes)
    except json.JSONDecodeError:
        print("ERROR: The model output was not valid JSON. Printing raw output below:\n")
        # If this happens, structured outputs probably aren't enabled / model mismatch.
        # Re-run after checking model + schema params.
        raise

    raid_markdown = render_markdown(raid_data)

    # Print to terminal
    print("===== RAIDSense Output =====\n")
    print(raid_markdown)
    print("\n============================\n")

    # Save both JSON + Markdown reports
    notes_path = Path(notes_file)

    json_path = notes_path.with_name(notes_path.stem + "_RAID.json")
    md_path = notes_path.with_name(notes_path.stem + "_RAID.md")

    json_path.write_text(json.dumps(raid_data, indent=2), encoding="utf-8")
    md_path.write_text(raid_markdown, encoding="utf-8")

    print(f"RAID JSON saved to: {json_path.name}")
    print(f"RAID Markdown saved to: {md_path.name}")


if __name__ == "__main__":
    main()