from pypdf import PdfReader
import tiktoken

def extract_text(filepath):
    if filepath.endswith(".pdf"):
        reader = PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # Fallback for Windows-1252 or other encodings
            with open(filepath, "r", encoding="windows-1252", errors="replace") as f:
                return f.read()

def chunk_text(text, max_tokens=500):
    """Split into chunks by token count so nothing exceeds context limits."""
    enc = tiktoken.get_encoding("cl100k_base")
    words = text.split()
    chunks, current, current_tokens = [], [], 0

    for word in words:
        tok_len = len(enc.encode(word + " "))
        if current_tokens + tok_len > max_tokens:
            chunks.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(word)
        current_tokens += tok_len

    if current:
        chunks.append(" ".join(current))
    return chunks
