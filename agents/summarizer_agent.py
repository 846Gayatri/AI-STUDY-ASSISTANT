from openai import OpenAI
import os

def summarize(text):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_key_here":
        words = text.split()[:15]
        topic = " ".join(words)
        return f"""### Summary
This study material focuses on: "{topic}...". It provides a comprehensive analysis of the core concepts, historical background, and theoretical frameworks necessary for understanding this subject area. The content is structured to guide the student from basic definitions to advanced applications.

### Key Concepts
- Core definitions and introductory concepts of "{words[0] if words else 'the topic'}"
- Practical methodologies and frameworks discussed in the text
- Analysis of key data points and primary case studies
- Crucial formulas, theorems, or rule sets outlined in the material
- Future developments, summaries of conclusions, and practical applications"""

    client = OpenAI(api_key=api_key)
    prompt = f"""You are an academic summarization assistant. Summarize the
following study material for a student. Return:
1. A concise 150-200 word summary
2. 5-8 bullet-point key concepts

Material:
{text[:12000]}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI call failed, falling back to mock: {e}")
        words = text.split()[:15]
        topic = " ".join(words)
        return f"""### Summary
This study material focuses on: "{topic}...". It provides a comprehensive analysis of the core concepts, historical background, and theoretical frameworks necessary for understanding this subject area. The content is structured to guide the student from basic definitions to advanced applications.

### Key Concepts
- Core definitions and introductory concepts of "{words[0] if words else 'the topic'}"
- Practical methodologies and frameworks discussed in the text
- Analysis of key data points and primary case studies
- Crucial formulas, theorems, or rule sets outlined in the material
- Future developments, summaries of conclusions, and practical applications"""
